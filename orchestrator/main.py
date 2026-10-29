import os
import re
import json
import httpx
import traceback
import asyncio
from typing import Optional, Dict, Any
from github import GithubException
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graph import build_graph
from auth import router as auth_router
from llm_client import ask_groq
from mcp_clients.github_mcp_client import GitHubMCPClient

app = FastAPI(
    title="AI Engineering Copilot - Multi-Agent System",
    description="Multi-agent deployment failure investigation copilot coordinated via LangGraph.",
    version="2.0.0",
)

# Configurable CORS origins with secure defaults
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173")
allowed_origins = [orig.strip() for orig in cors_origins_env.split(",") if orig.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

copilot_graph = build_graph()

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_LOG_SIZE_CHARS = 500_000  # 500 KB character limit


class AnalyzeRequest(BaseModel):
    repo_name: str = Field(..., description="Format: owner/repo, e.g. facebook/react")
    log_text: str = Field(..., min_length=1, max_length=MAX_LOG_SIZE_CHARS)
    github_token: Optional[str] = Field(None, description="User OAuth token (optional)")


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    repo_name = request.repo_name.strip()

    if not REPO_PATTERN.match(repo_name):
        raise HTTPException(
            status_code=400,
            detail="repo_name must be in the format 'owner/repo', e.g. facebook/react",
        )

    try:
        result = copilot_graph.invoke({
            "repo_name": repo_name,
            "log_text": request.log_text,
            "github_token": request.github_token or "",
        })
    except GithubException as e:
        gh_msg = (e.data or {}).get("message", "") if isinstance(e.data, dict) else str(e.data)
        if e.status == 404:
            raise HTTPException(
                status_code=404,
                detail=f"GitHub returned 404 for '{repo_name}' ({gh_msg}). Repo is private or inaccessible.",
            )
        if e.status == 401:
            raise HTTPException(status_code=401, detail="GitHub token is invalid or expired.")
        if e.status == 403:
            raise HTTPException(status_code=429, detail=f"GitHub rate limit or forbidden: {gh_msg}")
        raise HTTPException(status_code=502, detail=f"GitHub API error {e.status}: {gh_msg}")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed ({type(e).__name__}): {e}")

    final_report = result.get("final_report", {})
    agent_outputs = result.get("agent_outputs", {})
    verification = result.get("verification", {})

    return {
        "repo": repo_name,
        "incident_id": result.get("incident_id"),
        "investigation_rounds": result.get("investigation_round", 1),
        "root_cause": result.get("root_cause", ""),
        "fix_suggestion": result.get("fix_suggestion", ""),
        "why_it_works": result.get("why_it_works", ""),
        "beginner_explanation": result.get("beginner_explanation", ""),
        "interview_questions": result.get("interview_questions", []),
        "documentation_links": result.get("documentation_links", []),
        "implicated_commits": result.get("implicated_commits", []),
        "errors_found": result.get("logs_data", {}).get("error_count", 0),
        "commits_scanned": len(result.get("implicated_commits", [])),
        "scan_mode": result.get("github_data", {}).get("mode", "targeted"),
        "agent_outputs": agent_outputs,
        "verification": verification,
        "final_report": final_report,
        "events": result.get("events", []),
    }


@app.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    """
    Streaming analysis endpoint sending Server-Sent Events (SSE)
    as individual specialist agents execute.
    """
    repo_name = request.repo_name.strip()
    if not REPO_PATTERN.match(repo_name):
        raise HTTPException(status_code=400, detail="Invalid repo_name format.")

    async def event_generator():
        initial_state = {
            "repo_name": repo_name,
            "log_text": request.log_text,
            "github_token": request.github_token or "",
            "events": [],
        }

        yield f"data: {json.dumps({'type': 'start', 'message': 'Multi-agent investigation initiated'})}\n\n"
        await asyncio.sleep(0.05)

        # Run graph in threadpool so it doesn't block async event loop
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, copilot_graph.invoke, initial_state)
            events = result.get("events", [])
            for event in events:
                yield f"data: {json.dumps({'type': 'agent_event', 'event': event})}\n\n"
                await asyncio.sleep(0.05)

            payload = {
                "type": "completed",
                "repo": repo_name,
                "incident_id": result.get("incident_id"),
                "root_cause": result.get("root_cause", ""),
                "fix_suggestion": result.get("fix_suggestion", ""),
                "why_it_works": result.get("why_it_works", ""),
                "beginner_explanation": result.get("beginner_explanation", ""),
                "interview_questions": result.get("interview_questions", []),
                "documentation_links": result.get("documentation_links", []),
                "implicated_commits": result.get("implicated_commits", []),
                "agent_outputs": result.get("agent_outputs", {}),
                "verification": result.get("verification", {}),
                "final_report": result.get("final_report", {}),
            }
            yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class ChatRequest(BaseModel):
    repo_name: str
    context: Dict[str, Any]
    question: str


