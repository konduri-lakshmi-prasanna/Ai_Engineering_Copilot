import os
import re
import yaml
from typing import Dict, Any, Optional, List
from github import Github, Auth
from schemas import (
    AgentOutput,
    AgentExecutionStatus,
    SpecialistFinding,
    EvidenceItem,
    EvidenceType,
    FindingSeverity,
)


def cicd_agent(repo_name: str, log_text: str, token: Optional[str] = None) -> AgentOutput:
    """
    CI/CD Investigation Agent.
    Investigates build, test, and deployment pipelines.
    - Inspects GitHub Actions workflow definitions in .github/workflows/
    - Analyzes pipeline logs for failed stages, dependency steps, test failures
    - Correlates CI/CD configuration with actual runtime failures
    """
    findings: List[SpecialistFinding] = []
    evidence: List[EvidenceItem] = []
    integration_status: Dict[str, Any] = {"live_cicd_available": False, "workflows_inspected": []}

    token = token or os.getenv("GITHUB_TOKEN")
    workflow_files: Dict[str, str] = {}

    # 1. Fetch workflow configurations from repository if accessible
    if token:
        try:
            gh = Github(auth=Auth.Token(token))
            repo = gh.get_repo(repo_name)
            try:
                contents = repo.get_contents(".github/workflows")
                for item in contents:
                    if item.path.endswith((".yml", ".yaml")):
                        try:
                            content_str = item.decoded_content.decode("utf-8", errors="replace")
                            workflow_files[item.path] = content_str
                            integration_status["workflows_inspected"].append(item.path)
                        except Exception:
                            pass
            except Exception:
                # No .github/workflows directory found
                pass
        except Exception as e:
            integration_status["github_error"] = str(e)

    # 2. Check for CI/CD signals in deployment log
    is_ci_failure = False
    pipeline_signals = []

    ci_patterns = [
        (r"(?:npm run build|yarn build|pnpm build) failed with exit code (\d+)", "Build Step Failure"),
        (r"(?:pytest|jest|mocha|npm test) failed", "Test Suite Failure"),
        (r"actions/setup-(?:node|python|java)@v\d+.*failed", "CI Environment Setup Failure"),
        (r"Process completed with exit code (\d+)", "Workflow Step Exit Failure"),
        (r"##\[error\](.*)", "GitHub Actions Annotations Error"),
    ]

    for pattern, cat in ci_patterns:
        matches = re.finditer(pattern, log_text, re.IGNORECASE)
        for m in matches:
            is_ci_failure = True
            matched_line = m.group(0)
            pipeline_signals.append((cat, matched_line))
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceType.CICD_STEP,
                    reference=f"pipeline:signal-{len(evidence)+1}",
                    snippet=matched_line,
                    relevance=f"Detected CI/CD pipeline step error: {cat}",
                )
            )

    # 3. Correlate with workflow files
    if workflow_files:
        for path, yml_content in workflow_files.items():
            evidence.append(
                EvidenceItem(
                    source_type=EvidenceType.CICD_STEP,
                    reference=path,
                    snippet=yml_content[:500],
                    relevance=f"Workflow definition file {path}",
                )
            )

            # Check if workflow defines missing scripts or variables
            if "npm run test" in yml_content and "npm test" in log_text:
                findings.append(
                    SpecialistFinding(
                        category="CI/CD Step Mismatch",
                        description=f"Workflow {path} invokes test commands that failed in pipeline execution.",
                        severity=FindingSeverity.HIGH,
                        confidence=0.85,
                        evidence_items=[evidence[-1]],
                    )
                )

    if pipeline_signals:
        for cat, sig in pipeline_signals[:5]:
            findings.append(
                SpecialistFinding(
                    category=cat,
                    description=f"Pipeline step failure observed: {sig}",
                    severity=FindingSeverity.HIGH,
                    confidence=0.80,
                    evidence_items=[item for item in evidence if item.snippet == sig],
                )
            )

    summary = (
        f"CI/CD Agent inspected {len(workflow_files)} workflow files and identified "
        f"{len(pipeline_signals)} pipeline failure signals."
        if pipeline_signals or workflow_files
        else "No live CI/CD pipeline failure or workflow definitions detected in log."
    )

    status = (
        AgentExecutionStatus.COMPLETED
        if (findings or workflow_files)
        else AgentExecutionStatus.INSUFFICIENT_DATA
    )

    return AgentOutput(
        agent_name="CI/CD Investigation Agent",
        status=status,
        summary=summary,
        findings=findings,
        supporting_evidence=evidence,
        confidence_estimate=0.8 if findings else 0.3,
        unresolved_questions=(
            ["Live GitHub Actions webhook/run logs not connected; inspected static workflow definitions and supplied logs."]
            if not integration_status["live_cicd_available"]
            else []
        ),
        recommended_next_steps=[
            "Verify the build/test commands defined in .github/workflows match the repo scripts."
        ] if findings else [],
        integration_status=integration_status,
    )
