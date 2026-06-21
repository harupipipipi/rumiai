from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


RAW_COMMAND_REJECTED = "RAW_COMMAND_REJECTED"
INVALID_EXEC_REQUEST = "INVALID_EXEC_REQUEST"
INVALID_DESKTOP_INPUT = "INVALID_DESKTOP_INPUT"
INVALID_SANDBOX_ID = "INVALID_SANDBOX_ID"
INVALID_PROVIDER_ID = "INVALID_PROVIDER_ID"
RUNTIME_PROVIDER_UNAVAILABLE = "RUNTIME_PROVIDER_UNAVAILABLE"
DESKTOP_CONTROL_CONFLICT = "DESKTOP_CONTROL_CONFLICT"
DESKTOP_LEASE_REQUIRED = "DESKTOP_LEASE_REQUIRED"
DESKTOP_LEASE_INVALID = "DESKTOP_LEASE_INVALID"
DESKTOP_LEASE_EXPIRED = "DESKTOP_LEASE_EXPIRED"
FRAME_NOT_FOUND = "FRAME_NOT_FOUND"
FRAME_NOT_MODIFIED = "FRAME_NOT_MODIFIED"


@dataclass
class SandboxContractError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "code": self.code,
            "error": self.message,
            "status_code": self.status_code,
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload


class RequestValidationError(SandboxContractError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        status_code: int = 400,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})
        if field is not None:
            merged["field"] = field
        super().__init__(code=code, message=message, status_code=status_code, details=merged)


def contract_error_response(exc: SandboxContractError) -> dict[str, Any]:
    return exc.to_dict()
