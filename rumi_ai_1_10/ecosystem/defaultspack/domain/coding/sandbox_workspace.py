from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.coding.file_ops import CHECKPOINT_SKIPPED_DIRS, FileOps
from domain.coding.workspace_jail import (
    PROTECTED_PATH_PARTS,
    SECRET_FILE_NAMES,
    SECRET_PATH_PARTS,
    SECRET_SUFFIXES,
    WorkspaceJail,
)
from domain.coding.workspace_resolver import WorkspaceResolver


MAX_SANDBOX_WORKSPACE_FILES = 4000
MAX_SANDBOX_WORKSPACE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_SANDBOX_WORKSPACE_FILE_BYTES = 4 * 1024 * 1024
MAX_SANDBOX_DIFF_CHARS = 120_000
MAX_SANDBOX_ARTIFACT_BYTES = 32 * 1024 * 1024
SANDBOX_STATE_SCHEMA = 1


@dataclass(frozen=True)
class SandboxWorkspace:
    sandbox_id: str
    state_root: Path
    base_root: Path
    work_root: Path
    artifact_root: Path
    host_workspace_root: Path
    workspace_id: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "sandbox_workspace_root": str(self.work_root),
            "sandbox_artifact_root": str(self.artifact_root),
            "host_workspace_root": str(self.host_workspace_root),
            "workspace_id": self.workspace_id,
            "execution_boundary": "sandbox_workspace",
        }


