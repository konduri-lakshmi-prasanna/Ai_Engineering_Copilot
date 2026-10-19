import uuid
import json
import os
from typing import Dict, Any, List, Optional
from schemas import (
    InvestigationPlan,
    IncidentReport,
    EvidenceItem,
    EvidenceType,
    AgentOutput,
    VerificationResult,
)
from llm_client import ask_groq_json, ask_groq


def plan_investigation(repo_name: str, log_text: str) -> InvestigationPlan:
    """
    Orchestrator Agent - Planning Phase.
    Examines incident request and error signals to create a structured investigation plan.
    Determines which specialist agents to activate.
    """
    plan_id = str(uuid.uuid4())[:8]

    # Deterministic heuristics to select specialists based on log signals
    specialists = ["github", "logs", "docs"]

    if any(k in log_text.lower() for k in ["workflow", "action", "exit code", "step", "ci", "build"]):
        specialists.append("cicd")

    if any(k in log_text.lower() for k in ["docker", "container", "crashloop", "oom", "port", "k8s", "pod"]):
        specialists.append("infra")

    initial_hypotheses = []
    if "missing script" in log_text.lower():
        initial_hypotheses.append("npm/yarn build command references a script not present in package.json")
    elif "database" in log_text.lower() or "connection" in log_text.lower():
        initial_hypotheses.append("Database connection failure due to missing or null environment variable")
    elif "syntaxerror" in log_text.lower() or "traceback" in log_text.lower():
        initial_hypotheses.append("Application runtime exception in recently modified source code")
    else:
        initial_hypotheses.append("Deployment failure detected in build or execution logs")

    return InvestigationPlan(
        plan_id=plan_id,
        incident_summary=f"Deployment failure investigation for repository {repo_name}",
        required_specialists=specialists,
        initial_hypotheses=initial_hypotheses,
        focus_areas={
            "github": "Inspect recent commits and configuration files",
            "logs": "Parse stack trace and identify primary error",
            "docs": "Retrieve remediation documentation",
            "cicd": "Examine workflow definitions and pipeline steps",
            "infra": "Examine container environment and resource limits",
        },
    )


def synthesize_final_report(
    incident_id: str,
    repo_name: str,
    log_text: str,
    agent_outputs: Dict[str, Dict[str, Any]],
    verification_dict: Dict[str, Any],
    investigation_rounds: int = 1,
) -> IncidentReport:
    """
    Orchestrator Agent - Final Synthesis Phase.
    Combines verified facts, evidence items, and specialist outputs into the authoritative IncidentReport.
    Uses LLM reasoning grounded strictly in evidence, falling back to deterministic synthesis if needed.
    """
    verification = VerificationResult(**verification_dict) if verification_dict else None

    # Collect all evidence items from all agents
    all_evidence: List[EvidenceItem] = []
    agent_summaries: Dict[str, str] = {}

    for agent_key, out in agent_outputs.items():
        summary = out.get("summary", "")
        agent_summaries[agent_key] = summary
        for ev in out.get("supporting_evidence", []):
            try:
                all_evidence.append(EvidenceItem(**ev) if isinstance(ev, dict) else ev)
            except Exception:
                pass

    evidence_summary = [
        {"source": ev.source_type.value, "reference": ev.reference, "snippet": ev.snippet[:150]}
        for ev in all_evidence[:10]
    ]

    prompt = f"""
You are the Orchestrator Agent synthesizing a verified incident diagnosis report for {repo_name}.
Below is the verified evidence gathered by specialist agents:

Confirmed Facts:
{json.dumps(verification.confirmed_facts if verification else [], indent=2)}

Contradictions Found:
{json.dumps(verification.contradictions_found if verification else [], indent=2)}

Specialist Agent Summaries:
{json.dumps(agent_summaries, indent=2)}

Evidence Samples:
{json.dumps(evidence_summary, indent=2)}

Log snippet:
{log_text[:500]}

Generate a structured final incident report conforming strictly to the evidence:
1. most_likely_root_cause: Concrete root cause based only on verified evidence. If evidence is insufficient, say "Root cause could not be conclusively confirmed."
2. recommended_fix: Clear, copy-pasteable resolution steps.
3. why_it_works: Explanation of why the fix resolves the root mechanism.
4. preventive_measures: 2-3 preventive DevOps/engineering actions.
5. remaining_uncertainty: Any remaining unknown or unverified factors.
6. beginner_explanation: 2-3 sentence concept explanation for a junior developer.
7. interview_questions: 2 relevant technical interview questions.

Respond ONLY with a JSON object in this exact schema:
{{
  "most_likely_root_cause": "...",
  "recommended_fix": "...",
  "why_it_works": "...",
  "preventive_measures": ["...", "..."],
  "remaining_uncertainty": "...",
  "beginner_explanation": "...",
  "interview_questions": ["...", "..."]
}}
"""
    try:
        raw_llm = ask_groq_json(prompt)
        parsed = json.loads(raw_llm)
    except Exception:
        # Graceful deterministic fallback
        logs_summary = agent_summaries.get("logs", "Error found in deployment logs.")
        parsed = {
            "most_likely_root_cause": logs_summary,
            "recommended_fix": "Check the primary error line and configuration files identified in the investigation.",
            "why_it_works": "Restores required environment configuration or source code compatibility.",
            "preventive_measures": [
                "Implement pre-commit validation and CI checks.",
                "Ensure environment variables are checked during build time.",
            ],
            "remaining_uncertainty": "External service availability and cluster state were not verified live.",
            "beginner_explanation": "Deployment failures typically occur when code changes introduce unmet expectations about runtime configurations or scripts.",
            "interview_questions": [
                "How do you distinguish between primary and cascading deployment errors?",
                "How would you ensure database connection variables are validated before application startup?",
            ],
        }

    return IncidentReport(
        incident_id=incident_id,
        repo=repo_name,
        confirmed_facts=verification.confirmed_facts if verification else ["Deployment error logged."],
        most_likely_root_cause=parsed.get("most_likely_root_cause", "Root cause under review."),
        supporting_evidence=all_evidence[:10],
        contradictory_or_missing_evidence=verification.contradictions_found if verification else [],
        recommended_fix=parsed.get("recommended_fix", "Consult the suggested fix instructions."),
        why_it_works=parsed.get("why_it_works", ""),
        validation_performed=verification.validation_performed if verification else "Automated evidence verification.",
        validation_result=verification.fix_validation_result if verification else "Completed.",
        preventive_measures=parsed.get("preventive_measures", []),
        remaining_uncertainty=parsed.get("remaining_uncertainty", "None reported."),
        beginner_explanation=parsed.get("beginner_explanation", ""),
        interview_questions=parsed.get("interview_questions", []),
        investigation_rounds=investigation_rounds,
        agent_summaries=agent_summaries,
    )
