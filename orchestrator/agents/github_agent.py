from github import Github
import os
from dotenv import load_dotenv

load_dotenv()


def github_agent(repo_name: str, limit: int = 30) -> dict:
    """
    Fetches the most recent `limit` commits from a repo, including a short
    diff snippet per changed file, so the reasoning step can actually judge
    which commit(s) are responsible for an error instead of guessing from
    filenames alone.
    """
    token = os.getenv("GITHUB_TOKEN")
    gh = Github(token)
    repo = gh.get_repo(repo_name)
    commits = repo.get_commits()[:limit]

    result = {"repo": repo_name, "commits": []}
    for c in commits:
        files = []
        for f in c.files[:5]:
            files.append({
                "filename": f.filename,
                "status": f.status,
                "patch": f.patch[:400] if f.patch else None,
            })

        result["commits"].append({
            "sha": c.sha[:7],
            "message": c.commit.message,
            "author": c.commit.author.name,
            "date": str(c.commit.author.date),
            "files": files,
        })
    return result