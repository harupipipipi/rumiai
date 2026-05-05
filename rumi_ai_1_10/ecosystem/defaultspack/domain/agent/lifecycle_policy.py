from __future__ import annotations

from typing import Any


class LifecyclePolicy:
    def evaluate(self, definition: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        if not definition.get("enabled", True):
            return {"allowed": False, "status": "blocked", "blocked_reason": "agent_disabled"}
        if state.get("status") == "paused":
            return {"allowed": False, "status": "paused", "blocked_reason": "manual_pause"}
        stop = definition.get("stop_conditions") if isinstance(definition.get("stop_conditions"), dict) else {}
        failure_count = int(state.get("failure_count") or 0)
        no_change_count = int(state.get("no_change_count") or 0)
        if stop.get("max_failures") is not None and failure_count >= int(stop["max_failures"]):
            return {"allowed": False, "status": "failed", "blocked_reason": "max_failures"}
        if stop.get("max_no_change_ticks") is not None and no_change_count >= int(stop["max_no_change_ticks"]):
            return {"allowed": False, "status": "completed", "blocked_reason": "max_no_change_ticks"}
        for key, reason in [
            ("approval_required", "approval_required"),
            ("login_required", "blocked_by_login"),
            ("captcha_required", "blocked_by_captcha"),
            ("network_error", "network_error"),
        ]:
            if state.get(key):
                return {"allowed": False, "status": "blocked", "blocked_reason": reason}
        return {"allowed": True, "status": "ready"}


class AgentLifecyclePolicy:
    def evaluate_stop_conditions(self, definition: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
        result = LifecyclePolicy().evaluate(definition, state)
        if result.get("allowed") is False:
            return [
                {
                    "code": result.get("blocked_reason") or result.get("status") or "blocked",
                    "message": result.get("blocked_reason") or "agent lifecycle guard blocked tick",
                }
            ]
        return []
