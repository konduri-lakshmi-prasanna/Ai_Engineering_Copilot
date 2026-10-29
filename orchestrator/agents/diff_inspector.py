"""
agents/diff_inspector.py
────────────────────────
Diff Inspector Agent — Phase 12
Fetches and parses the unified diff between two commits (or a commit and its
parent) inside a GitHub repository.

Public API
──────────
    inspect_diff(repo_name, base, head, *, token, path_filter,
                 max_files) -> DiffResult
    inspect_commit_diff(repo_name, sha, *, token, max_files) -> DiffResult
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from github import Github, GithubException, Auth


# ── Domain types ─────────────────────────────────────────────────────────────


@dataclass
class FileDiff:
    """Unified diff for a single file within a comparison."""
    filename: str
    status: str                # added | removed | modified | renamed
    additions: int
    deletions: int
    patch: Optional[str]       # unified diff patch text (may be None for binary)
    previous_filename: Optional[str] = None   # populated for renames


@dataclass
class DiffResult:
    """Complete diff between *base* and *head* revisions."""
    repo: str
    base: str                  # base commit SHA or ref
    head: str                  # head commit SHA or ref
    total_files_changed: int
    total_additions: int
    total_deletions: int
    files: List[FileDiff]
    truncated: bool = False    # True when max_files was hit
    error: Optional[str] = None


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_github_client(token: Optional[str]) -> Github:
    token = token or os.getenv("GITHUB_TOKEN")
    if token:
        return Github(auth=Auth.Token(token))
    return Github()


def _extract_file_diffs(
    comparison,
    path_filter: Optional[str],
    max_files: int,
) -> tuple[List[FileDiff], bool]:
    """
    Extracts FileDiff list from a PyGithub Comparison object.

    Returns (file_diffs, truncated).
    """
    diffs: List[FileDiff] = []
    truncated = False

    for f in comparison.files:
        if len(diffs) >= max_files:
            truncated = True
            break

        # Optional filename filter (substring match)
        if path_filter and path_filter not in f.filename:
            continue

        diffs.append(
            FileDiff(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                patch=f.patch[:3000] if f.patch else None,    # cap patch size
                previous_filename=getattr(f, "previous_filename", None),
            )
        )

    return diffs, truncated


def _sum_additions(files: List[FileDiff]) -> int:
    return sum(f.additions for f in files)


def _sum_deletions(files: List[FileDiff]) -> int:
    return sum(f.deletions for f in files)


# ── Public API ────────────────────────────────────────────────────────────────


def inspect_diff(
    repo_name: str,
    base: str,
    head: str,
    *,
    token: Optional[str] = None,
    path_filter: Optional[str] = None,
    max_files: int = 20,
) -> DiffResult:
    """
    Returns the unified diff between *base* and *head* refs in *repo_name*.

    Parameters
    ──────────
    repo_name   : ``owner/repo`` string.
    base        : Base commit SHA, branch name, or tag.
    head        : Head commit SHA, branch name, or tag.
    token       : GitHub personal-access or OAuth token.
    path_filter : Optional substring; only files whose path contains this
                  string are included in the result.
    max_files   : Maximum number of FileDiff items to return.

    Returns
    ───────
    DiffResult — always returned (never raises).  Inspect ``.error`` to detect
    API failures.
    """
    try:
        gh = _build_github_client(token)
        repo = gh.get_repo(repo_name)
        comparison = repo.compare(base, head)
    except GithubException as exc:
        return DiffResult(
            repo=repo_name, base=base, head=head,
            total_files_changed=0, total_additions=0, total_deletions=0,
            files=[], error=f"GitHub API error {exc.status}: {exc.data}",
        )
    except Exception as exc:
        return DiffResult(
            repo=repo_name, base=base, head=head,
            total_files_changed=0, total_additions=0, total_deletions=0,
            files=[], error=str(exc),
        )

    files, truncated = _extract_file_diffs(comparison, path_filter, max_files)

    return DiffResult(
        repo=repo_name,
        base=base,
        head=head,
        total_files_changed=comparison.total_commits,
        total_additions=_sum_additions(files),
        total_deletions=_sum_deletions(files),
        files=files,
        truncated=truncated,
    )


def inspect_commit_diff(
    repo_name: str,
    sha: str,
    *,
    token: Optional[str] = None,
    max_files: int = 20,
) -> DiffResult:
    """
    Returns the diff introduced by a single commit (commit vs its first parent).

    Parameters
    ──────────
    repo_name : ``owner/repo`` string.
    sha       : Full or abbreviated commit SHA.
    token     : GitHub personal-access or OAuth token.
    max_files : Maximum number of FileDiff items to return.

    Returns
    ───────
    DiffResult — always returned (never raises).
    """
    try:
        gh = _build_github_client(token)
        repo = gh.get_repo(repo_name)
        commit = repo.get_commit(sha)
    except GithubException as exc:
        return DiffResult(
            repo=repo_name, base="", head=sha,
            total_files_changed=0, total_additions=0, total_deletions=0,
            files=[], error=f"GitHub API error {exc.status}: {exc.data}",
        )
    except Exception as exc:
        return DiffResult(
            repo=repo_name, base="", head=sha,
            total_files_changed=0, total_additions=0, total_deletions=0,
            files=[], error=str(exc),
        )

    parents = commit.parents
    base_sha = parents[0].sha if parents else ""

    files: List[FileDiff] = []
    truncated = False
    for f in commit.files:
        if len(files) >= max_files:
            truncated = True
            break
        files.append(
            FileDiff(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                patch=f.patch[:3000] if f.patch else None,
                previous_filename=getattr(f, "previous_filename", None),
            )
        )

    return DiffResult(
        repo=repo_name,
        base=base_sha,
        head=sha,
        total_files_changed=len(files),
        total_additions=_sum_additions(files),
        total_deletions=_sum_deletions(files),
        files=files,
        truncated=truncated,
    )
