import os
import re
import httpx
from dotenv import load_dotenv

load_dotenv()

API = "https://api.github.com"
MAX_LOG_LINES = 150
MAX_LOG_CHARS = 8000

# GitHub prefixes every log line with a timestamp, and CI tools add ANSI
# colour codes. Both are noise for the log parser and the model.
_TIMESTAMP = re.compile(r"^\ufeff?\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class DeploymentAgentError(Exception):
    """Raised when GitHub refuses or fails a request. Carries an HTTP status
    so the API layer can pass a sensible one back to the frontend."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _headers(token):
    token = token or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(client, url, params=None, allow_missing=False):
    response = client.get(url, params=params)

    if response.status_code == 200:
        return response
    if allow_missing and response.status_code in (404, 410):
        return None

    if response.status_code == 401:
        raise DeploymentAgentError(
            "GitHub rejected the token (401). Log in with GitHub again, "
            "or check GITHUB_TOKEN in your .env file.",
            401,
        )
    if response.status_code == 403:
        if response.headers.get("x-ratelimit-remaining") == "0":
            raise DeploymentAgentError("GitHub API rate limit hit. Try again shortly.", 429)
        raise DeploymentAgentError(
            "GitHub denied access to this repo's workflow runs (403). The token "
            "needs the 'repo' scope (or Actions read access).",
            403,
        )
    if response.status_code == 404:
        raise DeploymentAgentError(
            "Repo not found, or this token can't see its GitHub Actions. "
            "For private repos, log in with GitHub first.",
            404,
        )
    raise DeploymentAgentError(f"GitHub returned an unexpected error ({response.status_code}).", 502)


def _clean_log(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = _ANSI.sub("", _TIMESTAMP.sub("", line)).rstrip()
        lines.append(line)

    # Failures sit at the end of a job log, so keep the tail.
    text = "\n".join(lines[-MAX_LOG_LINES:])
    if len(text) > MAX_LOG_CHARS:
        text = text[-MAX_LOG_CHARS:]
    return text.strip()


def _run_summary(run: dict) -> dict:
    return {
        "id": run["id"],
        "name": run.get("name") or run.get("display_title") or "workflow run",
        "run_number": run.get("run_number"),
        "branch": run.get("head_branch"),
        "sha": (run.get("head_sha") or "")[:7],
        "event": run.get("event"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("created_at"),
        "url": run.get("html_url"),
    }


def deployment_agent(repo_name: str, token: str | None = None, client: httpx.Client | None = None) -> dict:
    """
    Looks up the most recent FAILED GitHub Actions run for a repo, finds the
    job and step that failed, and downloads that job's log, so the user
    doesn't have to copy and paste a log by hand.

    Returns a dict with a "status" key:
      - "failed_run_found": run, failed_job, failed_steps, log_text (and log_note)
      - "no_runs":          the repo has no Actions runs at all
      - "no_failures":      runs exist, but none of them failed
    """
    owns_client = client is None
    if owns_client:
        client = httpx.Client(headers=_headers(token), follow_redirects=True, timeout=30)

    try:
        runs_url = f"{API}/repos/{repo_name}/actions/runs"

        failed = _get(client, runs_url, {"status": "failure", "per_page": 1}).json()
        failed_runs = failed.get("workflow_runs", [])

        if not failed_runs:
            latest = _get(client, runs_url, {"per_page": 1}).json().get("workflow_runs", [])
            if not latest:
                return {
                    "status": "no_runs",
                    "message": (
                        f"{repo_name} has no GitHub Actions runs yet, so there is no "
                        "deployment to check. Add a workflow, or paste a log below."
                    ),
                }
            run = _run_summary(latest[0])
            return {
                "status": "no_failures",
                "run": run,
                "message": (
                    f"Good news: no failed runs found for {repo_name}. The latest run "
                    f"({run['name']} #{run['run_number']}) is "
                    f"{run['conclusion'] or 'still in progress'}."
                ),
            }

        run = failed_runs[0]
        jobs_url = f"{API}/repos/{repo_name}/actions/runs/{run['id']}/jobs"
        jobs = _get(client, jobs_url, {"filter": "latest", "per_page": 100}).json().get("jobs", [])

        failed_jobs = [j for j in jobs if j.get("conclusion") == "failure"]
        target = failed_jobs[0] if failed_jobs else (jobs[0] if jobs else None)

        result = {
            "status": "failed_run_found",
            "run": _run_summary(run),
            "failed_job": target["name"] if target else None,
            "failed_steps": [],
            "log_text": "",
            "log_note": None,
        }

        if not target:
            result["log_note"] = "The run failed before any job started, so there is no log."
            return result

        result["failed_steps"] = [
            s["name"] for s in target.get("steps", []) if s.get("conclusion") == "failure"
        ]

        log_response = _get(
            client,
            f"{API}/repos/{repo_name}/actions/jobs/{target['id']}/logs",
            allow_missing=True,
        )
        if log_response is None:
            result["log_note"] = (
                "GitHub no longer has the log for this run (logs expire after a while). "
                "Re-run the workflow, or paste the error below."
            )
        else:
            result["log_text"] = _clean_log(log_response.text)

        return result
    except httpx.HTTPError as e:
        raise DeploymentAgentError(f"Could not reach GitHub: {e}", 502)
    finally:
        if owns_client:
            client.close()