import json
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any
from agents.github_agent import github_agent, github_agent_targeted, fetch_package_json
from agents.log_parser import extract_file_paths
from agents.logs_agent import logs_agent
from agents.docs_rag_agent import docs_rag_agent
from llm_client import ask_groq_json


class CopilotState(TypedDict):
    repo_name: str
    log_text: str
    github_token: str
    github_data: dict
    logs_data: dict
    docs_data: dict
    implicated_commits: List[Dict[str, Any]]
    root_cause: str
    fix_suggestion: str
    why_it_works: str
    beginner_explanation: str
    interview_questions: List[str]
    documentation_links: List[str]


def github_node(state: CopilotState) -> CopilotState:
    file_paths = extract_file_paths(state["log_text"])
    token = state.get("github_token") or None

    if file_paths:
        # We found real file paths in the stack trace — go fetch exactly
        # those files and their real history instead of guessing.
        data = github_agent_targeted(state["repo_name"], file_paths, token=token)
        data["mode"] = "targeted"
    else:
        # No identifiable file path in the log — fall back to a blind
        # recent-commits scan.
        data = github_agent(state["repo_name"], limit=8, token=token)
        data["mode"] = "recent"

    # Always fetch package.json's scripts — it's the ground truth for
    # npm "missing script" errors, regardless of which mode ran above.
    data["package_json"] = fetch_package_json(state["repo_name"], token=token)

    state["github_data"] = data
    return state


def logs_node(state: CopilotState) -> CopilotState:
    state["logs_data"] = logs_agent(state["log_text"])
    return state


def docs_node(state: CopilotState) -> CopilotState:
    # Query the local RAG knowledge base using the actual error lines
    # found in the log — not the raw log_text — so retrieval is grounded
    # in the specific error signal rather than diluted by noise.
    error_lines = state["logs_data"].get("errors", [])
    query_text = " ".join(error_lines[:20])
    state["docs_data"] = docs_rag_agent(query_text, top_k=3)
    return state


def reasoning_node(state: CopilotState) -> CopilotState:
    github_data = state["github_data"]
    mode = github_data.get("mode", "recent")

    if mode == "targeted":
        evidence = []
        for f in github_data["files"]:
            entry = {"file": f["path"], "found_in_repo": f["found"]}
            if f["found"]:
                entry["current_content_snippet"] = f["current_content"]
            if f.get("error"):
                entry["note"] = f["error"]
            entry["recent_commits_touching_this_file"] = [
                {"sha": c["sha"], "message": c["message"], "patch": c["patch"]}
                for c in f["commits"]
            ]
            evidence.append(entry)

        evidence_json = json.dumps(evidence, indent=2)
        evidence_label = (
            "the specific files named in the stack trace/log, each with its "
            "current content and the real recent commits that touched it"
        )
    else:
        commits_context = []
        for c in github_data["commits"]:
            commits_context.append({
                "sha": c["sha"],
                "message": c["message"][:200],
                "files": [
                    {"filename": f["filename"], "status": f["status"], "patch": f["patch"]}
                    for f in c["files"]
                ],
            })
        evidence_json = json.dumps(commits_context, indent=2)
        evidence_label = (
            "the most recent commits in the repo (no specific file could be "
            "identified from the log, so this is a broader recent-activity scan)"
        )

    # This is now OUTSIDE the if/else, so it applies in both modes.
    package_json_info = github_data.get("package_json")
    package_json_block = (
        f"\npackage.json scripts (ground truth — if the error mentions a missing "
        f"npm script, check here directly, don't guess):\n{json.dumps(package_json_info, indent=2)}\n"
        if package_json_info else ""
    )

    # Documentation retrieved from the local RAG knowledge base. Only
    # included if something actually matched — an empty list means the
    # model should not pretend it has relevant docs to lean on.
    docs_results = state.get("docs_data", {}).get("results", [])
    docs_block = ""
    if docs_results:
        docs_context = [
            {"title": d["title"], "url": d["url"], "summary": d["snippet"]}
            for d in docs_results
        ]
        docs_block = (
            f"\nRelevant documentation retrieved from the knowledge base "
            f"(use this to inform root_cause/fix_suggestion and cite the "
            f"url(s) in documentation_links if you actually use them):\n"
            f"{json.dumps(docs_context, indent=2)}\n"
        )

    prompt = f"""
You are an AI Engineering Copilot analyzing a deployment failure. You don't
just diagnose — you also teach. The person reading your output may be a
student or junior developer, so explain things clearly.

You are given {evidence_label}, plus errors extracted from a deployment log.

Evidence:
{evidence_json}
{package_json_block}
{docs_block}
Log errors:
{json.dumps(state['logs_data']['errors'][:20], indent=2)}

Task:
0. Ground your answer only in the evidence actually provided above. If the
   evidence doesn't clearly explain the error, say so plainly in root_cause
   instead of inventing a plausible-sounding but unverified explanation.
1. Identify which file(s)/commit(s) above are actually responsible for the
   reported errors, based on the real content/diffs shown — not guesses.
   There could be one, several, or none. Reference specific commit sha(s)
   where relevant.
2. Explain the root cause concretely.
3. Suggest a specific fix.
4. Explain WHY that fix works — the underlying mechanism, not just "this fixes it".
5. Write a beginner_explanation: 2-4 sentences explaining the general concept
   behind this bug, as if teaching someone new to the topic.
6. Write 2-3 short interview_questions related to the concept behind this bug.
7. If the documentation block above has entries you actually used, list their
   url(s) in documentation_links. If it's empty or irrelevant, return an
   empty list — don't invent a link.

Respond ONLY with a JSON object in exactly this shape, no other text:
{{
  "implicated_commits": [{{"sha": "<short sha>", "reason": "<why this is likely responsible>"}}],
  "root_cause": "<explanation>",
  "fix_suggestion": "<concrete fix>",
  "why_it_works": "<why the suggested fix resolves the root cause>",
  "beginner_explanation": "<plain-language explanation of the underlying concept>",
  "interview_questions": ["<question 1>", "<question 2>"],
  "documentation_links": ["<url 1>"]
}}

If nothing above appears responsible, return an empty list for
implicated_commits and say so plainly in root_cause. Still fill in
beginner_explanation and interview_questions based on the log errors alone.
"""

    raw = ask_groq_json(prompt)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = {
            "implicated_commits": [],
            "root_cause": raw or "The model did not return a parseable result.",
            "fix_suggestion": "",
            "why_it_works": "",
            "beginner_explanation": "",
            "interview_questions": [],
            "documentation_links": [],
        }

    state["implicated_commits"] = parsed.get("implicated_commits", [])
    state["root_cause"] = parsed.get("root_cause", "")
    state["fix_suggestion"] = parsed.get("fix_suggestion", "")
    state["why_it_works"] = parsed.get("why_it_works", "")
    state["beginner_explanation"] = parsed.get("beginner_explanation", "")
    state["interview_questions"] = parsed.get("interview_questions", [])
    state["documentation_links"] = parsed.get("documentation_links", [])
    return state


def build_graph():
    graph = StateGraph(CopilotState)
    graph.add_node("github", github_node)
    graph.add_node("logs", logs_node)
    graph.add_node("docs", docs_node)
    graph.add_node("reasoning", reasoning_node)

    graph.set_entry_point("github")
    graph.add_edge("github", "logs")
    graph.add_edge("logs", "docs")
    graph.add_edge("docs", "reasoning")
    graph.add_edge("reasoning", END)

    return graph.compile()