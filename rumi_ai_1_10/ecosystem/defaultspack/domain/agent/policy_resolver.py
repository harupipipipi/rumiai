from __future__ import annotations

from typing import Any


HIGH_RISK_ACTIONS = {"external_send", "payment", "delete", "credential_input"}


class PolicyResolver:
    """Deny-first resolver across profile/agent/role/user/approval layers."""

    def resolve(self, *layers: dict[str, Any]) -> dict[str, Any]:
        allow: set[str] = set()
        deny: set[str] = set()
        model_allow: set[str] = set()
        model_deny: set[str] = set()
        approval_required: dict[str, bool] = {}
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            allow.update(str(item) for item in layer.get("tool_allowlist") or layer.get("allowlist") or layer.get("allowed_tools") or layer.get("tools") or [])
            deny.update(str(item) for item in layer.get("tool_denylist") or layer.get("denylist") or layer.get("disabled_tools") or layer.get("tool_blocklist") or [])
            model_allow.update(str(item) for item in layer.get("model_allowlist") or layer.get("allowed_models") or [])
            model_deny.update(str(item) for item in layer.get("model_denylist") or layer.get("blocked_models") or [])
            for key in (
                "write_actions_require_approval",
                "terminal_actions_require_approval",
                "external_send_requires_approval",
                "settings_mutation_requires_approval",
            ):
                if key in layer:
                    approval_required[key] = bool(layer[key])
        return {
            "tool_allowlist": sorted(allow - deny),
            "tool_denylist": sorted(deny),
            "model_allowlist": sorted(model_allow - model_deny),
            "model_denylist": sorted(model_deny),
            "approval_required": approval_required,
            "deny_precedence": True,
        }

    def tool_allowed(self, tool_name: str, policy: dict[str, Any]) -> bool:
        if tool_name in set(policy.get("tool_denylist") or []):
            return False
        allow = set(policy.get("tool_allowlist") or [])
        return not allow or tool_name in allow

    def is_tool_denied(self, tool_name: str, policy: dict[str, Any]) -> bool:
        return not self.tool_allowed(tool_name, policy)