class SandboxWorkspaceManager:
    """Maintain copy-on-write coding workspaces for sandbox-only tools."""

    def __init__(self, state_dir: str | os.PathLike[str] | None = None) -> None:
        self.state_dir = Path(state_dir) if state_dir is not None else _default_state_dir()

    def prepare(self, input_data: dict[str, Any] | None, context: dict[str, Any] | None) -> SandboxWorkspace:
        args = input_data or {}
        ctx = context or {}
        resolution = WorkspaceResolver().resolve(args, ctx, allow_cwd_fallback=True)
        host_root = Path(resolution.root_path).expanduser().resolve()
        if not host_root.is_dir():
            raise ValueError("workspace root must exist")
        sandbox_id = _sandbox_id(args, ctx, host_root)
        state_root = (self.state_dir / sandbox_id).resolve()
        base_root = state_root / "base"
        work_root = state_root / "work"
        artifact_root = state_root / "artifacts"
        manifest_path = state_root / "manifest.json"
        reset = args.get("reset") is True or args.get("fresh") is True
        existing_manifest = _read_json(manifest_path)
        can_reuse = (
            not reset
            and base_root.is_dir()
            and work_root.is_dir()
            and existing_manifest.get("schema") == SANDBOX_STATE_SCHEMA
            and existing_manifest.get("host_workspace_root") == str(host_root)
        )
        if not can_reuse:
            if state_root.exists():
                shutil.rmtree(state_root)
            state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            stage_audit = _stage_workspace(host_root, base_root, include_paths=args.get("include_paths"))
            shutil.copytree(base_root, work_root, symlinks=False)
            artifact_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_json(
                manifest_path,
                {
                    "schema": SANDBOX_STATE_SCHEMA,
                    "sandbox_id": sandbox_id,
                    "host_workspace_root": str(host_root),
                    "workspace_id": resolution.workspace_id,
                    "created_at": _now(),
                    "updated_at": _now(),
                    "stage_audit": stage_audit,
                },
            )
        else:
            artifact_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            existing_manifest["updated_at"] = _now()
            _write_json(manifest_path, existing_manifest)
        return SandboxWorkspace(
            sandbox_id=sandbox_id,
            state_root=state_root,
            base_root=base_root,
            work_root=work_root,
            artifact_root=artifact_root,
            host_workspace_root=host_root,
            workspace_id=resolution.workspace_id,
        )

    def read_file(
        self,
        workspace: SandboxWorkspace,
        path: Any,
        *,
        start_line: Any = None,
        end_line: Any = None,
        max_chars: Any = None,
    ) -> dict[str, Any]:
        ops = FileOps(workspace.work_root)
        if start_line is not None or end_line is not None:
            window = ops.read_file_lines(path, start_line=_optional_int(start_line), end_line=_optional_int(end_line))
            content = window["content"]
            payload = {
                "path": str(path),
                "content": content,
                "size": len(content.encode("utf-8")),
                "encoding": "utf-8",
                **window,
            }
        else:
            content = ops.read_file(path)
            payload = {
                "path": str(path),
                "content": content,
                "size": len(content.encode("utf-8")),
                "encoding": "utf-8",
            }
        clipped, truncated, omitted = _clip_text(payload["content"], _max_chars(max_chars))
        if truncated:
            payload["content"] = clipped
            payload["truncated"] = True
            payload["omitted_chars"] = omitted
        return {**payload, **workspace.to_public_dict()}

    def write_file(self, workspace: SandboxWorkspace, path: Any, content: Any) -> dict[str, Any]:
        ops = FileOps(workspace.work_root)
        before_diff = ops.diff_text(path, str(content))
        size = ops.write_file(path, str(content))
        preview = self.diff_preview(workspace)
        return {
            "path": str(path),
            "size": size,
            "written": True,
            "host_modified": False,
            "sandbox_only": True,
            "diff": before_diff,
            **_change_summary(preview),
            **workspace.to_public_dict(),
        }

    def patch_file(self, workspace: SandboxWorkspace, path: Any, old: Any, new: Any) -> dict[str, Any]:
        ops = FileOps(workspace.work_root)
        result = ops.apply_patch_text(path, str(old), str(new))
        preview = self.diff_preview(workspace)
        return {
            **result,
            "host_modified": False,
            "sandbox_only": True,
            **_change_summary(preview),
            **workspace.to_public_dict(),
        }

    def diff_preview(self, workspace: SandboxWorkspace, *, max_chars: Any = None) -> dict[str, Any]:
        budget = _max_chars(max_chars) or MAX_SANDBOX_DIFF_CHARS
        changed = _changed_files(workspace.base_root, workspace.work_root)
        diff_parts: list[str] = []
        truncated = False
        for item in changed:
            if len("".join(diff_parts)) >= budget:
                truncated = True
                break
            text = _unified_diff_for_change(workspace.base_root, workspace.work_root, item, budget - len("".join(diff_parts)))
            if text:
                diff_parts.append(text)
        diff_text = "".join(diff_parts)
        if len(diff_text) > budget:
            diff_text = diff_text[: max(0, budget - 28)].rstrip() + "\n[diff truncated]\n"
            truncated = True
        return {
            "changed_files": changed,
            "changed_file_count": len(changed),
            "diff": diff_text,
            "diff_truncated": truncated,
            "diff_summary": _diff_summary(changed),
            "host_modified": False,
            "sandbox_only": True,
            **workspace.to_public_dict(),
        }

    def export_artifacts(self, workspace: SandboxWorkspace, paths: Any = None) -> dict[str, Any]:
        changed = self.diff_preview(workspace)["changed_files"]
        requested = _artifact_paths(paths, changed)
        export_id = "art_" + uuid.uuid4().hex[:12]
        export_root = workspace.artifact_root / export_id
        export_root.mkdir(mode=0o700, parents=True, exist_ok=False)
        copied: list[dict[str, Any]] = []
        total_bytes = 0
        jail = WorkspaceJail(workspace.work_root)
        for raw_path in requested:
            source = jail.resolve_user_path(raw_path)
            rel = jail.relative(source)
            jail.ensure_allowed(rel, operation="artifact_export")
            if not source.exists():
                continue
            target = export_root / rel
            if source.is_dir():
                bytes_used, files = _copy_artifact_tree(source, target, total_bytes)
                total_bytes += bytes_used
                copied.extend(files)
            else:
                size = source.stat().st_size
                if total_bytes + size > MAX_SANDBOX_ARTIFACT_BYTES:
                    raise ValueError("sandbox artifact export is too large")
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copy2(source, target)
                total_bytes += size
                copied.append({"path": rel, "artifact_path": str(target), "size": size})
        return {
            "artifact_id": export_id,
            "artifact_root": str(export_root),
            "artifact_paths": [item["artifact_path"] for item in copied],
            "files": copied,
            "total_bytes": total_bytes,
            "host_modified": False,
            "sandbox_only": True,
            **workspace.to_public_dict(),
        }


