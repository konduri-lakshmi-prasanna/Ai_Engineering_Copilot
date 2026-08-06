from github import Github
import os
from dotenv import load_dotenv

load_dotenv()

def github_agent(repo_name: str, limit: int = 5) -> dict:
    """
    Fetches recent commits and changed files from a GitHub repo.
    repo_name format: "owner/repo"
    """
    token = os.getenv("GITHUB_TOKEN")
    gh = Github(token)
    repo = gh.get_repo(repo_name)
    commits = repo.get_commits()[:limit]

    result = {"repo": repo_name, "commits": []}

    for c in commits:
        result["commits"].append({
            "sha": c.sha[:7],
            "message": c.commit.message,
            "author": c.commit.author.name,
            "date": str(c.commit.author.date),
            "files_changed": [f.filename for f in c.files],
        })

    return result