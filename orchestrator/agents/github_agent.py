import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from github import Github, GithubException, Auth
from dotenv import load_dotenv

from schemas import (
    AgentOutput,
    AgentExecutionStatus,
    SpecialistFinding,
    EvidenceItem,
    EvidenceType,
    FindingSeverity,
)
from mcp_clients.github_mcp_client import GitHubMCPClient

load_dotenv()


def _get_repo(repo_name: str, token: Optional[str] = None):
    token = token or os.getenv("GITHUB_TOKEN")
    if token:
        gh = Github(auth=Auth.Token(token))
    else:
        gh = Github()
    return gh.get_repo(repo_name)


def fetch_package_json(repo_name: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    token = token or os.getenv("GITHUB_TOKEN")
    candidate_paths = [
        "package.json",
        "frontend/package.json",
        "client/package.json",
        "web/package.json",
        "app/package.json",
    ]

    try:
        repo = _get_repo(repo_name, token)
        for path in candidate_paths:
            try:
                content_file = repo.get_contents(path)
                pkg = json.loads(content_file.decoded_content.decode("utf-8"))
                return {
                    "found_at": path,
                    "scripts": pkg.get("scripts", {}),
                    "name": pkg.get("name"),
                }
            except Exception:
                continue
    except Exception:
        pass

    return None


def github_agent_targeted(repo_name: str, file_paths: list, commits_per_file: int = 5, token: Optional[str] = None) -> dict:
    repo = _get_repo(repo_name, token)
    result = {"repo": repo_name, "files": []}

    for path in file_paths:
        file_entry = {"path": path, "current_content": None, "commits": [], "found": False}
        try:
            content_file = repo.get_contents(path)
            raw = content_file.decoded_content.decode("utf-8", errors="replace")
            file_entry["current_content"] = raw[:3000]
            file_entry["found"] = True
        except Exception:
            file_entry["error"] = (
                "File not found at this exact path in the repo — it may have "
                "moved, or the path in the log doesn't match the repo layout."
            )

        try:
            commits = repo.get_commits(path=path)[:commits_per_file]
            for c in commits:
                patch = None
                for f in c.files:
                    if f.filename == path:
                        patch = f.patch[:600] if f.patch else None
                        break
                file_entry["commits"].append({
                    "sha": c.sha[:7],
                    "message": c.commit.message[:200],
                    "date": str(c.commit.author.date),
                    "patch": patch,
                })
        except Exception:
            pass

        result["files"].append(file_entry)

    return result


def github_agent_recent(repo_name: str, limit: int = 8, token: Optional[str] = None) -> dict:
    repo = _get_repo(repo_name, token)
    commits = repo.get_commits()[:limit]

    result = {"repo": repo_name, "commits": []}
    for c in commits:
        files = []
        for f in c.files[:3]:
            files.append({
                "filename": f.filename,
                "status": f.status,
                "patch": f.patch[:250] if f.patch else None,
            })

        result["commits"].append({
            "sha": c.sha[:7],
            "message": c.commit.message,
            "author": c.commit.author.name,
            "date": str(c.commit.author.date),
            "files": files,
        })
    return result


# Alias for backward compatibility
github_agent = github_agent_recent


def run_github_investigation(
    repo_name: str,
    file_paths: Optional[List[str]] = None,
    token: Optional[str] = None,
    mcp_client: Optional[GitHubMCPClient] = None,
) -> AgentOutput:
    """
    Main entry point for GitHub Code Investigation Agent returning standardized AgentOutput.
    Correlates stack trace file paths with repository contents and commit history.
    Uses MCP Client if configured, or PyGithub API with graceful fallback.
    """
    evidence: List[EvidenceItem] = []
    findings: List[SpecialistFinding] = []
    token = token or os.getenv("GITHUB_TOKEN")
    client_mcp = mcp_client or GitHubMCPClient(token=token)

    integration_status = client_mcp.get_status()

    # Check package.json scripts (common root cause in JS projects)
    pkg_data = fetch_package_json(repo_name, token=token)
    if pkg_data:
        ev = EvidenceItem(
            source_type=EvidenceType.GITHUB_CODE,
            reference=f"{pkg_data['found_at']}:scripts",
            snippet=json.dumps(pkg_data.get("scripts", {}), indent=2),
            relevance=f"Package scripts defined in {pkg_data['found_at']}",
        )
        evidence.append(ev)
        findings.append(
            SpecialistFinding(
                category="Package Scripts Configuration",
                description=f"Repository defines scripts: {list(pkg_data.get('scripts', {}).keys())} in {pkg_data['found_at']}",
                severity=FindingSeverity.INFO,
                confidence=1.0,
                evidence_items=[ev],
            )
        )

    # If targeted files are provided from logs
    if file_paths:
        mode = "targeted"
        try:
            targeted_data = github_agent_targeted(repo_name, file_paths, commits_per_file=3, token=token)
            for f in targeted_data["files"]:
                if f["found"] and f["current_content"]:
                    ev = EvidenceItem(
                        source_type=EvidenceType.GITHUB_CODE,
                        reference=f"{f['path']}",
                        snippet=f["current_content"][:400],
                        relevance=f"Source content of implicated file {f['path']}",
                    )
                    evidence.append(ev)

                for c in f.get("commits", []):
                    c_ev = EvidenceItem(
                        source_type=EvidenceType.GITHUB_COMMIT,
                        reference=f"commit:{c['sha']} ({f['path']})",
                        snippet=f"Message: {c['message']}\nPatch: {c.get('patch', '') or 'N/A'}"[:400],
                        relevance=f"Recent commit modifying implicated file {f['path']}",
                    )
                    evidence.append(c_ev)
                    findings.append(
                        SpecialistFinding(
                            category="Recent File Modification",
                            description=f"Commit {c['sha']} modified {f['path']}: {c['message']}",
                            severity=FindingSeverity.HIGH,
                            confidence=0.85,
                            evidence_items=[c_ev],
                        )
                    )
        except Exception as e:
            integration_status["error"] = str(e)
    else:
        mode = "recent"
        try:
            recent_data = github_agent_recent(repo_name, limit=5, token=token)
            for c in recent_data["commits"]:
                ev = EvidenceItem(
                    source_type=EvidenceType.GITHUB_COMMIT,
                    reference=f"commit:{c['sha']}",
                    snippet=f"{c['message']} by {c['author']}"[:300],
                    relevance="Recent repository commit",
                )
                evidence.append(ev)
                findings.append(
                    SpecialistFinding(
                        category="Recent Repository Change",
                        description=f"Commit {c['sha']} by {c['author']}: {c['message']}",
                        severity=FindingSeverity.MEDIUM,
                        confidence=0.70,
                        evidence_items=[ev],
                    )
                )
        except Exception as e:
            integration_status["error"] = str(e)

    summary = (
        f"GitHub Code Investigation Agent inspected repository in {mode} mode. "
        f"Gathered {len(evidence)} evidence items across commits and manifests."
    )

    status = (
        AgentExecutionStatus.COMPLETED
        if evidence
        else (AgentExecutionStatus.FAILED if "error" in integration_status else AgentExecutionStatus.INSUFFICIENT_DATA)
    )

    return AgentOutput(
        agent_name="GitHub Code Investigation Agent",
        status=status,
        summary=summary,
        findings=findings,
        supporting_evidence=evidence,
        confidence_estimate=0.88 if evidence else 0.3,
        unresolved_questions=[] if evidence else ["Unable to retrieve repo data; verify token permissions."],
        recommended_next_steps=["Correlate implicated commit changes with error stack trace line numbers."],
        integration_status=integration_status,
        error_message=integration_status.get("error"),
    )