@app.post("/chat")
def chat(request: ChatRequest):
    """
    Handles follow-up questions using the full multi-agent investigation context.
    """
    context_json = json.dumps(request.context, indent=2)

    prompt = f"""
You are the AI Engineering Copilot. You previously performed a comprehensive multi-agent investigation
for repository {request.repo_name}.

Below is the verified multi-agent investigation context (findings, verified evidence, root cause, suggested fix):
{context_json}

The engineer asks a follow-up question:
"{request.question}"

Answer directly, practically, and accurately based on the verified evidence above.
- If asked for code, configuration, or commands, provide exact, copy-pasteable instructions.
- If the question requires information that was not verified or was unavailable in the logs, state so honestly.
"""
    try:
        answer = ask_groq(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

    return {"answer": answer}


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _resolve_to_username(identifier: str, client: httpx.AsyncClient, headers: dict) -> str:
    identifier = identifier.strip()
    if "@" in identifier:
        if not EMAIL_PATTERN.match(identifier):
            raise HTTPException(status_code=400, detail="Enter a valid email address")

        search_response = await client.get(
            "https://api.github.com/search/users",
            headers=headers,
            params={"q": f"{identifier} in:email"},
        )
        if search_response.status_code == 403:
            raise HTTPException(status_code=429, detail="GitHub API rate limit hit")
        if search_response.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to search GitHub for that email")

        items = search_response.json().get("items", [])
        if not items:
            raise HTTPException(
                status_code=404,
                detail=f"No public GitHub profile found for '{identifier}'. Try their username instead.",
            )
        return items[0]["login"]

    if not USERNAME_PATTERN.match(identifier):
        raise HTTPException(status_code=400, detail="Enter a valid GitHub username or email")
    return identifier


@app.get("/github/repos")
async def list_user_repos(username: str):
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    repos = []
    async with httpx.AsyncClient() as client:
        resolved_username = await _resolve_to_username(username, client, headers)
        page = 1
        while True:
            response = await client.get(
                f"https://api.github.com/users/{resolved_username}/repos",
                headers=headers,
                params={"sort": "updated", "per_page": 100, "page": page},
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"GitHub user '{resolved_username}' not found")
            if response.status_code == 403:
                raise HTTPException(status_code=429, detail="GitHub API rate limit hit")
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch repositories")

            batch = response.json()
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1

    return {
        "username": resolved_username,
        "repos": [
            {
                "full_name": r["full_name"],
                "private": r["private"],
                "updated_at": r["updated_at"],
                "description": r.get("description"),
            }
            for r in repos
        ],
    }


@app.get("/github/repo/inspect")
async def inspect_repo(repo_name: str, token: Optional[str] = None):
    """
    Scans and summarizes the connected repository's code, structure,
    manifests, scripts, and recent commits upon repository selection.
    """
    repo_name = repo_name.strip()
    if not REPO_PATTERN.match(repo_name):
        raise HTTPException(status_code=400, detail="Invalid repo_name format.")

    from agents.github_agent import inspect_repository
    return inspect_repository(repo_name, token=token)


FILE_PATH_PATTERN = re.compile(r"^[\w./\-][\w./\- ]*$")
MAX_FILE_SIZE_CHARS = 50_000   # 50 KB — enough for source, not a full dump


@app.get("/github/repo/code")
async def fetch_file_code(repo_name: str, file_path: str, token: Optional[str] = None):
    """
    Fetches the raw content of a single file from the selected repository.
    Used by the frontend Code Viewer panel to display actual source code
    alongside the multi-agent investigation report.

    Returns:
      - repo:      the repo name
      - file_path: the requested path
      - content:   raw file text (truncated to 50 KB if very large)
      - truncated: bool — True when the response was cut
      - language:  language hint inferred from the file extension
    """
    repo_name = repo_name.strip()
    file_path = file_path.strip().lstrip("/")

    if not REPO_PATTERN.match(repo_name):
        raise HTTPException(status_code=400, detail="Invalid repo_name format.")
    if not FILE_PATH_PATTERN.match(file_path):
        raise HTTPException(status_code=400, detail="Invalid file_path format.")

    # Language hint map for frontend syntax highlighting
    EXT_LANG = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "jsx": "jsx", "tsx": "tsx", "java": "java", "go": "go",
        "rb": "ruby", "rs": "rust", "sh": "bash", "yml": "yaml",
        "yaml": "yaml", "json": "json", "toml": "toml",
        "dockerfile": "dockerfile", "md": "markdown",
    }
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    # special case: file named "Dockerfile"
    if file_path.lower().endswith("dockerfile"):
        ext = "dockerfile"
    language = EXT_LANG.get(ext, "plaintext")

    from agents.github_agent import _get_repo
    from github import GithubException

    try:
        repo = _get_repo(repo_name, token=token)
        content_file = repo.get_contents(file_path)
        raw = content_file.decoded_content.decode("utf-8", errors="replace")
        truncated = len(raw) > MAX_FILE_SIZE_CHARS
        return {
            "repo": repo_name,
            "file_path": file_path,
            "content": raw[:MAX_FILE_SIZE_CHARS],
            "truncated": truncated,
            "language": language,
            "size_bytes": content_file.size,
        }
    except GithubException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"File '{file_path}' not found in '{repo_name}'.")
        raise HTTPException(status_code=502, detail=f"GitHub API error {e.status}: {e.data}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch file: {e}")



