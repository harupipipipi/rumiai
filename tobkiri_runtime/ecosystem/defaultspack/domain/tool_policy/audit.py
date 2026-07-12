from __future__ import annotations

from typing import Any

from core_runtime.runtime_audit_helpers import audit_event


def audit_tool_policy(context: dict[str, Any] | None, event_type: str, payload: dict[str, Any]) -> None:
    audit_event(context or {}, event_type, payload)
