from __future__ import annotations

import difflib
import hashlib
import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.coding.workspace_jail import WorkspaceJail


MAX_SYNTHETIC_TEXT_BYTES = 1024 * 1024


@dataclass(frozen=True)
class StatusEntry:
    xy: str
    git_path: str
    path: str
    previous_path: str | None = None


class ChangeRequestSnapshotter:
    def __init__(self, workspace_root: str | os.PathLike[str]) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.jail = WorkspaceJail(self.workspace_root)
        self.git_root = Path(self._run_git(["rev-parse", "--show-toplevel"]).strip()).resolve()
        self._ensure_git_root_allowed()
        self.pathspec = self._workspace_pathspec()

    def snapshot(self) -> dict[str, Any]:
        base_sha = self._run_git(["rev-parse", "HEAD"]).strip()
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        entries = self._status_entries()
        tracked_entries = [entry for entry in entries if entry.xy != "??"]
        untracked_entries = self._untracked_entries(entries)

        tracked_patch_chunks = [self._tracked_patch(entry.git_path) for entry in tracked_entries]
        untracked_chunks = []
        untracked_hashes: dict[str, str] = {}
        file_stats = []

        for entry in tracked_entries:
            stat = self._tracked_file_stat(entry)
            file_stats.append(stat)

        for entry in untracked_entries:
            synthetic = self._synthetic_untracked_diff(entry)
            untracked_chunks.append(synthetic["patch"])
            untracked_hashes[entry.path] = synthetic["sha256"]
            file_stats.append(synthetic["stat"])

        patch = normalize_patch("".join(tracked_patch_chunks + untracked_chunks))
        untracked_hash_list = [
            {"path": path, "sha256": untracked_hashes[path]}
            for path in sorted(untracked_hashes)
        ]
        working_tree_hash = working_tree_hash_for(
            base_sha=base_sha,
            normalized_patch=patch,
            untracked_file_hashes=untracked_hash_list,
        )
        totals = {
            "files": len(file_stats),
            "additions": sum(int(item.get("additions") or 0) for item in file_stats),
            "deletions": sum(int(item.get("deletions") or 0) for item in file_stats),
        }
        risk_tags = sorted({tag for item in file_stats for tag in item.get("riskTags", [])})
        if totals["additions"] + totals["deletions"] >= 500:
            risk_tags.append("large_change")
        return {
            "created_at": _utc_now(),
            "workspace_root": str(self.workspace_root),
            "git_root": str(self.git_root),
            "branch": branch,
            "base_sha": base_sha,
            "working_tree_hash": working_tree_hash,
            "normalized_patch": patch,
            "patch_bytes": len(patch.encode("utf-8")),
            "untracked_file_hashes": untracked_hash_list,
            "file_stats": sorted(file_stats, key=lambda item: item.get("path") or ""),
            "totals": totals,
            "riskTags": sorted(set(risk_tags)),
        }

    def _ensure_git_root_allowed(self) -> None:
        root = str(self.workspace_root)
        git_root = str(self.git_root)
        if git_root == root or git_root.startswith(root + os.sep):
            return
        if root.startswith(git_root + os.sep):
            return
        raise ValueError("git root is outside workspace root: " + git_root)

    def _workspace_pathspec(self) -> str:
        try:
            relative = self.workspace_root.relative_to(self.git_root)
        except ValueError:
            return "."
        text = relative.as_posix()
        return text if text and text != "." else "."

    def _run_git(self, args: list[str], *, binary: bool = False) -> str:
        completed = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=str(getattr(self, "git_root", self.workspace_root)),
            text=not binary,
            encoding="utf-8" if not binary else None,
            errors="replace" if not binary else None,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "replace") if binary else completed.stderr
            stdout = completed.stdout.decode("utf-8", "replace") if binary else completed.stdout
            raise RuntimeError((stderr or stdout or "git command failed").strip())
        return completed.stdout.decode("utf-8", "replace") if binary else completed.stdout

    def _status_entries(self) -> list[StatusEntry]:
        output = self._run_git(["status", "--porcelain=v1", "--", self.pathspec])
        entries: list[StatusEntry] = []
        for line in output.splitlines():
            if not line:
                continue
            xy = line[:2]
            path_text = line[3:] if len(line) > 3 else ""
            paths = _porcelain_paths(path_text)
            if not paths:
                continue
            git_path = paths[-1]
            visible = self._visible_workspace_path(git_path)
            if not visible:
                continue
            previous = self._visible_workspace_path(paths[0]) if len(paths) > 1 else None
            entries.append(StatusEntry(xy=xy, git_path=git_path, path=visible, previous_path=previous))
        return entries

    def _untracked_entries(self, status_entries: list[StatusEntry]) -> list[StatusEntry]:
        output = self._run_git(["ls-files", "--others", "--exclude-standard", "-z", "--", self.pathspec])
        entries = []
        seen = set()
        for git_path in output.split("\0"):
            if not git_path or git_path in seen:
                continue
            seen.add(git_path)
            visible = self._visible_workspace_path(git_path)
            if visible:
                entries.append(StatusEntry(xy="??", git_path=git_path, path=visible))
        if entries:
            return entries
        return [entry for entry in status_entries if entry.xy == "??"]

    def _visible_workspace_path(self, git_path: str) -> str:
        absolute = (self.git_root / git_path).resolve(strict=False)
        try:
            relative = absolute.relative_to(self.workspace_root)
        except ValueError:
            return ""
        rel = relative.as_posix()
        if not rel or rel == "." or self.jail.restriction_reason(rel):
            return ""
        return rel

    def _tracked_patch(self, git_path: str) -> str:
        return self._run_git(
            ["diff", "--binary", "--no-ext-diff", "--no-textconv", "HEAD", "--", git_path]
        )

    def _tracked_file_stat(self, entry: StatusEntry) -> dict[str, Any]:
        additions = 0
        deletions = 0
        binary = False
        numstat = self._run_git(["diff", "--numstat", "HEAD", "--", entry.git_path])
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            if parts[0] == "-" or parts[1] == "-":
                binary = True
                continue
            additions += _safe_int(parts[0])
            deletions += _safe_int(parts[1])
        kind = _status_kind(entry.xy)
        return {
            "path": entry.path,
            "previousPath": entry.previous_path,
            "status": kind,
            "binary": binary,
            "additions": additions,
            "deletions": deletions,
            "riskTags": risk_tags_for_path(entry.path),
        }

    def _synthetic_untracked_diff(self, entry: StatusEntry) -> dict[str, Any]:
        path = (self.git_root / entry.git_path).resolve(strict=False)
        digest = _file_sha256(path)
        data = path.read_bytes()
        binary = _looks_binary(data) or len(data) > MAX_SYNTHETIC_TEXT_BYTES
        if binary:
            patch = (
                f"diff --git a/{entry.path} b/{entry.path}\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                f"+++ b/{entry.path}\n"
                f"Binary files /dev/null and b/{entry.path} differ\n"
            )
            additions = 0
        else:
            text = data.decode("utf-8")
            lines = text.splitlines()
            diff_lines = list(
                difflib.unified_diff(
                    [],
                    lines,
                    fromfile="/dev/null",
                    tofile=f"b/{entry.path}",
                    lineterm="",
                )
            )
            patch = "\n".join(diff_lines)
            if patch:
                patch += "\n"
            patch = f"diff --git a/{entry.path} b/{entry.path}\nnew file mode 100644\n" + patch
            additions = len(lines)
        return {
            "patch": patch,
            "sha256": digest,
            "stat": {
                "path": entry.path,
                "previousPath": None,
                "status": "untracked",
                "binary": binary,
                "additions": additions,
                "deletions": 0,
                "riskTags": risk_tags_for_path(entry.path),
            },
        }


