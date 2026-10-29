"""
tests/test_phase12.py
─────────────────────
Phase 12 — Unit tests for Code Search and Diff Inspector agents.
All tests are fully offline: no real GitHub API calls are made.
PyGithub objects are replaced with lightweight dataclass stubs.
"""

from __future__ import annotations

import sys
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.code_search import (
    CodeSearchResult,
    CodeMatch,
    search_code_in_repo,
    _compile_pattern,
    _match_lines,
    _extract_context,
)
from agents.diff_inspector import (
    DiffResult,
    FileDiff,
    inspect_diff,
    inspect_commit_diff,
    _sum_additions,
    _sum_deletions,
)


# ─────────────────────────────────────────────────────────────────────────────
# Stubs
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _StubContentFile:
    """Minimal stub for github.ContentFile."""
    path: str
    name: str
    type: str = "file"
    size: int = 100
    _content: str = ""

    @property
    def decoded_content(self):
        return self._content.encode("utf-8")


@dataclass
class _StubFilePatch:
    """Minimal stub for a file entry inside a Commit / Comparison."""
    filename: str
    status: str = "modified"
    additions: int = 5
    deletions: int = 2
    patch: Optional[str] = "@@ -1,3 +1,4 @@\n context\n+added line\n context"
    previous_filename: Optional[str] = None


@dataclass
class _StubCommit:
    sha: str
    files: List[_StubFilePatch] = field(default_factory=list)
    parents: List[MagicMock] = field(default_factory=list)


@dataclass
class _StubComparison:
    files: List[_StubFilePatch] = field(default_factory=list)
    total_commits: int = 1


# ─────────────────────────────────────────────────────────────────────────────
# code_search — internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_compile_pattern_literal():
    """Special regex characters in a literal query must be escaped."""
    p = _compile_pattern("raise ValueError(", use_regex=False)
    assert p.search("    raise ValueError('oops')")
    assert not p.search("print('hello')")


def test_compile_pattern_regex():
    """Regex mode compiles the pattern as-is."""
    p = _compile_pattern(r"def \w+\(", use_regex=True)
    assert p.search("def my_function(arg):")
    assert not p.search("class MyClass:")


def test_match_lines_basic():
    content = "line one\nraise ValueError\nline three\n"
    pattern = re.compile("ValueError", re.IGNORECASE)
    hits = _match_lines(content, pattern)
    assert len(hits) == 1
    assert hits[0] == (2, "raise ValueError")


def test_match_lines_case_insensitive():
    content = "Error\nerror\nERROR\nnormal"
    pattern = re.compile("error", re.IGNORECASE)
    hits = _match_lines(content, pattern)
    assert len(hits) == 3


def test_extract_context_middle():
    lines = ["a", "b", "c", "d", "e"]
    before, after = _extract_context(lines, idx=2, window=2)
    assert before == ["a", "b"]
    assert after == ["d", "e"]


def test_extract_context_boundaries():
    lines = ["a", "b"]
    before, after = _extract_context(lines, idx=0, window=2)
    assert before == []
    assert after == ["b"]


# ─────────────────────────────────────────────────────────────────────────────
# search_code_in_repo — integration with mocked GitHub
# ─────────────────────────────────────────────────────────────────────────────


def _make_content_item(path: str, content: str, size: int = 100) -> _StubContentFile:
    name = path.split("/")[-1]
    return _StubContentFile(path=path, name=name, size=size, _content=content)


def test_search_code_empty_query():
    result = search_code_in_repo("owner/repo", "  ")
    assert result.error is not None
    assert result.total_matches == 0


def test_search_code_invalid_regex():
    result = search_code_in_repo("owner/repo", "[unclosed", use_regex=True)
    assert result.error is not None
    assert "Invalid regex" in result.error


