from __future__ import annotations

from typing import Any

from domain.tool_policy.internal_context import (
    internal_tool_decision_allows,
    tool_server_approval_context_is_internal,
)
from domain.ui_compiler.service import commit_ui_plan, compile_ui_plan


def ui_compile_plan(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    return compile_ui_plan(arguments)


def ui_commit_plan(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return commit_ui_plan(
        arguments,
        workspace_root=_trusted_workspace(context),
        authorized=_authorized(context),
    )


def _authorized(context: dict[str, Any] | None) -> bool:
    return tool_server_approval_context_is_internal(context) or internal_tool_decision_allows(context)


def _trusted_workspace(context: dict[str, Any] | None) -> str | None:
    if not isinstance(context, dict):
        return None
    raw = context.get("conversation_workspace_dir") or context.get("workspace_dir")
    return str(raw) if raw else None
