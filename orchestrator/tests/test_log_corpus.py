"""
Phase 11 Tests — Multi-fixture log corpus: Kubernetes CrashLoop, OOMKilled, and npm build failure.
Tests the enhanced log_parser.detect_error_type() and the upgraded logs_agent findings.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.log_parser import detect_error_type, extract_file_paths
from agents.logs_agent import logs_agent
from schemas import AgentExecutionStatus, EvidenceType, FindingSeverity


# ── Sample log fixtures (inline, mirrors sample_app/*.log) ─────────────────

K8S_CRASHLOOP_LOG = """
2026-10-21T08:00:21Z ERROR [backend-api] Traceback (most recent call last):
2026-10-21T08:00:21Z ERROR [backend-api]   File "app/main.py", line 24, in startup
2026-10-21T08:00:21Z ERROR [backend-api]     db.connect(os.environ["DATABASE_URL"])
2026-10-21T08:00:21Z ERROR [backend-api] KeyError: 'DATABASE_URL'
2026-10-21T08:00:21Z INFO  Container backend-api exited with code 1
2026-10-21T08:00:31Z WARNING [k8s-event] pod/backend-api-78d9f4b6c-lmnop: CrashLoopBackOff
"""

K8S_OOM_LOG = """
2026-10-21T09:00:07Z INFO  [data-processor] Reading CSV batch_export_2026.csv (2.1 GB)
2026-10-21T09:01:17Z ERROR [data-processor] MemoryError: unable to allocate 134217728 bytes for array
2026-10-21T09:01:17Z ERROR [data-processor]   File "app/batch/processor.py", line 88, in load_dataset
2026-10-21T09:01:18Z INFO  [k8s-event] Container data-processor OOMKilled (exit code 137)
2026-10-21T09:01:18Z WARNING [k8s-event] pod data-processor-5f8c9d7b6-xyzab killed: OOMKilled
"""

NPM_BUILD_LOG = """
2026-10-21T11:02:10Z ERROR [CI] Failed to compile.
2026-10-21T11:02:10Z ERROR [CI] TypeScript error in src/components/Dashboard.tsx:
2026-10-21T11:02:10Z ERROR [CI]   src/components/Dashboard.tsx(142,23): error TS2345
2026-10-21T11:02:10Z ERROR [CI] npm ERR! code ELIFECYCLE
2026-10-21T11:02:10Z ERROR [CI] npm ERR! errno 1
2026-10-21T11:02:10Z ERROR [CI] npm ERR! frontend@1.2.0 build: `react-scripts build`
2026-10-21T11:02:10Z ERROR [CI] npm ERR! Exit status 1
2026-10-21T11:02:11Z ERROR [CI] Process completed with exit code 1
"""


# ── detect_error_type unit tests ───────────────────────────────────────────

def test_detect_crashloop():
    result = detect_error_type(K8S_CRASHLOOP_LOG)
    assert result["is_crashloop"] is True
    assert result["is_oom"] is False
    assert result["is_npm_failure"] is False
    # exit_codes is a list (may be empty if the log phrases it differently)
    assert isinstance(result["exit_codes"], list)


def test_detect_oomkilled():
    result = detect_error_type(K8S_OOM_LOG)
    assert result["is_oom"] is True
    assert result["is_crashloop"] is False
    assert 137 in result["exit_codes"]
    # pod name fragment should be extracted
    assert any("data-processor" in pod for pod in result["pod_names"])


def test_detect_npm_failure():
    result = detect_error_type(NPM_BUILD_LOG)
    assert result["is_npm_failure"] is True
    assert result["is_oom"] is False
    assert result["is_crashloop"] is False


def test_detect_clean_log():
    clean = "INFO Service started successfully on port 8000"
    result = detect_error_type(clean)
    assert result["is_oom"] is False
    assert result["is_crashloop"] is False
    assert result["is_npm_failure"] is False
    assert result["exit_codes"] == []


# ── logs_agent integration tests with new fixture logs ────────────────────

def test_logs_agent_crashloop_findings():
    out = logs_agent(K8S_CRASHLOOP_LOG)
    assert out.status == AgentExecutionStatus.COMPLETED
    categories = [f.category for f in out.findings]
    assert any("CrashLoopBackOff" in c for c in categories), f"Missing CrashLoopBackOff finding. Got: {categories}"
    # KeyError should also be detected
    assert any("KeyError" in c or "Application Runtime Error" in c for c in categories)


def test_logs_agent_oom_findings():
    out = logs_agent(K8S_OOM_LOG)
    assert out.status == AgentExecutionStatus.COMPLETED
    categories = [f.category for f in out.findings]
    assert any("OOMKilled" in c or "Memory" in c for c in categories), f"Missing OOM finding. Got: {categories}"
    # File from stack trace should be extracted
    assert any("processor.py" in ev.snippet or "processor.py" in ev.reference
               for ev in out.supporting_evidence)


def test_logs_agent_npm_findings():
    out = logs_agent(NPM_BUILD_LOG)
    assert out.status == AgentExecutionStatus.COMPLETED
    categories = [f.category for f in out.findings]
    assert any("npm" in c.lower() or "Build" in c for c in categories), f"Missing npm finding. Got: {categories}"
    # Summary should mention npm failure
    assert "npm" in out.summary.lower() or "npm" in str(out.integration_status)


def test_extract_file_paths_from_k8s_log():
    paths = extract_file_paths(K8S_CRASHLOOP_LOG)
    assert "app/main.py" in paths


def test_extract_file_paths_from_oom_log():
    paths = extract_file_paths(K8S_OOM_LOG)
    assert any("processor.py" in p for p in paths)


def test_logs_agent_summary_enrichment():
    """Verify the summary string contains detected signal names."""
    oom_out = logs_agent(K8S_OOM_LOG)
    assert "OOMKilled" in oom_out.summary

    cl_out = logs_agent(K8S_CRASHLOOP_LOG)
    assert "CrashLoopBackOff" in cl_out.summary

    npm_out = logs_agent(NPM_BUILD_LOG)
    assert "npm" in npm_out.summary.lower()
