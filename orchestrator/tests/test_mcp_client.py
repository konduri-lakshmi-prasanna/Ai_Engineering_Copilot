import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_clients.github_mcp_client import GitHubMCPClient


def test_mcp_client_fallback_when_disabled():
    # When MCP is disabled, it should report available=False and provide clean fallback status
    client = GitHubMCPClient()
    client.enabled = False

    assert client.is_available is False
    status = client.get_status()
    assert status["mcp_enabled"] is False
    assert status["mode"] == "Direct_API_Fallback"


def test_mcp_client_read_only_status():
    client = GitHubMCPClient(token="mock-token")
    client.enabled = True
    assert client.is_available is True
    status = client.get_status()
    assert status["mcp_configured"] is True
