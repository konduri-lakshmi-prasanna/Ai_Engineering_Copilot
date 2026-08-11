import os
import re
import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from graph import build_graph
from auth import router as auth_router
from llm_client import ask_groq

app = FastAPI(title="AI Engineering Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

copilot_graph = build_graph()

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class AnalyzeRequest(BaseModel):
    repo_name: str = Field(..., description="Format: owner/repo, e.g. facebook/react")
    log_text: str = Field(..., min_length=1)


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
        })
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "Not Found" in error_msg:
            raise HTTPException(status_code=404, detail=f"Repo '{repo_name}' not found or not accessible")
        if "403" in error_msg or "rate limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail="GitHub API rate limit hit — try again shortly")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {error_msg}")

    github_data = result["github_data"]
    scan_mode = github_data.get("mode", "recent")
    items_scanned = (
        len(github_data.get("files", []))
        if scan_mode == "targeted"
        else len(github_data.get("commits", []))
    )

    return {
        "repo": repo_name,
        "commits_scanned": items_scanned,
        "scan_mode": scan_mode,
        "implicated_commits": result["implicated_commits"],
        "errors_found": result["logs_data"]["error_count"],
        "root_cause": result["root_cause"],
        "fix_suggestion": result["fix_suggestion"],
        "why_it_works": result.get("why_it_works", ""),
        "beginner_explanation": result.get("beginner_explanation", ""),
        "interview_questions": result.get("interview_questions", []),
    }


class ChatRequest(BaseModel):
    repo_name: str
    context: dict
    question: str


@app.post("/chat")
def chat(request: ChatRequest):
    """
    Handles follow-up questions about an analysis that already ran, instead
    of re-running the full GitHub/logs/reasoning pipeline from scratch.
    """
    context_json = json.dumps(request.context, indent=2)

    prompt = f"""
You already analyzed a deployment issue for the repo {request.repo_name}.
Here is what you found earlier:

{context_json}

The user now asks a follow-up question:
"{request.question}"

Answer directly and practically, building on the analysis above — don't
re-diagnose from scratch or invent a new root cause. If they ask for exact
commands, give a numbered, copy-pasteable list. If the question needs
information not covered above, say so honestly rather than guessing.
"""

    try:
        answer = ask_groq(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

    return {"answer": answer}


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _resolve_to_username(identifier: str, client: httpx.AsyncClient, headers: dict) -> str:
    """
    Accepts either a GitHub username or an email address and returns a
    GitHub username. GitHub has no direct "look up by email" endpoint
    (emails are private by default), so for an email we fall back to
    GitHub's user-search API, which only finds a match if that person has
    made their email public on their profile.
    """
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
            raise HTTPException(status_code=429, detail="GitHub API rate limit hit — try again shortly")
        if search_response.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to search GitHub for that email")

        items = search_response.json().get("items", [])
        if not items:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No public GitHub profile found for '{identifier}'. "
                    "Most people keep their email private on GitHub — try their username instead."
                ),
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
                raise HTTPException(status_code=429, detail="GitHub API rate limit hit — try again shortly")
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


@app.get("/")
def health_check():
    return {"status": "AI Engineering Copilot API is running"}