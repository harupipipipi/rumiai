from __future__ import annotations

import hashlib
from typing import Any

from domain.coding.file_ops import FileOps
from domain.coding.git_ops import GitOps
from domain.coding.workspace_resolver import WorkspaceResolver


def build_file_tree(input_data: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    resolution = WorkspaceResolver().resolve(data, context or {}, allow_cwd_fallback=True)
    directory = str(data.get("directory") or ".")
    recursive = bool(data.get("recursive", True))
    limit = data.get("limit", 400)
    if not isinstance(limit, int) or limit < 1:
        limit = 400
    files = FileOps(resolution.root_path).list_files(directory, recursive=recursive)
    clipped = len(files) > limit
    files = files[:limit]
    git_status = None
    git_error = None
    if data.get("include_git", True):
        try:
            git_status = GitOps(resolution.root_path).status()
        except Exception as exc:
            git_error = str(exc)
    workspace_hash = hashlib.sha256(str(resolution.root_path or "").encode("utf-8")).hexdigest()[:16]
    return {
        "workspace_id": resolution.workspace_id or f"ws_{workspace_hash}",
        "workspace_hash": workspace_hash,
        "workspace_root": f"workspace:{workspace_hash}",
        "root": ".",
        "directory": directory,
        "recursive": recursive,
        "files": files,
        "total_returned": len(files),
        "clipped": clipped,
        "status": {
            "git": git_status,
            "git_error": git_error,
            "counts": _counts(files, git_status),
        },
        "policy": {
            "read_only": True,
            "workspace_source": resolution.source,
            "trusted": resolution.trusted,
        },
    }


def _counts(files: list[dict[str, Any]], git_status: dict[str, Any] | None) -> dict[str, int]:
    counts = {
        "files": sum(1 for item in files if not item.get("is_dir")),
        "directories": sum(1 for item in files if item.get("is_dir")),
        "staged": 0,
        "modified": 0,
        "untracked": 0,
    }
    if isinstance(git_status, dict):
        counts["staged"] = len(git_status.get("staged") or [])
        counts["modified"] = len(git_status.get("modified") or [])
        counts["untracked"] = len(git_status.get("untracked") or [])
    return counts
