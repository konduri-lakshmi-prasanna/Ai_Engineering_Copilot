import os
import sys
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas import (
    AgentExecutionStatus,
    EvidenceType,
    FindingSeverity,
    AgentOutput,
    VerificationResult,
)
from agents.logs_agent import logs_agent
from agents.log_parser import extract_file_paths
from agents.cicd_agent import cicd_agent
from agents.infra_agent import infra_agent
from agents.docs_rag_agent import knowledge_agent, docs_rag_agent
from agents.verification_agent import verify_investigation
from agents.orchestrator_agent import plan_investigation, synthesize_final_report


def test_extract_file_paths():
    log = """
    Traceback (most recent call last):
      File "sample_app/db_config.py", line 12, in connect
        raise ConnectionError("DB offline")
      File "/usr/lib/python3.11/site-packages/urllib3/poolmanager.py", line 400, in urlopen
        pass
    """
    paths = extract_file_paths(log)
    assert "sample_app/db_config.py" in paths
    # site-packages must be excluded
    assert not any("site-packages" in p for p in paths)


def test_logs_agent_primary_vs_secondary():
    sample_log = """
    2026-10-19 10:00:01 INFO Starting deployment
    2026-10-19 10:00:02 ERROR ValueError: Database URL is null — connection failed
    2026-10-19 10:00:03 Traceback (most recent call last):
      File "sample_app/db_config.py", line 8, in connect
        raise ValueError("Database URL is null")
    2026-10-19 10:00:04 ERROR Rolling back deployment due to failure
    """
    out = logs_agent(sample_log)
    assert isinstance(out, AgentOutput)
    assert out.status == AgentExecutionStatus.COMPLETED
    assert len(out.findings) >= 1
    # Check primary error detection
    categories = [f.category for f in out.findings]
    assert "ValueError" in categories or "Application Runtime Error" in categories
    # Check evidence attribution
    assert any(ev.source_type == EvidenceType.LOG_LINE for ev in out.supporting_evidence)


def test_cicd_agent_signals():
    log = """
    npm run build failed with exit code 1
    Process completed with exit code 1
    """
    out = cicd_agent("org/repo", log, token=None)
    assert isinstance(out, AgentOutput)
    assert out.status == AgentExecutionStatus.COMPLETED
    assert any("Build Step Failure" in f.category for f in out.findings)
    assert any(ev.source_type == EvidenceType.CICD_STEP for ev in out.supporting_evidence)


def test_infra_agent_signals():
    log = """
    Container backend failed: CrashLoopBackOff
    standard_init_linux.go:228: exec user process caused: no such file or directory
    """
    out = infra_agent("org/repo", log, token=None)
    assert isinstance(out, AgentOutput)
    assert out.status == AgentExecutionStatus.COMPLETED
    categories = [f.category for f in out.findings]
    assert any("Container Lifecycle" in c for c in categories)


def test_infra_agent_docker_build_failure():
    log = """
    Step 4/10 : COPY package.json ./
    COPY failed: stat package.json: file does not exist
    failed to solve with frontend dockerfile.v0
    """
    out = infra_agent("org/repo", log, token=None)
    assert isinstance(out, AgentOutput)
    assert out.status == AgentExecutionStatus.COMPLETED
    categories = [f.category for f in out.findings]
    assert any("Docker Build Context" in c or "Docker Build Step Failure" in c for c in categories)
    assert any(ev.source_type == EvidenceType.INFRA_EVENT for ev in out.supporting_evidence)


def test_knowledge_agent_retrieval():
    out = knowledge_agent("cors header missing access-control-allow-origin", top_k=2)
    assert isinstance(out, AgentOutput)
    if out.findings:
        assert any(ev.source_type == EvidenceType.DOCUMENTATION for ev in out.supporting_evidence)
        assert out.status == AgentExecutionStatus.COMPLETED
    else:
        assert out.status == AgentExecutionStatus.INSUFFICIENT_DATA


def test_verification_agent_contradiction_detection():
    agent_outputs = {
        "logs": {
            "findings": [{"category": "SyntaxError", "description": "Invalid syntax"}],
            "supporting_evidence": [{"source_type": "log_line", "reference": "log:1", "snippet": "SyntaxError"}],
        },
        "infra": {
            "findings": [{"category": "Resource Limits OOMKilled", "description": "Killed by OOM"}],
            "supporting_evidence": [],
        },
    }
    ver = verify_investigation(
        agent_outputs=agent_outputs,
        proposed_cause="npm script error",
        proposed_fix="pip install flask",
        log_text="SyntaxError: invalid syntax",
    )
    assert isinstance(ver, VerificationResult)
    # Must flag contradiction between Python fix and npm root cause
    assert len(ver.contradictions_found) > 0


def test_orchestrator_planning():
    plan = plan_investigation("acme/service", "OOMKilled exit code 137 in container")
    assert "infra" in plan.required_specialists
    assert "github" in plan.required_specialists
    assert "logs" in plan.required_specialists
