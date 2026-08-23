"""Regression tests for PackVM-owned Git branch discovery."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ecosystem.rumi_git_read_pack.runtime.read import _branch_listing


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_branch_listing_includes_unique_cached_remote_only_name(tmp_path: Path) -> None:
    """Expose a remote-only branch using the safe local tracking name."""
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Tobkiri Test")
    _git(repository, "config", "user.email", "test@example.invalid")
    (repository / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "fixture")
    head = _git(repository, "rev-parse", "HEAD").strip()
    _git(repository, "update-ref", "refs/remotes/origin/topic", head)

    assert _branch_listing(repository).splitlines() == ["*\tmain", "\ttopic"]


def test_branch_listing_excludes_ambiguous_and_symbolic_remote_names(
    tmp_path: Path,
) -> None:
    """Do not offer names that ``git switch`` cannot resolve unambiguously."""
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Tobkiri Test")
    _git(repository, "config", "user.email", "test@example.invalid")
    (repository / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "fixture")
    head = _git(repository, "rev-parse", "HEAD").strip()
    _git(repository, "update-ref", "refs/remotes/origin/topic", head)
    _git(repository, "update-ref", "refs/remotes/upstream/topic", head)
    _git(repository, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/topic")

    assert _branch_listing(repository).splitlines() == ["*\tmain"]
