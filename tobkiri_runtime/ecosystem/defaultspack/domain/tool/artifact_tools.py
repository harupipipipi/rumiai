from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.coding.file_ops import FileOps

from ._agent_os_common import err, ok, read_text_file, simple_diff, workspace, zip_path


def _file_ops(root: Path) -> FileOps:
    return FileOps(str(root))


def artifact_file_read(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        resolved = ws.resolve(path, must_exist=True)
        if not resolved.is_file():
            return err("artifact path is not a file", "NOT_FILE")
        rel_path = ws.relative(resolved)
        content = _file_ops(ws.root).read_file(rel_path)
        return ok({"path": rel_path, "content": content, "size": len(content.encode("utf-8"))})
    except Exception as exc:
        return err(str(exc), "READ_FAILED")


def artifact_file_write(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    content = str(arguments.get("content") or "")
    try:
        ws = workspace(context)
        ops = _file_ops(ws.root)
        before = ""
        resolved = ws.resolve(path)
        if resolved.exists() and resolved.is_file():
            before = read_text_file(resolved)
        checkpoint = None
        if arguments.get("checkpoint", True) is not False:
            checkpoint = ops.checkpoint_before_mutation("artifact.file.write", [path], metadata={"path": path})
        size = ops.write_file(path, content)
        data = {
            "path": path,
            "size": size,
            "diff": simple_diff(before, content, path=path),
            "checkpoint": checkpoint,
        }
        return ok(data)
    except Exception as exc:
        return err(str(exc), "WRITE_FAILED")


def artifact_file_patch(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    old_text = arguments.get("old_text")
    new_text = arguments.get("new_text")
    if not path or old_text is None or new_text is None:
        return err("'path', 'old_text', and 'new_text' are required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        resolved = ws.resolve(path, must_exist=True)
        content = read_text_file(resolved)
        count = content.count(str(old_text))
        expected = arguments.get("expected_replacements", 1)
        expected = int(expected) if expected is not None else count
        if count != expected:
            return err(
                f"expected {expected} replacements but found {count}",
                "REPLACEMENT_COUNT_MISMATCH",
                found=count,
                expected=expected,
            )
        updated = content.replace(str(old_text), str(new_text), expected)
        ops = _file_ops(ws.root)
        checkpoint = None
        if arguments.get("checkpoint", True) is not False:
            checkpoint = ops.checkpoint_before_mutation("artifact.file.patch", [path], metadata={"path": path})
        size = ops.write_file(path, updated)
        return ok(
            {
                "path": path,
                "patched": True,
                "replacements": expected,
                "size": size,
                "diff": simple_diff(content, updated, path=path),
                "checkpoint": checkpoint,
            }
        )
    except Exception as exc:
        return err(str(exc), "PATCH_FAILED")


def artifact_file_delete(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    path = str(arguments.get("path") or "")
    if not path:
        return err("'path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        ops = _file_ops(ws.root)
        checkpoint = None
        if arguments.get("checkpoint", True) is not False:
            checkpoint = ops.checkpoint_before_mutation("artifact.file.delete", [path], metadata={"path": path})
        ops.delete_file(path)
        return ok({"path": path, "deleted": True, "checkpoint": checkpoint})
    except Exception as exc:
        return err(str(exc), "DELETE_FAILED")


def artifact_file_list(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    base_path = str(arguments.get("path") or ".")
    recursive = bool(arguments.get("recursive", False))
    include_hidden = bool(arguments.get("include_hidden", False))
    max_entries = int(arguments.get("max_entries") or 200)
    try:
        ws = workspace(context)
        base = ws.resolve(base_path, must_exist=True, allow_root=True)
        if not base.is_dir():
            return err("artifact path is not a directory", "NOT_DIRECTORY")
        entries = []
        iterator = base.rglob("*") if recursive else base.iterdir()
        for item in sorted(iterator):
            rel = ws.relative(item)
            if not include_hidden and any(part.startswith(".") for part in rel.split("/")):
                continue
            entries.append(
                {
                    "name": item.name,
                    "path": rel,
                    "is_dir": item.is_dir(),
                    "size": 0 if item.is_dir() else item.stat().st_size,
                }
            )
            if len(entries) >= max_entries:
                break
        return ok({"path": ws.relative(base) if base != ws.root else ".", "entries": entries})
    except Exception as exc:
        return err(str(exc), "LIST_FAILED")


def artifact_zip(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    source_path = str(arguments.get("path") or arguments.get("source_path") or ".")
    output_path = str(arguments.get("output_path") or "artifact.zip")
    try:
        ws = workspace(context)
        source = ws.resolve(source_path, must_exist=True, allow_root=True)
        output = ws.resolve(output_path)
        data = zip_path(source, output, root=ws.root)
        data["source_path"] = ws.relative(source) if source != ws.root else "."
        return ok(data)
    except Exception as exc:
        return err(str(exc), "ZIP_FAILED")
