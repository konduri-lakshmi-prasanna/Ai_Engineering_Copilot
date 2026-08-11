from github import Github
import os
from dotenv import load_dotenv

load_dotenv()


def _get_repo(repo_name: str):
    token = os.getenv("GITHUB_TOKEN")
    gh = Github(token)
    return gh.get_repo(repo_name)


def github_agent_targeted(repo_name: str, file_paths: list, commits_per_file: int = 5) -> dict:
    """
    For each file path pulled from the log's stack trace, fetches that
    file's actual current content plus the real commits that last touched
    it — the real error source, instead of a guess from recent activity.
    """
    repo = _get_repo(repo_name)

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

def fetch_package_json(repo_name: str) -> dict | None:
    """
    Fetches package.json's scripts field directly — the ground truth for
    npm 'missing script' errors. Checks the repo root first, then common
    frontend subfolder names, since many repos nest the frontend app.
    """
    repo = _get_repo(repo_name)
    candidate_paths = [
        "package.json",
        "frontend/package.json",
        "client/package.json",
        "web/package.json",
        "app/package.json",
    ]

    import json as _json
    for path in candidate_paths:
        try:
            content_file = repo.get_contents(path)
            pkg = _json.loads(content_file.decoded_content.decode("utf-8"))
            return {
                "found_at": path,
                "scripts": pkg.get("scripts", {}),
                "name": pkg.get("name"),
            }
        except Exception:
            continue

    return None




def github_agent(repo_name: str, limit: int = 8) -> dict:
    """
    Fallback: fetches the most recent `limit` commits with a short diff
    snippet per changed file. Used only when the log doesn't contain any
    identifiable file paths, so we have nothing to target directly.
    """
    repo = _get_repo(repo_name)
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