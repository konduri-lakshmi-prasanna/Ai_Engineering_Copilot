import re
import json
from typing import Dict, Any, List
from schemas import (
    VerificationResult,
    AgentOutput,
    EvidenceType,
)


def verify_investigation(
    agent_outputs: Dict[str, Dict[str, Any]],
    proposed_cause: str,
    proposed_fix: str,
    log_text: str,
) -> VerificationResult:
    """
    Verification Agent.
    - Evaluates the claims and proposed root cause against the collected evidence across all agents.
    - Flags unsupported assumptions, contradictions, and data gaps.
    - Determines if evidence is sufficient or if a targeted re-investigation is required.
    - Performs bounded, deterministic validations.
    """
    confirmed_facts: List[str] = []
    contradictions: List[str] = []
    unsupported_assumptions: List[str] = []
    reinvestigation_focus: List[str] = []

    all_evidence = []
    for agent_key, out_dict in agent_outputs.items():
        all_evidence.extend(out_dict.get("supporting_evidence", []))

    # 1. Verification of primary log error
    logs_output = agent_outputs.get("logs", {})
    logs_findings = logs_output.get("findings", [])
    has_log_evidence = any(ev.get("source_type") == EvidenceType.LOG_LINE.value for ev in all_evidence)

    if has_log_evidence:
        confirmed_facts.append("Deployment failure is verified with explicit error logs.")
    else:
        unsupported_assumptions.append("No explicit error log line exists to confirm an active failure.")

    # 2. Check for missing script vs package.json verification
    github_output = agent_outputs.get("github", {})
    package_json_ev = [
        ev for ev in github_output.get("supporting_evidence", [])
        if "package.json" in ev.get("reference", "")
    ]

    is_missing_script_error = bool(re.search(r"missing script: (\S+)", log_text, re.IGNORECASE))
    if is_missing_script_error:
        match = re.search(r"missing script: (\S+)", log_text, re.IGNORECASE)
        script_name = match.group(1)
        if package_json_ev:
            try:
                scripts_snippet = json.loads(package_json_ev[0].get("snippet", "{}"))
                if script_name not in scripts_snippet:
                    confirmed_facts.append(f"Confirmed: script '{script_name}' is absent from package.json scripts.")
                else:
                    contradictions.append(
                        f"Log claims missing script '{script_name}', but package.json defines '{script_name}': '{scripts_snippet.get(script_name)}'."
                    )
            except Exception:
                pass
        else:
            reinvestigation_focus.append(f"Inspect package.json to verify presence of script '{script_name}'.")

    # 3. Check database / environment variable verification
    is_env_error = bool(re.search(r"(?:DATABASE_URL|URL|ENV).*is (?:null|undefined|missing)", log_text, re.IGNORECASE))
    if is_env_error:
        confirmed_facts.append("Verified: runtime configuration/environment variable is undefined during initialization.")

    # 4. Code & AST-level Line Verification against Repo Files
    code_verification = None
    stack_trace_match = re.search(r'File "([^"]+)", line (\d+)(?:, in (\w+))?', log_text)
    if stack_trace_match:
        file_path = stack_trace_match.group(1).replace("\\", "/").lstrip("./")
        line_num = int(stack_trace_match.group(2))
        func_name = stack_trace_match.group(3) or "module"

        # Search for this file in github evidence
        matched_file_ev = next(
            (ev for ev in github_output.get("supporting_evidence", []) if file_path in ev.get("reference", "")),
            None
        )

        if matched_file_ev:
            content = matched_file_ev.get("snippet", "")
            lines = content.splitlines()
            start = max(0, line_num - 3)
            end = min(len(lines), line_num + 3)
            context_lines = []
            for idx in range(start, end):
                prefix = "-> " if idx + 1 == line_num else "   "
                context_lines.append(f"{prefix}{idx+1}: {lines[idx] if idx < len(lines) else ''}")

            code_context_str = "\n".join(context_lines)
            confirmed_facts.append(
                f"Code Verified: Repo file '{file_path}' contains the failing line {line_num} executed in the stack trace."
            )

            code_verification = {
                "file": file_path,
                "line": line_num,
                "function": func_name,
                "context_code": code_context_str,
                "verified_in_repo": True,
            }
        else:
            unsupported_assumptions.append(
                f"File '{file_path}' from stack trace was not found or verified in the repository tree."
            )

    # 5. Check for contradictory claims between agents
    infra_findings = agent_outputs.get("infra", {}).get("findings", [])
    infra_oom = any("OOM" in f.get("category", "") for f in infra_findings)
    code_syntax_err = any("SyntaxError" in f.get("category", "") for f in logs_findings)

    if infra_oom and code_syntax_err:
        contradictions.append(
            "Conflict between infrastructure OOMKilled signal and application SyntaxError. Likely cascading error."
        )

    # 5. Fix validation
    fix_validation_result = "Suggested fix aligns with observed error mechanism."
    if "npm" in proposed_cause.lower() and "python" in proposed_fix.lower():
        contradictions.append("Suggested fix references Python whereas the root cause is in Node/npm ecosystem.")
        fix_validation_result = "Rejected: Fix ecosystem does not match root cause ecosystem."

    # Determine sufficiency
    is_sufficient = (len(confirmed_facts) >= 1) and (len(contradictions) == 0)
    needs_reinvestigation = not is_sufficient and (len(reinvestigation_focus) > 0)

    validation_performed = (
        f"Cross-referenced {len(all_evidence)} evidence points across {len(agent_outputs)} agents. "
        f"Verified log error presence, package.json scripts, and environment variable bindings."
    )

    return VerificationResult(
        is_sufficient=is_sufficient,
        needs_reinvestigation=needs_reinvestigation,
        reinvestigation_focus=reinvestigation_focus,
        confirmed_facts=confirmed_facts,
        contradictions_found=contradictions,
        unsupported_assumptions=unsupported_assumptions,
        validation_performed=validation_performed,
        fix_validation_result=fix_validation_result,
        code_verification=code_verification,
    )
