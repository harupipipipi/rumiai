from __future__ import annotations

import re
from os import PathLike
from typing import Any

from blocks._common import error, ok
from domain.artifact.workspace import ArtifactWorkspace
from domain.chat.store import ChatStore


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

_FORMAT_ALIASES = {
    "text": ("text", ".txt", "text/plain"),
    "txt": ("text", ".txt", "text/plain"),
    "text/plain": ("text", ".txt", "text/plain"),
    "markdown": ("markdown", ".md", "text/markdown"),
    "md": ("markdown", ".md", "text/markdown"),
    "text/markdown": ("markdown", ".md", "text/markdown"),
    "text/x-markdown": ("markdown", ".md", "text/markdown"),
}


def run(input_data: dict[str, Any] | None, context: dict[str, Any] | None):
    payload = input_data if isinstance(input_data, dict) else {}
    conversation_id = str(payload.get("conversation_id") or "").strip()
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    requested_format = str(payload.get("format") or "text").strip().lower().lstrip(".")
    format_spec = _FORMAT_ALIASES.get(requested_format)
    if format_spec is None:
        return error("format must be one of: text, txt, markdown, md", "INVALID_INPUT")
    export_format, extension, mime_type = format_spec

    store = ChatStore()
    content = store.export_conversation(conversation_id, fmt=export_format)
    if content is None:
        return error("Conversation not found", "NOT_FOUND")

    workspace_context = dict(context or {})
    for key in ("artifact_root", "conversation_workspace_dir", "workspace_root"):
        value = workspace_context.get(key)
        if isinstance(value, PathLike):
            workspace_context[key] = str(value)
    if not any(
        isinstance(workspace_context.get(key), str) and workspace_context.get(key, "").strip()
        for key in ("artifact_root", "conversation_workspace_dir", "workspace_root")
    ):
        workspace_context["conversation_workspace_dir"] = str(store.conversation_workspace_dir(conversation_id))

    workspace = ArtifactWorkspace(workspace_context)
    relative_path = "context/" + _safe_filename(conversation_id) + extension
    target = workspace.resolve(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content), encoding="utf-8")

    path = workspace.relative(target)
    filename = target.name
    size = target.stat().st_size
    artifact = {
        "path": path,
        "filename": filename,
        "name": filename,
        "size": size,
        "format": export_format,
        "mime_type": mime_type,
    }
    return ok(
        {
            "path": path,
            "filename": filename,
            "name": filename,
            "size": size,
            "format": export_format,
            "mime_type": mime_type,
            "content_type": mime_type,
            "conversation_id": conversation_id,
            "artifacts": [artifact],
            "message": f"Materialized conversation context to {path}.",
        }
    )


def _safe_filename(value: str) -> str:
    safe = _SAFE_FILENAME_RE.sub("-", value.strip()).strip(".-")
    return safe[:100] or "conversation"