def _default_state_dir() -> Path:
    override = os.environ.get("RUMI_SANDBOX_CODING_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "sandbox_coding"


def _sandbox_id(args: dict[str, Any], context: dict[str, Any], host_root: Path) -> str:
    raw = (
        args.get("sandbox_id")
        or args.get("sandbox_workspace_id")
        or context.get("sandbox_id")
        or context.get("conversation_id")
        or context.get("chat_id")
    )
    if isinstance(raw, str) and raw.strip():
        candidate = raw.strip()
    else:
        seed = "|".join(
            str(value or "")
            for value in (
                host_root,
                context.get("principal_id"),
                context.get("pack_id"),
                context.get("_source_pack_id"),
            )
        )
        candidate = "sbx_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    safe = "".join(ch if ch.isalnum() or ch in "_.:-" else "_" for ch in candidate)[:96]
    return safe if safe.startswith("sbx_") else "sbx_" + safe


def _stage_workspace(source_root: Path, target_root: Path, *, include_paths: Any = None) -> dict[str, int]:
    target_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    roots = _selected_stage_roots(source_root, include_paths)
    audit = {"files": 0, "bytes": 0, "skipped": 0}
    for source in roots:
        if source.is_file():
            _stage_file(source_root, source, target_root, audit)
        elif source.is_dir():
            for current, dirs, files in os.walk(source, topdown=True, followlinks=False):
                current_path = Path(current)
                rel_dir = current_path.relative_to(source_root)
                dirs[:] = [
                    name
                    for name in dirs
                    if not _should_skip_rel((rel_dir / name).as_posix())
                    and not _is_special_or_link(current_path / name)
                ]
                (target_root / rel_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
                for file_name in files:
                    file_path = current_path / file_name
                    if _should_skip_rel((rel_dir / file_name).as_posix()) or _is_special_or_link(file_path):
                        audit["skipped"] += 1
                        continue
                    _stage_file(source_root, file_path, target_root, audit)
    return audit


def _selected_stage_roots(source_root: Path, include_paths: Any) -> list[Path]:
    if include_paths in (None, "", []):
        return [source_root]
    values = include_paths if isinstance(include_paths, list) else [include_paths]
    jail = WorkspaceJail(source_root)
    roots: list[Path] = []
    for value in values:
        resolved = jail.resolve_user_path(value)
        rel = jail.relative(resolved)
        jail.ensure_allowed(rel, operation="sandbox_stage")
        roots.append(resolved)
    return roots or [source_root]


def _stage_file(source_root: Path, source: Path, target_root: Path, audit: dict[str, int]) -> None:
    try:
        stat_result = source.stat()
    except OSError:
        audit["skipped"] += 1
        return
    if not stat.S_ISREG(stat_result.st_mode) or stat_result.st_nlink > 1:
        audit["skipped"] += 1
        return
    size = int(stat_result.st_size)
    if size > MAX_SANDBOX_WORKSPACE_FILE_BYTES:
        audit["skipped"] += 1
        return
    if audit["files"] + 1 > MAX_SANDBOX_WORKSPACE_FILES:
        raise ValueError("sandbox workspace has too many files")
    if audit["bytes"] + size > MAX_SANDBOX_WORKSPACE_TOTAL_BYTES:
        raise ValueError("sandbox workspace is too large")
    rel = source.relative_to(source_root)
    target = target_root / rel
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copy2(source, target)
    os.chmod(target, stat_result.st_mode & 0o700)
    audit["files"] += 1
    audit["bytes"] += size


def _should_skip_rel(rel: str) -> bool:
    parts = tuple(part for part in str(rel or "").replace("\\", "/").split("/") if part)
    if not parts:
        return False
    if any(part in PROTECTED_PATH_PARTS for part in parts):
        return True
    if any(part in SECRET_PATH_PARTS for part in parts):
        return True
    if parts[0] in CHECKPOINT_SKIPPED_DIRS:
        return True
    name = parts[-1].lower()
    if name == ".env" or (name.startswith(".env.") and not name.endswith((".example", ".sample", ".template"))):
        return True
    if name in SECRET_FILE_NAMES or name.endswith(SECRET_SUFFIXES):
        return True
    return False


def _is_special_or_link(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return True
    return not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) or stat.S_ISLNK(mode)


def _changed_files(base_root: Path, work_root: Path) -> list[dict[str, Any]]:
    base_files = _file_map(base_root)
    work_files = _file_map(work_root)
    changed: list[dict[str, Any]] = []
    for rel in sorted(set(base_files) | set(work_files)):
        base = base_files.get(rel)
        work = work_files.get(rel)
        if base is None:
            changed.append({"path": rel, "status": "added", "size": work.stat().st_size if work else 0})
        elif work is None:
            changed.append({"path": rel, "status": "deleted", "size": base.stat().st_size})
        elif _sha256(base) != _sha256(work):
            changed.append({"path": rel, "status": "modified", "size": work.stat().st_size})
    return changed


def _file_map(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if not root.is_dir():
        return result
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if not _should_skip_rel((current_path / name).relative_to(root).as_posix())]
        for name in files:
            path = current_path / name
            if path.is_file():
                result[path.relative_to(root).as_posix()] = path
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unified_diff_for_change(base_root: Path, work_root: Path, change: dict[str, Any], budget: int) -> str:
    if budget <= 0:
        return ""
    rel = str(change.get("path") or "")
    old_path = base_root / rel
    new_path = work_root / rel
    old_text = "" if change.get("status") == "added" else _read_text_for_diff(old_path)
    new_text = "" if change.get("status") == "deleted" else _read_text_for_diff(new_path)
    if old_text is None or new_text is None:
        return f"diff -- {rel}\n[binary or too-large file omitted]\n"
    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            lineterm="",
        )
    )
    if not diff.endswith("\n"):
        diff += "\n"
    if len(diff) > budget:
        return diff[: max(0, budget - 28)].rstrip() + "\n[diff truncated]\n"
    return diff


