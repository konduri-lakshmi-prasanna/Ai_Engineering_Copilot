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
