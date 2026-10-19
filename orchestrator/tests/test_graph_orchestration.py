import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph import build_graph
from schemas import IncidentReport


def test_graph_full_execution_bounded():
    sample_log = """
    2026-10-19 10:00:01 INFO Starting deployment
    2026-10-19 10:00:02 ERROR ValueError: Database URL is null — connection failed
    2026-10-19 10:00:03 Traceback (most recent call last):
      File "sample_app/db_config.py", line 8, in connect
        raise ValueError("Database URL is null — connection failed")
    """

    copilot_graph = build_graph()
    result = copilot_graph.invoke({
        "repo_name": "konduri-lakshmi-prasanna/Ai_Engineering_Copilot",
        "log_text": sample_log,
        "github_token": "",
        "max_rounds": 2,
    })

    assert "incident_id" in result
    assert "agent_outputs" in result
    assert "github" in result["agent_outputs"]
    assert "logs" in result["agent_outputs"]
    assert "cicd" in result["agent_outputs"]
    assert "infra" in result["agent_outputs"]
    assert "docs" in result["agent_outputs"]
    assert "verification" in result
    assert "final_report" in result

    # Check that bounded retry loop did not exceed max_rounds
    assert result.get("investigation_round", 1) <= 2

    # Check that final report is populated and has confirmed facts
    report_data = result["final_report"]
    assert report_data["repo"] == "konduri-lakshmi-prasanna/Ai_Engineering_Copilot"
    assert len(report_data["confirmed_facts"]) > 0
    assert len(report_data["supporting_evidence"]) > 0


def test_graph_insufficient_evidence_honest_reporting():
    # A vague log with no identifiable error
    vague_log = "2026-10-19 10:00:01 INFO System running normally"

    copilot_graph = build_graph()
    result = copilot_graph.invoke({
        "repo_name": "test/repo",
        "log_text": vague_log,
        "max_rounds": 1,
    })

    assert "final_report" in result
    report = result["final_report"]
    # The system should not invent errors when none are present
    assert result["agent_outputs"]["logs"]["status"] == "INSUFFICIENT_DATA"
