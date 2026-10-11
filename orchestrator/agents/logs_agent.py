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
from agents.log_parser import extract_file_paths


def logs_agent(log_text: str) -> AgentOutput:
    """
    Log Analysis Agent.
    - Parses deployment logs and application stack traces deterministically.
    - Extracts error lines, exception types, and file locations.
    - Distinguishes primary root errors from cascading/secondary errors.
    - Generates evidence-backed hypotheses without treating every warning as a root cause.
    """
    lines = log_text.splitlines()
    error_lines = [
        (idx + 1, line)
        for idx, line in enumerate(lines)
        if re.search(r"(error|exception|fail|traceback|fatal|panic|err:)", line, re.IGNORECASE)
    ]

    evidence: List[EvidenceItem] = []
    findings: List[SpecialistFinding] = []

    # 1. Deterministic extraction of stack traces and file paths
    extracted_paths = extract_file_paths(log_text, max_files=8)

    # 2. Extract top error lines as concrete evidence
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

    # 3. Create structured findings
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
                        reference=f"stack_trace:paths",
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

    status = AgentExecutionStatus.COMPLETED if error_lines else AgentExecutionStatus.INSUFFICIENT_DATA

    return AgentOutput(
        agent_name="Log Analysis Agent",
        status=status,
        summary=summary,
        findings=findings,
        supporting_evidence=evidence,
        confidence_estimate=0.9 if primary_error_line else 0.2,
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
        },
    )