from __future__ import annotations

import re
from os import PathLike
from typing import Any

from blocks._common import error, ok
from domain.artifact.workspace import ArtifactWorkspace
from domain.chat.store import ChatStore


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def run(input_data: dict[str, Any] | None, context: dict[str, Any] | None):
    payload = input_data if isinstance(input_data, dict) else {}
    conversation_id = str(payload.get("conversation_id") or "").strip()
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")

    fmt = str(payload.get("format") or "markdown").strip().lower()
    if fmt not in {"markdown", "text", "txt"}:
        return error("format must be 'markdown' or 'text'", "INVALID_INPUT")

    store = ChatStore()
    content = store.export_conversation(conversation_id, fmt="markdown")
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
    relative_path = "context/" + _safe_filename(conversation_id) + ".txt"
    target = workspace.resolve(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content), encoding="utf-8")

    path = workspace.relative(target)
    size = target.stat().st_size
    return ok(
        {
            "path": path,
            "size": size,
            "conversation_id": conversation_id,
            "message": f"Materialized conversation context to {path}.",
        }
    )


def _safe_filename(value: str) -> str:
    safe = _SAFE_FILENAME_RE.sub("-", value.strip()).strip(".-")
    return safe[:100] or "conversation"
