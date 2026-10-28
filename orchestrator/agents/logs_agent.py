import os
import re
from typing import Dict, Any, List
from schemas import (
    AgentOutput,
    AgentExecutionStatus,
    SpecialistFinding,
    EvidenceItem,
    EvidenceType,
    FindingSeverity,
)
from agents.log_parser import extract_file_paths, detect_error_type


def logs_agent(log_text: str) -> AgentOutput:
    """
    Log Analysis Agent.
    - Parses deployment logs and application stack traces deterministically.
    - Extracts error lines, exception types, and file locations.
    - Distinguishes primary root errors from cascading/secondary errors.
    - Detects Kubernetes OOMKilled, CrashLoopBackOff, and npm build failures.
    - Generates evidence-backed hypotheses without treating every warning as a root cause.
    """
    lines = log_text.splitlines()
    error_lines = [
        (idx + 1, line)
        for idx, line in enumerate(lines)
        if re.search(r"(error|exception|fail|traceback|fatal|panic|err:|oomkilled|crashloop)", line, re.IGNORECASE)
    ]

    evidence: List[EvidenceItem] = []
    findings: List[SpecialistFinding] = []

    # 1. Deterministic extraction of stack traces and file paths
    extracted_paths = extract_file_paths(log_text, max_files=8)

    # 2. High-level error type detection (OOM, CrashLoop, npm, exit codes)
    error_type = detect_error_type(log_text)

    # 3. OOMKilled / CrashLoopBackOff findings
    if error_type["is_oom"]:
        exit_code_note = ""
        if 137 in error_type["exit_codes"]:
            exit_code_note = " (exit code 137 confirms OOM kill signal)"
        oom_ev = EvidenceItem(
            source_type=EvidenceType.LOG_LINE,
            reference="log:oom_signal",
            snippet=f"OOMKilled detected{exit_code_note}. Pod(s): {', '.join(error_type['pod_names']) or 'unknown'}",
            relevance="Kernel killed the container process due to memory limit breach",
        )
        evidence.append(oom_ev)
        findings.append(
            SpecialistFinding(
                category="OOMKilled — Memory Limit Exceeded",
                description=(
                    f"Container was killed by the OOM killer{exit_code_note}. "
                    "Root cause is likely a memory leak or insufficient resources.limits.memory."
                ),
                severity=FindingSeverity.CRITICAL,
                confidence=0.97,
                evidence_items=[oom_ev],
            )
        )

    if error_type["is_crashloop"]:
        cl_ev = EvidenceItem(
            source_type=EvidenceType.LOG_LINE,
            reference="log:crashloop_signal",
            snippet=f"CrashLoopBackOff detected. Pod(s): {', '.join(error_type['pod_names']) or 'unknown'}",
            relevance="Kubernetes keeps restarting the container because it exits repeatedly",
        )
        evidence.append(cl_ev)
        findings.append(
            SpecialistFinding(
                category="CrashLoopBackOff",
                description=(
                    "Pod is in CrashLoopBackOff. Container exits on every restart. "
                    "Check container exit code and logs from previous container instance."
                ),
                severity=FindingSeverity.CRITICAL,
                confidence=0.97,
                evidence_items=[cl_ev],
            )
        )

    if error_type["is_npm_failure"]:
        npm_ev = EvidenceItem(
            source_type=EvidenceType.LOG_LINE,
            reference="log:npm_failure",
            snippet="npm ERR! / ELIFECYCLE / Exit status detected — npm script failed.",
            relevance="CI/CD npm build or script step exited with non-zero status",
        )
        evidence.append(npm_ev)
        findings.append(
            SpecialistFinding(
                category="npm Build / Script Failure",
                description=(
                    "npm run script exited with error. Likely cause: TypeScript compile error, "
                    "missing env variable, or node version mismatch."
                ),
                severity=FindingSeverity.HIGH,
                confidence=0.93,
                evidence_items=[npm_ev],
            )
        )

    # 4. Extract top error lines as concrete evidence
    primary_error_line = None
    cascading_error_lines = []

    for line_no, line_content in error_lines[:15]:
        ev = EvidenceItem(
            source_type=EvidenceType.LOG_LINE,
            reference=f"log:line-{line_no}",
            snippet=line_content.strip()[:300],
            relevance="Deployment log error signature",
        )
        evidence.append(ev)

        # Distinguish primary error: usually the first explicit Exception or fatal error
        if not primary_error_line and re.search(r"(exception|fatal|panic|error:)", line_content, re.IGNORECASE):
            primary_error_line = (line_no, line_content)
        else:
            cascading_error_lines.append((line_no, line_content))

    # 5. Create structured findings for stack trace errors
    if primary_error_line:
        line_no, line_content = primary_error_line
        # Detect exception type
        exc_match = re.search(r"([A-Za-z0-9_]+(?:Error|Exception)):(.*)", line_content)
        category = exc_match.group(1) if exc_match else "Application Runtime Error"
        desc = exc_match.group(2).strip() if exc_match else line_content.strip()

        findings.append(
            SpecialistFinding(
                category=category,
                description=f"Primary error identified at line {line_no}: {desc}",
                severity=FindingSeverity.CRITICAL,
                confidence=0.92,
                evidence_items=[item for item in evidence if f"line-{line_no}" in item.reference],
            )
        )

    if cascading_error_lines:
        findings.append(
            SpecialistFinding(
                category="Cascading / Secondary Failures",
                description=f"Identified {len(cascading_error_lines)} subsequent downstream errors or rollback notifications triggered after the primary failure.",
                severity=FindingSeverity.MEDIUM,
                confidence=0.75,
                evidence_items=[
                    item for item in evidence
                    if any(f"line-{lno}" in item.reference for lno, _ in cascading_error_lines[:3])
                ],
            )
        )

    if extracted_paths:
        findings.append(
            SpecialistFinding(
                category="Implicated Code Locations",
                description=f"Stack trace directly implicates source files: {', '.join(extracted_paths)}",
                severity=FindingSeverity.HIGH,
                confidence=0.95,
                evidence_items=[
                    EvidenceItem(
                        source_type=EvidenceType.LOG_LINE,
                        reference="stack_trace:paths",
                        snippet=", ".join(extracted_paths),
                        relevance="Files referenced directly in exception stack frames",
                    )
                ],
            )
        )

    summary = (
        f"Log Analysis Agent processed {len(lines)} lines, isolating {len(error_lines)} error signals. "
        f"Identified primary error and {len(extracted_paths)} implicated source files."
        if error_lines
        else "Log Analysis Agent processed log text but found no explicit error keywords or stack traces."
    )

    # Enrich summary with K8s specifics
    k8s_tags = []
    if error_type["is_oom"]:
        k8s_tags.append("OOMKilled")
    if error_type["is_crashloop"]:
        k8s_tags.append("CrashLoopBackOff")
    if error_type["is_npm_failure"]:
        k8s_tags.append("npm build failure")
    if k8s_tags:
        summary += f" Detected signals: {', '.join(k8s_tags)}."

    status = AgentExecutionStatus.COMPLETED if (error_lines or findings) else AgentExecutionStatus.INSUFFICIENT_DATA

    return AgentOutput(
        agent_name="Log Analysis Agent",
        status=status,
        summary=summary,
        findings=findings,
        supporting_evidence=evidence,
        confidence_estimate=0.9 if primary_error_line or findings else 0.2,
        unresolved_questions=(
            ["Some log lines truncated in snippet; full context may contain earlier warnings."]
            if len(lines) > 500
            else []
        ),
        recommended_next_steps=[
            f"Correlate implicated files ({', '.join(extracted_paths)}) with GitHub repository state."
        ] if extracted_paths else [],
        integration_status={
            "total_lines": len(lines),
            "errors_found": len(error_lines),
            "paths_extracted": extracted_paths,
            "error_type": error_type,
        },
    )