# ─────────────────────────────────────────────────────────────────────────────
# Phase 12 — Code Search & Diff Inspection endpoints
# ─────────────────────────────────────────────────────────────────────────────

from agents.code_search import search_code_in_repo
from agents.diff_inspector import inspect_diff, inspect_commit_diff

# Validation: only allow sane regex/query lengths
MAX_QUERY_LEN = 200
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")


@app.get("/github/repo/search")
def code_search(
    repo_name: str,
    query: str,
    use_regex: bool = False,
    extensions: str = "",
    max_results: int = 30,
    token: Optional[str] = None,
):
    """
    Searches source files in *repo_name* for *query* (plain text or regex).

    Query params
    ────────────
    repo_name   : owner/repo
    query       : text or regex pattern to search for
    use_regex   : treat query as a regular expression (default: false)
    extensions  : comma-separated file extensions to search, e.g. ``.py,.js``
                  (default: all common source extensions)
    max_results : cap on the number of matches returned (1-100, default 30)
    token       : optional GitHub OAuth token
    """
    repo_name = repo_name.strip()
    if not REPO_PATTERN.match(repo_name):
        raise HTTPException(status_code=400, detail="Invalid repo_name format (expected owner/repo).")
    if not query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")
    if len(query) > MAX_QUERY_LEN:
        raise HTTPException(status_code=400, detail=f"query exceeds maximum length of {MAX_QUERY_LEN} characters.")
    max_results = max(1, min(max_results, 100))

    ext_tuple = None
    if extensions.strip():
        raw_exts = [e.strip() for e in extensions.split(",") if e.strip()]
        # Normalise: ensure leading dot
        ext_tuple = tuple(e if e.startswith(".") else f".{e}" for e in raw_exts)

    result = search_code_in_repo(
        repo_name,
        query,
        token=token,
        use_regex=use_regex,
        max_results=max_results,
        **({"file_extensions": ext_tuple} if ext_tuple else {}),
    )

    if result.error:
        raise HTTPException(status_code=502, detail=result.error)

    # Serialise dataclasses to plain dicts for JSON response
    return {
        "repo": result.repo,
        "query": result.query,
        "use_regex": result.use_regex,
        "files_scanned": result.files_scanned,
        "total_matches": result.total_matches,
        "truncated": result.truncated,
        "matches": [
            {
                "file_path": m.file_path,
                "line_number": m.line_number,
                "line_content": m.line_content,
                "context_before": m.context_before,
                "context_after": m.context_after,
            }
            for m in result.matches
        ],
    }


