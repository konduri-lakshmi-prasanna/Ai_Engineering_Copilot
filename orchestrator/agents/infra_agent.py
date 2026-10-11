import os
import re
from typing import Dict, Any, Optional, List
from github import Github
from schemas import (
    AgentOutput,
    AgentExecutionStatus,
    SpecialistFinding,
    EvidenceItem,
    EvidenceType,
    FindingSeverity,
)


def infra_agent(repo_name: str, log_text: str, token: Optional[str] = None) -> AgentOutput:
    """
    Infrastructure Investigation Agent.
    Investigates Docker configuration, container startup failures, environment setups,
    and Kubernetes runtime events.
    - Inspects Dockerfile and docker-compose.yml in the repository
    - Detects container lifecycle errors (CrashLoopBackOff, OOMKilled, Connection Refused, Missing ENV)
    - Clearly marks when live cluster integration is unavailable and uses static/log signals
    """
    findings: List[SpecialistFinding] = []
    evidence: List[EvidenceItem] = []
    integration_status: Dict[str, Any] = {
        "live_k8s_connected": False,
        "dockerfile_found": False,
        "compose_found": False,
    }

    token = token or os.getenv("GITHUB_TOKEN")

    # 1. Inspect repository infrastructure files (Dockerfile, docker-compose)
    if token:
        try:
            gh = Github(token)
            repo = gh.get_repo(repo_name)
            for path in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "k8s/deployment.yaml"]:
                try:
                    content_file = repo.get_contents(path)
                    raw = content_file.decoded_content.decode("utf-8", errors="replace")
                    if "dockerfile" in path.lower():
                        integration_status["dockerfile_found"] = True
                    if "compose" in path.lower():
                        integration_status["compose_found"] = True

                    evidence.append(
                        EvidenceItem(
                            source_type=EvidenceType.INFRA_EVENT,
                            reference=path,
                            snippet=raw[:600],
                            relevance=f"Infrastructure configuration file {path}",
                        )
                    )
                except Exception:
                    pass
        except Exception as e:
            integration_status["github_error"] = str(e)

    # 2. Extract infrastructure error patterns from log
    infra_error_patterns = [
        (r"CrashLoopBackOff", "Container Lifecycle", "Container continuously crashed upon startup (CrashLoopBackOff)."),
        (r"OOMKilled|out of memory|exit code 137", "Resource Limits", "Process exceeded container memory limits and was killed by Linux OOM killer."),
        (r"ECONNREFUSED|connect: connection refused", "Networking / Port Binding", "Service attempted to connect to target port/host but connection was refused."),
        (r"standard_init_linux\.go:\d+: exec user process caused: (.*)", "Container Runtime Exec", "Container entrypoint failed to execute."),
        (r"(?:ENV|DATABASE_URL|PORT|SECRET|API_KEY).*(?:is undefined|is null|missing|not set)", "Environment Configuration", "Mandatory environment variable missing in runtime container context."),
        (r"bind: address already in use|port \d+ already allocated", "Port Allocation Conflict", "Container failed to bind to target port because it is already occupied."),
    ]

    for pattern, cat, desc in infra_error_patterns:
        match = re.search(pattern, log_text, re.IGNORECASE)
        if match:
            matched_line = match.group(0)
            ev = EvidenceItem(
                source_type=EvidenceType.INFRA_EVENT,
                reference=f"log:infra-signal-{len(evidence)+1}",
                snippet=matched_line,
                relevance=f"Infrastructure failure signature detected: {cat}",
            )
            evidence.append(ev)

            findings.append(
                SpecialistFinding(
                    category=cat,
                    description=f"{desc} Matched: '{matched_line}'",
                    severity=FindingSeverity.CRITICAL if "OOM" in cat or "Crash" in cat else FindingSeverity.HIGH,
                    confidence=0.88,
                    evidence_items=[ev],
                )
            )

    summary = (
        f"Infrastructure Agent analyzed runtime environment and identified {len(findings)} infra-level problems."
        if findings
        else "No infrastructure, container crash, or networking binding errors identified in the deployment log."
    )

    status = AgentExecutionStatus.COMPLETED if findings or evidence else AgentExecutionStatus.INSUFFICIENT_DATA

    return AgentOutput(
        agent_name="Infrastructure Investigation Agent",
        status=status,
        summary=summary,
        findings=findings,
        supporting_evidence=evidence,
        confidence_estimate=0.85 if findings else 0.2,
        unresolved_questions=[
            "Live Kubernetes cluster integration is optional and currently offline; analysis performed from container logs and repo specs."
        ],
        recommended_next_steps=[
            "Verify container environment variables, memory limits, and service ports in docker-compose.yml / deployment manifests."
        ] if findings else [],
        integration_status=integration_status,
    )
