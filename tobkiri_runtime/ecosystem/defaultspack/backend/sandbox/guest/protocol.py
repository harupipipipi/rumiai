from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..policy import desktop_input_audit_fields, validate_desktop_input_payload, validate_exec_payload


@dataclass(frozen=True)
class GuestExecRequest:
    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str]
    timeout_ms: int
    stdin: str | None
    client_request_id: str | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, require_request_id: bool = True) -> "GuestExecRequest":
        validated = validate_exec_payload(payload, require_request_id=require_request_id)
        return cls(**validated)

    def to_agent_payload(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "env": dict(self.env),
            "timeout_ms": self.timeout_ms,
            "stdin": self.stdin,
            "client_request_id": self.client_request_id,
        }


@dataclass(frozen=True)
class DesktopInputRequest:
    action: str
    client_action_id: str
    lease_token: str | None = None
    x: int | None = None
    y: int | None = None
    to_x: int | None = None
    to_y: int | None = None
    button: str | None = None
    delta_x: int | None = None
    delta_y: int | None = None
    text: str | None = None
    key: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        width: int | None = None,
        height: int | None = None,
        require_lease: bool = True,
    ) -> "DesktopInputRequest":
        validated = validate_desktop_input_payload(
            payload,
            width=width,
            height=height,
            require_lease=require_lease,
        )
        return cls(**validated)

    def to_agent_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action,
            "client_action_id": self.client_action_id,
            "lease_token": self.lease_token,
        }
        for field in ("x", "y", "to_x", "to_y", "button", "delta_x", "delta_y", "text", "key"):
            value = getattr(self, field)
            if value is not None:
                payload[field] = value
        return payload

    def audit_fields(self) -> dict[str, Any]:
        return desktop_input_audit_fields(self.to_agent_payload())
