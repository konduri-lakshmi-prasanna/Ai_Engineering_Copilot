from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from graph import build_graph
from auth import router as auth_router
import re

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

    return {
        "repo": repo_name,
        "commits_analyzed": [c["sha"] for c in result["github_data"]["commits"]],
        "errors_found": result["logs_data"]["error_count"],
        "root_cause": result["root_cause"],
    }


@app.get("/")
def health_check():
    return {"status": "AI Engineering Copilot API is running"}