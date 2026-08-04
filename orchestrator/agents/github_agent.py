from github import Github
import os
from dotenv import load_dotenv

load_dotenv()

def github_agent(repo_name: str, limit: int = 5, max_files: int = 10) -> dict:
    """
    Fetches recent commits and changed files from a GitHub repo.
    repo_name format: "owner/repo", e.g. "konduri-lakshmi-prasanna/Ai_Engineering_Copilot"
    """
    token = os.getenv("GITHUB_TOKEN")
    gh = Github(token)
    repo = gh.get_repo(repo_name)
    commits = repo.get_commits()[:limit]

    result = {
        "repo": repo_name,
        "commits": []
    }

    ignore_folders = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".idea", ".vscode", "env", "dist", "build"}

    for c in commits:
        # Filter files belonging to venv, node_modules, etc.
        filtered_files = []
        for f in c.files:
            parts = f.filename.replace("\\", "/").split("/")
            if not any(part in ignore_folders for part in parts):
                filtered_files.append(f.filename)

        # Limit the number of files reported in the JSON output
        truncated = len(filtered_files) > max_files
        files_list = filtered_files[:max_files]
        if truncated:
            files_list.append(f"... and {len(filtered_files) - max_files} more files")

        result["commits"].append({
            "sha": c.sha[:7],
            "message": c.commit.message,
            "author": c.commit.author.name,
            "date": str(c.commit.author.date),
            "files_changed": files_list,
        })

    return result