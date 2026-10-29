"""
agents/code_search.py
─────────────────────
Code Search Agent — Phase 12
Searches source files in a GitHub repository for a given query string or
regex pattern.  Operates entirely via the PyGithub REST API (no MCP
dependency) so it works out-of-the-box with just a GITHUB_TOKEN.

Public API
──────────
    search_code_in_repo(repo_name, query, *, token, file_extensions,
                        max_results, use_regex) -> CodeSearchResult
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from github import Github, GithubException, Auth


# ── Domain types ─────────────────────────────────────────────────────────────


@dataclass
class CodeMatch:
    """One occurrence of the query inside a repository file."""
    file_path: str
    line_number: int
    line_content: str
    context_before: List[str] = field(default_factory=list)   # up to 2 lines
    context_after: List[str] = field(default_factory=list)    # up to 2 lines


@dataclass
class CodeSearchResult:
    """Aggregated result returned by search_code_in_repo()."""
    repo: str
    query: str
    use_regex: bool
    files_scanned: int
    total_matches: int
    matches: List[CodeMatch]
    truncated: bool = False          # True when max_results was hit
    error: Optional[str] = None


# ── Internal helpers ──────────────────────────────────────────────────────────


_DEFAULT_EXTENSIONS = (
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rb", ".rs", ".cs",
    ".sh", ".yaml", ".yml", ".toml", ".json",
)

_MAX_FILE_SIZE_BYTES = 200_000   # skip files larger than 200 KB


def _build_github_client(token: Optional[str]) -> Github:
    token = token or os.getenv("GITHUB_TOKEN")
    if token:
        return Github(auth=Auth.Token(token))
    return Github()


def _compile_pattern(query: str, use_regex: bool) -> re.Pattern:
    """Returns a compiled search pattern (case-insensitive)."""
    pattern_str = query if use_regex else re.escape(query)
    return re.compile(pattern_str, re.IGNORECASE)


def _match_lines(content: str, pattern: re.Pattern) -> List[tuple[int, str]]:
    """
    Returns (line_number, line_text) for every line containing a match.
    Line numbers are 1-based.
    """
    return [
        (idx + 1, line)
        for idx, line in enumerate(content.splitlines())
        if pattern.search(line)
    ]


def _extract_context(lines: List[str], idx: int, window: int = 2) -> tuple[List[str], List[str]]:
    """Returns (before, after) context lines around lines[idx]."""
    before = lines[max(0, idx - window): idx]
    after = lines[idx + 1: idx + 1 + window]
    return before, after


def _collect_repo_files(
    repo,
    extensions: tuple[str, ...],
    path: str = "",
    accumulated: Optional[List] = None,
) -> List:
    """
    Recursively collects file objects whose names end with one of *extensions*.
    Capped at 500 files to avoid runaway API calls on large mono-repos.
    """
    if accumulated is None:
        accumulated = []
    if len(accumulated) >= 500:
        return accumulated

    try:
        contents = repo.get_contents(path)
        for item in contents:
            if len(accumulated) >= 500:
                break
            if item.type == "dir":
                _collect_repo_files(repo, extensions, item.path, accumulated)
            elif any(item.name.lower().endswith(ext) for ext in extensions):
                accumulated.append(item)
    except GithubException:
        pass

    return accumulated


# ── Public API ────────────────────────────────────────────────────────────────


def search_code_in_repo(
    repo_name: str,
    query: str,
    *,
    token: Optional[str] = None,
    file_extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS,
    max_results: int = 30,
    use_regex: bool = False,
) -> CodeSearchResult:
    """
    Searches *query* across all source files in *repo_name*.

    Parameters
    ──────────
    repo_name       : ``owner/repo`` string.
    query           : Plain text or regex string to search for.
    token           : GitHub personal-access or OAuth token.
    file_extensions : Tuple of lowercase extensions to include (default covers
                      the most common languages).
    max_results     : Maximum number of CodeMatch items to return.
    use_regex       : When True *query* is treated as a raw regex; otherwise it
                      is escaped before compiling so special characters are
                      matched literally.

    Returns
    ───────
    CodeSearchResult — always returned (never raises).  Inspect ``.error``
    to detect API failures.
    """
    if not query.strip():
        return CodeSearchResult(
            repo=repo_name, query=query, use_regex=use_regex,
            files_scanned=0, total_matches=0, matches=[],
            error="Query string must not be empty.",
        )

    try:
        pattern = _compile_pattern(query, use_regex)
    except re.error as exc:
        return CodeSearchResult(
            repo=repo_name, query=query, use_regex=use_regex,
            files_scanned=0, total_matches=0, matches=[],
            error=f"Invalid regex pattern: {exc}",
        )

    try:
        gh = _build_github_client(token)
        repo = gh.get_repo(repo_name)
    except GithubException as exc:
        return CodeSearchResult(
            repo=repo_name, query=query, use_regex=use_regex,
            files_scanned=0, total_matches=0, matches=[],
            error=f"GitHub API error {exc.status}: {exc.data}",
        )

    file_items = _collect_repo_files(repo, file_extensions)

    all_matches: List[CodeMatch] = []
    files_scanned = 0
    truncated = False

    for item in file_items:
        if len(all_matches) >= max_results:
            truncated = True
            break

        # Skip oversized blobs
        if item.size > _MAX_FILE_SIZE_BYTES:
            continue

        try:
            raw = item.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            continue

        files_scanned += 1
        raw_lines = raw.splitlines()
        hits = _match_lines(raw, pattern)

        for line_no, line_text in hits:
            if len(all_matches) >= max_results:
                truncated = True
                break

            line_idx = line_no - 1
            before, after = _extract_context(raw_lines, line_idx)
            all_matches.append(
                CodeMatch(
                    file_path=item.path,
                    line_number=line_no,
                    line_content=line_text.rstrip(),
                    context_before=before,
                    context_after=after,
                )
            )

    return CodeSearchResult(
        repo=repo_name,
        query=query,
        use_regex=use_regex,
        files_scanned=files_scanned,
        total_matches=len(all_matches),
        matches=all_matches,
        truncated=truncated,
    )
