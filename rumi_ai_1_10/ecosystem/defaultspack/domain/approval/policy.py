from __future__ import annotations

from typing import Any

from .store import classify_approval_risk, redact_secrets


def risk_level_for_action(action: str) -> str:
    return str(classify_approval_risk(action).get("risk_level") or "medium")


def redact_payload(value: Any) -> Any:
    return redact_secrets(value)
