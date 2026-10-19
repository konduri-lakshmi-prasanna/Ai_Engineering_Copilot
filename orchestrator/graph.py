import uuid
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END

from schemas import CopilotState
from agents.orchestrator_agent import plan_investigation, synthesize_final_report
from agents.github_agent import run_github_investigation
from agents.logs_agent import logs_agent
from agents.log_parser import extract_file_paths
from agents.cicd_agent import cicd_agent
from agents.infra_agent import infra_agent
from agents.docs_rag_agent import knowledge_agent
from agents.verification_agent import verify_investigation


def plan_node(state: CopilotState) -> Dict[str, Any]:
    repo = state.get("repo_name", "")
    log_text = state.get("log_text", "")
    incident_id = state.get("incident_id") or str(uuid.uuid4())[:8]

    plan = plan_investigation(repo, log_text)
    event = {
        "stage": "plan",
        "agent": "Orchestrator Agent",
        "status": "COMPLETED",
        "message": f"Formulated investigation plan with specialists: {', '.join(plan.required_specialists)}",
    }
    events = list(state.get("events", []))
    events.append(event)

    return {
        "incident_id": incident_id,
        "active_plan": plan.model_dump(),
        "investigation_round": state.get("investigation_round", 1),
        "max_rounds": state.get("max_rounds", 2),
        "events": events,
    }


def github_node(state: CopilotState) -> Dict[str, Any]:
    file_paths = extract_file_paths(state.get("log_text", ""))
    token = state.get("github_token") or None
    out = run_github_investigation(state.get("repo_name", ""), file_paths=file_paths, token=token)
    return {"github_output": out.model_dump()}


def logs_node(state: CopilotState) -> Dict[str, Any]:
    out = logs_agent(state.get("log_text", ""))
    return {"logs_output": out.model_dump()}


def cicd_node(state: CopilotState) -> Dict[str, Any]:
    token = state.get("github_token") or None
    out = cicd_agent(state.get("repo_name", ""), state.get("log_text", ""), token=token)
    return {"cicd_output": out.model_dump()}


def infra_node(state: CopilotState) -> Dict[str, Any]:
    token = state.get("github_token") or None
    out = infra_agent(state.get("repo_name", ""), state.get("log_text", ""), token=token)
    return {"infra_output": out.model_dump()}


def merge_node(state: CopilotState) -> Dict[str, Any]:
    outputs: Dict[str, Dict[str, Any]] = {}
    merged_findings: List[Dict[str, Any]] = []

    events = list(state.get("events", []))

    for key, out_key in [("github", "github_output"), ("logs", "logs_output"), ("cicd", "cicd_output"), ("infra", "infra_output")]:
        out = state.get(out_key)
        if out:
            outputs[key] = out
            merged_findings.extend(out.get("findings", []))
            events.append({
                "stage": key,
                "agent": out.get("agent_name", key),
                "status": out.get("status", "COMPLETED"),
                "message": out.get("summary", ""),
            })

    events.append({
        "stage": "merge",
        "agent": "Orchestrator Agent",
        "status": "COMPLETED",
        "message": f"Aggregated {len(merged_findings)} findings across parallel specialist investigations.",
    })

    return {
        "agent_outputs": outputs,
        "merged_findings": merged_findings,
        "events": events,
    }


def docs_node(state: CopilotState) -> Dict[str, Any]:
    logs_out = state.get("logs_output", {})
    error_snippets = [
        ev.get("snippet", "")
        for ev in logs_out.get("supporting_evidence", [])
        if ev.get("source_type") == "log_line"
    ]
    query = " ".join(error_snippets[:10]) or state.get("log_text", "")[:200]

    out = knowledge_agent(query, top_k=3)
    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs["docs"] = out.model_dump()

    events = list(state.get("events", []))
    events.append({
        "stage": "docs",
        "agent": "Knowledge and Documentation Agent",
        "status": out.status.value,
        "message": out.summary,
    })

    return {
        "docs_output": out.model_dump(),
        "agent_outputs": agent_outputs,
        "events": events,
    }


def verification_node(state: CopilotState) -> Dict[str, Any]:
    agent_outputs = state.get("agent_outputs", {})
    log_text = state.get("log_text", "")

    logs_summary = agent_outputs.get("logs", {}).get("summary", "")
    github_findings = agent_outputs.get("github", {}).get("findings", [])
    proposed_cause = github_findings[0].get("description") if github_findings else logs_summary
    proposed_fix = "Correct the implicated configuration or update dependencies."

    ver_result = verify_investigation(agent_outputs, proposed_cause, proposed_fix, log_text)

    events = list(state.get("events", []))
    events.append({
        "stage": "verification",
        "agent": "Verification Agent",
        "status": "COMPLETED" if ver_result.is_sufficient else "INSUFFICIENT_DATA",
        "message": (
            f"Evidence {'sufficient' if ver_result.is_sufficient else 'insufficient'}. "
            f"Confirmed facts: {len(ver_result.confirmed_facts)}, Contradictions: {len(ver_result.contradictions_found)}."
        ),
    })

    return {
        "verification": ver_result.model_dump(),
        "events": events,
    }


