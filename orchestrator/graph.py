import json
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any
from agents.github_agent import github_agent
from agents.logs_agent import logs_agent
from llm_client import ask_groq_json


class CopilotState(TypedDict):
    repo_name: str
    log_text: str
    github_data: dict
    logs_data: dict
    implicated_commits: List[Dict[str, Any]]
    root_cause: str
    fix_suggestion: str


def github_node(state: CopilotState) -> CopilotState:
    # Scan a much wider window than before — the reasoning step decides
    # which of these are actually relevant, nothing is pre-filtered here.
    state["github_data"] = github_agent(state["repo_name"], limit=30)
    return state


def logs_node(state: CopilotState) -> CopilotState:
    state["logs_data"] = logs_agent(state["log_text"])
    return state


def reasoning_node(state: CopilotState) -> CopilotState:
    commits_context = []
    for c in state["github_data"]["commits"]:
        commits_context.append({
            "sha": c["sha"],
            "message": c["message"][:200],
            "files": [
                {
                    "filename": f["filename"],
                    "status": f["status"],
                    "patch": f["patch"],
                }
                for f in c["files"]
            ],
        })

    prompt = f"""
You are an AI Engineering Copilot analyzing a deployment failure.

You are given up to {len(commits_context)} recent commits (most recent first),
each with its changed files and a diff snippet, plus errors extracted from a
deployment log.

Commits:
{json.dumps(commits_context, indent=2)}

Log errors:
{json.dumps(state['logs_data']['errors'][:20], indent=2)}

Task:
1. Decide which of the commits above are actually likely responsible for the
   reported errors, based on the diffs — not just how recent they are. There
   could be one commit, several, or none at all. Only include a commit if its
   diff plausibly explains one of the log errors.
2. Explain the root cause, referencing the specific implicated commit sha(s).
3. Suggest a concrete fix.

Respond ONLY with a JSON object in exactly this shape, no other text:
{{
  "implicated_commits": [{{"sha": "<short sha>", "reason": "<why this commit likely caused it>"}}],
  "root_cause": "<explanation>",
  "fix_suggestion": "<concrete fix>"
}}

If none of the provided commits appear responsible, return an empty list for
implicated_commits and say so plainly in root_cause.
"""

    raw = ask_groq_json(prompt)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = {
            "implicated_commits": [],
            "root_cause": raw or "The model did not return a parseable result.",
            "fix_suggestion": "",
        }

    state["implicated_commits"] = parsed.get("implicated_commits", [])
    state["root_cause"] = parsed.get("root_cause", "")
    state["fix_suggestion"] = parsed.get("fix_suggestion", "")
    return state


def build_graph():
    graph = StateGraph(CopilotState)
    graph.add_node("github", github_node)
    graph.add_node("logs", logs_node)
    graph.add_node("reasoning", reasoning_node)

    graph.set_entry_point("github")
    graph.add_edge("github", "logs")
    graph.add_edge("logs", "reasoning")
    graph.add_edge("reasoning", END)

    return graph.compile()