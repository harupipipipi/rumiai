from __future__ import annotations

from typing import Any

from domain.tool.autonomy import autonomous_tool_execution_allowed
from domain.tool.schema_adapter import policy_from_context, tool_name_from_definition
from domain.tool.security import is_safe_first_party_memo_tool, is_sandbox_capability_tool, untrusted_tool_security_rejection

from .models import PolicyDecision
from .risk import resolve_tool_risk
from .sandbox import choose_sandbox_mode


_APPROVAL_REQUIRED_NAME_PARTS = ("write", "create", "update", "delete", "patch", "commit", "push")
_WRITE_LIKE_RISKS = {
    "file_write",
    "file_delete",
    "git_write",
    "git_push",
    "external_message",
    "scheduler_create",
    "capability_mutation",
}


def decide_tool_policy(
    tool_def: Any,
    context: dict[str, Any] | None,
    *,
    tool_name: str = "",
    arguments: dict[str, Any] | None = None,
    approval_granted: bool = False,
) -> PolicyDecision:
    context = context if isinstance(context, dict) else {}
    policy = policy_from_context(context)
    name = tool_name or tool_name_from_definition(tool_def)
    risk = resolve_tool_risk(tool_def, name)
    if isinstance(tool_def, dict):
        security_rejection = untrusted_tool_security_rejection(tool_def)
        if security_rejection is not None:
            return PolicyDecision(False, risk, action="deny", reason=security_rejection, matched_by="tool_security")

    denylist = _list(policy.get("tool_denylist") or policy.get("disabled_tools") or policy.get("tool_blocklist"))
    if name in denylist:
        return PolicyDecision(False, risk, action="deny", reason="tool denied by policy", matched_by="tool_denylist", matched_value=name)
    allowlist = _list(policy.get("tool_allowlist") or policy.get("enabled_tools") or policy.get("allowed_tools"))
    if allowlist and name not in allowlist:
        return PolicyDecision(False, risk, action="deny", reason="tool not in allowlist", matched_by="tool_allowlist")

    if risk == "shell" and policy.get("allow_shell") is False:
        return PolicyDecision(False, risk, action="deny", reason="shell tools disabled", matched_by="allow_shell", matched_value="false")
    if risk in {"network", "browser"} and policy.get("allow_network") is False:
        return PolicyDecision(False, risk, action="deny", reason="network tools disabled", matched_by="allow_network", matched_value="false")
    if risk in {"file_write", "file_delete"} and policy.get("allow_file_write") is False:
        return PolicyDecision(False, risk, action="deny", reason="file writes disabled", matched_by="allow_file_write", matched_value="false")

    if autonomous_tool_execution_allowed(name, arguments, context):
        return PolicyDecision(
            True,
            risk,
            action="allow",
            sandbox_mode=choose_sandbox_mode(policy, risk),
            metadata={"autonomous_profile": str(context.get("profile_id") or "")},
        )

    requires_approval = _requires_approval(tool_def, policy, risk, name)
    if requires_approval and not approval_granted:
        return PolicyDecision(
            True,
            risk,
            action="ask",
            requires_approval=True,
            reason="approval required by policy",
            sandbox_mode=choose_sandbox_mode(policy, risk),
        )
    return PolicyDecision(True, risk, action="allow", sandbox_mode=choose_sandbox_mode(policy, risk))


def _requires_approval(tool_def: Any, policy: dict[str, Any], risk: str, name: str) -> bool:
    if _truthy(policy.get("yolo_mode")):
        return False
    if isinstance(tool_def, dict) and is_safe_first_party_memo_tool(tool_def):
        return False
    if isinstance(tool_def, dict) and is_sandbox_capability_tool(tool_def):
        return False
    if isinstance(tool_def, dict) and tool_def.get("requires_approval") is True:
        return True
    if _is_write_like_name(name):
        return True
    if risk in _WRITE_LIKE_RISKS:
        return True
    if policy.get("open_world_require_approval") is True and risk in {"network", "browser", "computer"}:
        return True
    if policy.get("destructive_actions_require_approval") is True and risk in {"file_delete", "git_push", "pack_install"}:
        return True
    if policy.get("write_actions_require_approval") is True and risk in _WRITE_LIKE_RISKS:
        return True
    return False


def _is_write_like_name(name: str) -> bool:
    lowered = str(name or "").lower()
    return any(part in lowered for part in _APPROVAL_REQUIRED_NAME_PARTS)


def _list(value: Any) -> set[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
