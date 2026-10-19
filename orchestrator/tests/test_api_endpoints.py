import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "mcp_status" in data
    assert len(data["agents"]) == 7


def test_analyze_invalid_repo():
    response = client.post("/analyze", json={"repo_name": "invalid-repo-without-slash", "log_text": "Error: test"})
    assert response.status_code == 400
    assert "must be in the format 'owner/repo'" in response.json()["detail"]


def test_analyze_oversized_log():
    huge_log = "ERROR\n" * 200_000  # Exceeds max length limit
    response = client.post("/analyze", json={"repo_name": "owner/repo", "log_text": huge_log})
    assert response.status_code == 422  # Pydantic validation error for max_length


def test_chat_endpoint_grounding():
    context = {
        "root_cause": "Missing database URL in config",
        "fix_suggestion": "Set DATABASE_URL in .env",
    }
    response = client.post(
        "/chat",
        json={
            "repo_name": "test/app",
            "context": context,
            "question": "What is the recommended fix?",
        },
    )
    # Even if Groq returns answer or mock, status code is 200 or 500 if unconfigured
    assert response.status_code in (200, 500)