@app.get("/github/repo/diff")
def git_diff(
    repo_name: str,
    base: str,
    head: str,
    path_filter: str = "",
    max_files: int = 20,
    token: Optional[str] = None,
):
    """
    Returns the unified diff between *base* and *head* refs.

    Query params
    ────────────
    repo_name   : owner/repo
    base        : base commit SHA, branch, or tag
    head        : head commit SHA, branch, or tag
    path_filter : optional filename substring filter
    max_files   : cap on files returned (1-50, default 20)
    token       : optional GitHub OAuth token
    """
    repo_name = repo_name.strip()
    if not REPO_PATTERN.match(repo_name):
        raise HTTPException(status_code=400, detail="Invalid repo_name format (expected owner/repo).")
    if not base.strip() or not head.strip():
        raise HTTPException(status_code=400, detail="Both 'base' and 'head' are required.")
    max_files = max(1, min(max_files, 50))

    result = inspect_diff(
        repo_name,
        base.strip(),
        head.strip(),
        token=token,
        path_filter=path_filter.strip() or None,
        max_files=max_files,
    )

    if result.error:
        raise HTTPException(status_code=502, detail=result.error)

    return {
        "repo": result.repo,
        "base": result.base,
        "head": result.head,
        "total_files_changed": result.total_files_changed,
        "total_additions": result.total_additions,
        "total_deletions": result.total_deletions,
        "truncated": result.truncated,
        "files": [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch,
                "previous_filename": f.previous_filename,
            }
            for f in result.files
        ],
    }


@app.get("/github/repo/commit-diff")
def commit_diff(
    repo_name: str,
    sha: str,
    max_files: int = 20,
    token: Optional[str] = None,
):
    """
    Returns the diff introduced by a single commit (commit vs its first parent).

    Query params
    ────────────
    repo_name : owner/repo
    sha       : commit SHA (7–40 hex characters)
    max_files : cap on files returned (1-50, default 20)
    token     : optional GitHub OAuth token
    """
    repo_name = repo_name.strip()
    sha = sha.strip()
    if not REPO_PATTERN.match(repo_name):
        raise HTTPException(status_code=400, detail="Invalid repo_name format (expected owner/repo).")
    if not SHA_PATTERN.match(sha):
        raise HTTPException(status_code=400, detail="sha must be a 7–40 character hex string.")
    max_files = max(1, min(max_files, 50))

    result = inspect_commit_diff(repo_name, sha, token=token, max_files=max_files)

    if result.error:
        raise HTTPException(status_code=502, detail=result.error)

    return {
        "repo": result.repo,
        "sha": result.head,
        "parent_sha": result.base,
        "total_additions": result.total_additions,
        "total_deletions": result.total_deletions,
        "truncated": result.truncated,
        "files": [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch,
                "previous_filename": f.previous_filename,
            }
            for f in result.files
        ],
    }


@app.get("/health")
def health_check():
    mcp_client = GitHubMCPClient()
    return {
        "status": "healthy",
        "system": "AI Engineering Copilot Multi-Agent System",
        "version": "2.0.0",
        "mcp_status": mcp_client.get_status(),
        "agents": [
            "Orchestrator Agent",
            "GitHub Code Investigation Agent",
            "Log Analysis Agent",
            "CI/CD Investigation Agent",
            "Infrastructure Investigation Agent",
            "Knowledge and Documentation Agent",
            "Verification Agent",
        ],
    }


@app.get("/")
def root():
    return {"message": "AI Engineering Copilot Multi-Agent API is active. See /health and /docs."}