def route_verification(state: CopilotState) -> str:
    ver = state.get("verification") or {}
    round_no = state.get("investigation_round", 1)
    max_rounds = state.get("max_rounds", 2)

    if ver.get("needs_reinvestigation") and round_no < max_rounds:
        return "reinvestigate"
    return "final_report"


def reinvestigate_node(state: CopilotState) -> Dict[str, Any]:
    new_round = state.get("investigation_round", 1) + 1
    events = list(state.get("events", []))
    events.append({
        "stage": "reinvestigate",
        "agent": "Orchestrator Agent",
        "status": "RUNNING",
        "message": f"Entering investigation round {new_round} to resolve unverified assumptions.",
    })
    return {
        "investigation_round": new_round,
        "events": events,
    }


def final_report_node(state: CopilotState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "inc-1")
    repo = state.get("repo_name", "")
    log_text = state.get("log_text", "")
    agent_outputs = state.get("agent_outputs", {})
    verification = state.get("verification", {})
    rounds = state.get("investigation_round", 1)

    report = synthesize_final_report(
        incident_id=incident_id,
        repo_name=repo,
        log_text=log_text,
        agent_outputs=agent_outputs,
        verification_dict=verification,
        investigation_rounds=rounds,
    )

    events = list(state.get("events", []))
    events.append({
        "stage": "final_report",
        "agent": "Orchestrator Agent",
        "status": "COMPLETED",
        "message": "Final incident report generated and verified.",
    })

    implicated = [
        {"sha": ev.reference.replace("commit:", ""), "reason": ev.relevance}
        for ev in report.supporting_evidence if "commit:" in ev.reference
    ]

    return {
        "final_report": report.model_dump(),
        "root_cause": report.most_likely_root_cause,
        "fix_suggestion": report.recommended_fix,
        "why_it_works": report.why_it_works,
        "beginner_explanation": report.beginner_explanation,
        "interview_questions": report.interview_questions,
        "documentation_links": [
            ev.reference for ev in report.supporting_evidence if ev.source_type.value == "documentation"
        ],
        "implicated_commits": implicated,
        "github_data": {
            "mode": "targeted",
            "files": [],
            "commits": implicated,
        },
        "logs_data": {
            "error_count": len([ev for ev in report.supporting_evidence if ev.source_type.value == "log_line"]),
            "errors": [ev.snippet for ev in report.supporting_evidence if ev.source_type.value == "log_line"],
        },
        "docs_data": {
            "results": [
                {"title": ev.reference, "url": "", "snippet": ev.snippet}
                for ev in report.supporting_evidence if ev.source_type.value == "documentation"
            ]
        },
        "events": events,
    }


def build_graph():
    graph = StateGraph(CopilotState)

    # Add all agent nodes
    graph.add_node("plan", plan_node)
    graph.add_node("github", github_node)
    graph.add_node("logs", logs_node)
    graph.add_node("cicd", cicd_node)
    graph.add_node("infra", infra_node)
    graph.add_node("merge", merge_node)
    graph.add_node("docs", docs_node)
    graph.add_node("verification", verification_node)
    graph.add_node("reinvestigate", reinvestigate_node)
    graph.add_node("final_report", final_report_node)

    # Entry and Parallel Dispatch (Fan-out)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "github")
    graph.add_edge("plan", "logs")
    graph.add_edge("plan", "cicd")
    graph.add_edge("plan", "infra")

    # Fan-in to Merge
    graph.add_edge("github", "merge")
    graph.add_edge("logs", "merge")
    graph.add_edge("cicd", "merge")
    graph.add_edge("infra", "merge")

    # Knowledge correlation & Verification
    graph.add_edge("merge", "docs")
    graph.add_edge("docs", "verification")

    # Conditional routing after verification
    graph.add_conditional_edges(
        "verification",
        route_verification,
        {
            "reinvestigate": "reinvestigate",
            "final_report": "final_report",
        },
    )

    # Bounded retry loop back to specialists
    graph.add_edge("reinvestigate", "github")

    # Final report to END
    graph.add_edge("final_report", END)

    return graph.compile()