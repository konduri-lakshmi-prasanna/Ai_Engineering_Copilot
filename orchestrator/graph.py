from langgraph.graph import StateGraph, END
from typing import TypedDict
from agents.github_agent import github_agent
from agents.logs_agent import logs_agent
from llm_client import ask_groq


class CopilotState(TypedDict):
    repo_name: str
    log_text: str
    github_data: dict
    logs_data: dict
    root_cause: str


def github_node(state: CopilotState) -> CopilotState:
    # Keep commit count low to avoid oversized prompts later
    state["github_data"] = github_agent(state["repo_name"], limit=3)
    return state


def logs_node(state: CopilotState) -> CopilotState:
    state["logs_data"] = logs_agent(state["log_text"])
    return state


def reasoning_node(state: CopilotState) -> CopilotState:
    # Summarize commits instead of sending everything (avoids token limit errors)
    commits_summary = []
    for c in state["github_data"]["commits"][:3]:
        commits_summary.append({
            "sha": c["sha"],
            "message": c["message"][:200],
            "files_changed": c["files_changed"][:10],
        })

    prompt = f"""
You are an AI Engineering Copilot analyzing a deployment failure.

Recent commits:
{commits_summary}

Log errors found:
{state['logs_data']['errors'][:10]}

Based on this evidence, identify the likely root cause of the failure,
explain why it happened, and suggest a fix. Be concise.
"""
    state["root_cause"] = ask_groq(prompt)
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