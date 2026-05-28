from __future__ import annotations

from typing import Any


MIMO_CODING_COMPANY_PROFILE_ID = "defaultspack.mimo_coding_company"

_MIMO_AUTONOMOUS_TOOL_NAMES = {
    "coding_file_create",
    "coding_file_patch",
    "coding_file_write",
    "knowledge_create",
    "knowledge_get",
    "knowledge_list",
    "knowledge_search",
    "knowledge_update",
    "subagent",
    "todo",
}


def autonomous_tool_execution_allowed(
    tool_name: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> bool:
    if _profile_id(context) != MIMO_CODING_COMPANY_PROFILE_ID:
        return False

    normalized_tool_name = str(tool_name or "").strip()
    if normalized_tool_name in _MIMO_AUTONOMOUS_TOOL_NAMES:
        return True
    if normalized_tool_name != "rumi_api":
        return False

    payload = arguments if isinstance(arguments, dict) else {}
    action = str(payload.get("action") or "list_routes").strip()
    if action == "list_routes":
        return True
    if action != "request":
        return False
    return str(payload.get("method") or "GET").strip().upper() == "GET"


def _profile_id(context: dict[str, Any] | None) -> str:
    if not isinstance(context, dict):
        return ""
    return str(context.get("profile_id") or "").strip()
