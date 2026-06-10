from __future__ import annotations

from typing import Any


SENSITIVE_TOOL_CONTEXT_KEYS = {
    "approval_granted",
    "_agent_approval_granted",
    "tool_policy_decision",
    "_tool_permission_decision",
    "_tool_permission_internal",
    "_tool_server_approved",
    "_tool_server_approval_token_valid",
    "_tool_server_approval_internal",
    "_tool_server_approval_token",
    "_tool_server_approval_operation",
    "_tool_server_approval_args_hash",
    "_tool_server_approval_pack_id",
    "_tool_server_approval_conversation_id",
}

UNTRUSTED_TOOL_CONTEXT_KEYS = SENSITIVE_TOOL_CONTEXT_KEYS | {
    "effective_tool_allowlist",
    "profile_policy",
    "runtime_profile",
    "_tool_server_approved",
    "_tool_server_approval_token_valid",
}

_INTERNAL_TOOL_PERMISSION = object()
_TOOL_SERVER_APPROVAL_INTERNAL = object()


def sanitize_tool_context(context: dict[str, Any] | None) -> dict[str, Any]:
    clean = dict(context or {}) if isinstance(context, dict) else {}
    for key in SENSITIVE_TOOL_CONTEXT_KEYS:
        clean.pop(key, None)
    return clean


def sanitize_untrusted_tool_context(context: dict[str, Any] | None) -> dict[str, Any]:
    clean = dict(context or {}) if isinstance(context, dict) else {}
    for key in UNTRUSTED_TOOL_CONTEXT_KEYS:
        clean.pop(key, None)
    return clean


def seal_tool_context(context: dict[str, Any] | None, decision: dict[str, Any]) -> dict[str, Any]:
    sealed = sanitize_tool_context(context)
    sealed["_tool_permission_decision"] = dict(decision or {})
    sealed["_tool_permission_internal"] = _INTERNAL_TOOL_PERMISSION
    return sealed


def mark_tool_server_approval_context(context: dict[str, Any]) -> dict[str, Any]:
    context["_tool_server_approved"] = True
    context["_tool_server_approval_token_valid"] = True
    context["_tool_server_approval_internal"] = _TOOL_SERVER_APPROVAL_INTERNAL
    return context


def tool_server_approval_context_is_internal(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    return context.get("_tool_server_approval_internal") is _TOOL_SERVER_APPROVAL_INTERNAL


def internal_tool_decision(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(context, dict):
        return None
    if context.get("_tool_permission_internal") is not _INTERNAL_TOOL_PERMISSION:
        return None
    decision = context.get("_tool_permission_decision")
    return dict(decision) if isinstance(decision, dict) else None


def internal_tool_decision_allows(context: dict[str, Any] | None) -> bool:
    decision = internal_tool_decision(context)
    return bool(decision and decision.get("action") == "allow" and decision.get("allowed"))
