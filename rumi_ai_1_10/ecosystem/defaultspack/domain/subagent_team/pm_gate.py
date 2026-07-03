from __future__ import annotations

from typing import Any

from .mention_parser import sanitize_agent_mentions_for_gate


PM_AGENT_IDS = {"project_manager", "operations_manager"}
CREATOR_AGENT_IDS = {"creator", "client_manager", "president", "user"}


def pm_gate_decision(
    *,
    sender_id: str,
    content: str,
    target_agent_ids: list[str] | None = None,
    rich_requested: bool = False,
    action: str = "message",
    project_manager_id: str = "project_manager",
) -> dict[str, Any]:
    sender = str(sender_id or "user").strip().lower()
    targets = _dedupe(target_agent_ids or [])
    direct_targets = [target for target in targets if target not in PM_AGENT_IDS]
    sender_is_pm = sender in PM_AGENT_IDS or sender == str(project_manager_id or "").strip().lower()
    lifecycle_action = str(action or "").lower() in {
        "create_agent",
        "update_agent",
        "archive_agent",
        "create_channel",
        "update_channel",
        "archive_channel",
        "create_goal",
        "update_goal",
        "close_goal",
    }
    requires_pm = bool(direct_targets and not sender_is_pm)
    if rich_requested and direct_targets and not sender_is_pm:
        requires_pm = True
    reason = ""
    if requires_pm:
        reason = "direct specialist routing requires project manager gate"
    elif lifecycle_action:
        reason = "creator lifecycle change; no tool execution"
    else:
        reason = "pm gate not required"
    routed_targets = [project_manager_id] if requires_pm else targets
    return {
        "requires_pm": requires_pm,
        "allowed": True,
        "reason": reason,
        "sender_id": sender or "user",
        "requested_target_agent_ids": targets,
        "target_agent_ids": routed_targets,
        "route": "pm_gate" if requires_pm else "direct_team_route",
        "project_manager_id": project_manager_id,
        "lifecycle_action": lifecycle_action,
    }


def gated_content(*, content: str, sender_id: str, gate: dict[str, Any]) -> str:
    if not gate.get("requires_pm"):
        return str(content or "")
    requested = ", ".join(gate.get("requested_target_agent_ids") or []) or "unspecified"
    safe_original = sanitize_agent_mentions_for_gate(content)
    return (
        "@"
        + str(gate.get("project_manager_id") or "project_manager")
        + " PM gate request from "
        + str(sender_id or "user")
        + ". Requested targets: "
        + requested
        + ".\n\nOriginal request:\n"
        + safe_original
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip().lstrip("@").lower()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