def test_search_code_finds_match():
    """Mock the GitHub client so the search runs entirely offline."""
    py_file = _make_content_item(
        "src/app.py",
        "import os\nraise ValueError('bad config')\nprint('done')",
    )

    mock_repo = MagicMock()
    mock_repo.get_contents.return_value = [py_file]

    with patch("agents.code_search._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = search_code_in_repo("owner/repo", "ValueError")

    assert result.error is None
    assert result.total_matches >= 1
    assert result.matches[0].file_path == "src/app.py"
    assert result.matches[0].line_number == 2


def test_search_code_no_matches():
    py_file = _make_content_item("src/utils.py", "def helper(): pass\n")

    mock_repo = MagicMock()
    mock_repo.get_contents.return_value = [py_file]

    with patch("agents.code_search._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = search_code_in_repo("owner/repo", "ThisWillNeverExist12345")

    assert result.error is None
    assert result.total_matches == 0
    assert result.matches == []


def test_search_code_max_results_caps():
    """When max_results is hit, truncated should be True."""
    files = [
        _make_content_item(f"src/file{i}.py", "raise ValueError\n" * 5)
        for i in range(20)
    ]

    mock_repo = MagicMock()
    mock_repo.get_contents.return_value = files

    with patch("agents.code_search._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = search_code_in_repo("owner/repo", "ValueError", max_results=3)

    assert result.truncated is True
    assert len(result.matches) == 3


def test_search_code_skips_large_files():
    """Files over the size limit must be skipped."""
    large_file = _make_content_item("src/big.py", "raise ValueError\n", size=300_000)

    mock_repo = MagicMock()
    mock_repo.get_contents.return_value = [large_file]

    with patch("agents.code_search._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = search_code_in_repo("owner/repo", "ValueError")

    assert result.files_scanned == 0
    assert result.total_matches == 0


# ─────────────────────────────────────────────────────────────────────────────
# diff_inspector — internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_sum_additions():
    files = [FileDiff("a.py", "modified", 3, 1, None),
             FileDiff("b.py", "added", 10, 0, None)]
    assert _sum_additions(files) == 13


def test_sum_deletions():
    files = [FileDiff("a.py", "modified", 3, 1, None),
             FileDiff("b.py", "removed", 0, 5, None)]
    assert _sum_deletions(files) == 6


# ─────────────────────────────────────────────────────────────────────────────
# inspect_diff — integration with mocked GitHub
# ─────────────────────────────────────────────────────────────────────────────


def test_inspect_diff_basic():
    stub_files = [
        _StubFilePatch("src/main.py", "modified", 4, 2,
                       "@@ -1 +1 @@\n-old\n+new"),
        _StubFilePatch("README.md", "modified", 1, 0, "@@ -1 +1 @@\n+doc"),
    ]
    comparison = _StubComparison(files=stub_files, total_commits=2)

    mock_repo = MagicMock()
    mock_repo.compare.return_value = comparison

    with patch("agents.diff_inspector._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = inspect_diff("owner/repo", "abc1234", "def5678")

    assert result.error is None
    assert len(result.files) == 2
    assert result.total_additions == 5
    assert result.total_deletions == 2
    assert result.truncated is False


def test_inspect_diff_path_filter():
    stub_files = [
        _StubFilePatch("src/main.py", "modified", 4, 2, "patch"),
        _StubFilePatch("README.md", "modified", 1, 0, "patch"),
    ]
    comparison = _StubComparison(files=stub_files)

    mock_repo = MagicMock()
    mock_repo.compare.return_value = comparison

    with patch("agents.diff_inspector._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = inspect_diff("owner/repo", "abc", "def", path_filter=".py")

    assert len(result.files) == 1
    assert result.files[0].filename == "src/main.py"


def test_inspect_diff_max_files_truncated():
    stub_files = [_StubFilePatch(f"file{i}.py") for i in range(10)]
    comparison = _StubComparison(files=stub_files)

    mock_repo = MagicMock()
    mock_repo.compare.return_value = comparison

    with patch("agents.diff_inspector._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = inspect_diff("owner/repo", "abc", "def", max_files=3)

    assert result.truncated is True
    assert len(result.files) == 3


def test_inspect_commit_diff_basic():
    parent = MagicMock()
    parent.sha = "parent000"

    stub_files = [
        _StubFilePatch("src/api.py", "modified", 7, 3, "@@ patch @@\n+line"),
    ]
    commit = _StubCommit(sha="abc1234", files=stub_files, parents=[parent])

    mock_repo = MagicMock()
    mock_repo.get_commit.return_value = commit

    with patch("agents.diff_inspector._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = inspect_commit_diff("owner/repo", "abc1234")

    assert result.error is None
    assert result.head == "abc1234"
    assert result.base == "parent000"
    assert len(result.files) == 1
    assert result.total_additions == 7


def test_inspect_commit_diff_root_commit():
    """Root commits have no parent — base should be empty string."""
    stub_files = [_StubFilePatch("init.py", "added", 10, 0, None)]
    commit = _StubCommit(sha="root000", files=stub_files, parents=[])

    mock_repo = MagicMock()
    mock_repo.get_commit.return_value = commit

    with patch("agents.diff_inspector._build_github_client") as mock_gh:
        mock_gh.return_value.get_repo.return_value = mock_repo
        result = inspect_commit_diff("owner/repo", "root000")

    assert result.base == ""
    assert result.error is None