def normalize_patch(patch: str) -> str:
    text = str(patch or "").replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def working_tree_hash_for(
    *,
    base_sha: str,
    normalized_patch: str,
    untracked_file_hashes: list[dict[str, str]],
) -> str:
    payload = {
        "base_sha": str(base_sha or ""),
        "normalized_patch_sha256": hashlib.sha256(
            normalize_patch(normalized_patch).encode("utf-8")
        ).hexdigest(),
        "untracked_file_hashes": sorted(
            [
                {"path": str(item.get("path") or ""), "sha256": str(item.get("sha256") or "")}
                for item in untracked_file_hashes
            ],
            key=lambda item: item["path"],
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def risk_tags_for_path(path: str) -> list[str]:
    text = str(path or "").replace("\\", "/")
    name = text.rsplit("/", 1)[-1].lower()
    lowered = text.lower()
    tags = []
    if name in {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements.txt", "pyproject.toml", "poetry.lock", "cargo.toml", "cargo.lock"}:
        tags.append("dependencies")
    if lowered.endswith((".sql", ".migration")) or "/migrations/" in lowered:
        tags.append("database")
    if lowered.endswith((".yml", ".yaml", ".toml", ".ini", ".json")):
        tags.append("config")
    if "/tests/" in lowered or "/test/" in lowered or name.startswith("test_") or name.endswith("_test.py"):
        tags.append("tests")
    if lowered.endswith((".sh", ".bash", ".zsh", ".ps1")):
        tags.append("script")
    return sorted(set(tags))


def _status_kind(xy: str) -> str:
    if "R" in xy:
        return "renamed"
    if "A" in xy:
        return "added"
    if "D" in xy:
        return "deleted"
    return "modified"


def _porcelain_paths(path_text: str) -> tuple[str, ...]:
    try:
        parts = shlex.split(str(path_text or ""))
    except ValueError:
        parts = []
    if len(parts) == 1:
        text = parts[0]
    else:
        text = str(path_text or "").strip().strip('"')
    return tuple(part.strip('"') for part in text.split(" -> ") if part.strip('"'))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_binary(data: bytes) -> bool:
    if b"\0" in data[:8192]:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