def _read_text_for_diff(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_SANDBOX_WORKSPACE_FILE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def _diff_summary(changed: list[dict[str, Any]]) -> str:
    if not changed:
        return "Sandbox has no file changes."
    counts: dict[str, int] = {}
    for item in changed:
        status = str(item.get("status") or "modified")
        counts[status] = counts.get(status, 0) + 1
    parts = [f"{count} {status}" for status, count in sorted(counts.items())]
    return "Sandbox changed {} file(s): {}.".format(len(changed), ", ".join(parts))


def _change_summary(preview: dict[str, Any]) -> dict[str, Any]:
    return {
        "changed_files": preview.get("changed_files", []),
        "changed_file_count": preview.get("changed_file_count", 0),
        "diff_summary": preview.get("diff_summary", ""),
    }


def _artifact_paths(paths: Any, changed: list[dict[str, Any]]) -> list[str]:
    if paths in (None, "", []):
        return [str(item.get("path") or "") for item in changed if item.get("status") != "deleted"]
    values = paths if isinstance(paths, list) else [paths]
    return [str(value) for value in values if str(value).strip()]


def _copy_artifact_tree(source: Path, target: Path, current_bytes: int) -> tuple[int, list[dict[str, Any]]]:
    copied: list[dict[str, Any]] = []
    total = 0
    for current, dirs, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_dir = current_path.relative_to(source)
        dirs[:] = [name for name in dirs if not _should_skip_rel((rel_dir / name).as_posix())]
        for name in files:
            item = current_path / name
            if not item.is_file():
                continue
            rel = rel_dir / name
            size = item.stat().st_size
            if current_bytes + total + size > MAX_SANDBOX_ARTIFACT_BYTES:
                raise ValueError("sandbox artifact export is too large")
            dest = target / rel
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            total += size
            copied.append({"path": rel.as_posix(), "artifact_path": str(dest), "size": size})
    return total, copied


def _clip_text(text: Any, max_chars: int | None) -> tuple[str, bool, int]:
    content = str(text or "")
    if max_chars is None or len(content) <= max_chars:
        return content, False, 0
    clipped = content[: max(0, max_chars - 24)].rstrip() + "\n[truncated]"
    return clipped, True, len(content) - len(clipped)


def _max_chars(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("max_chars must be > 0")
    return min(max(parsed, 200), MAX_SANDBOX_DIFF_CHARS)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
