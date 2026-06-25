from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


SANDBOX_RUNTIME_UNAVAILABLE = "SANDBOX_RUNTIME_UNAVAILABLE"
SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE = "SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE"
INVALID_SANDBOX_POLICY = "INVALID_SANDBOX_POLICY"
INVALID_PROVIDER_ID = "INVALID_PROVIDER_ID"
RUNTIME_PROVIDER_UNAVAILABLE = "RUNTIME_PROVIDER_UNAVAILABLE"


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
            "success": False,
            "code": self.code,
            "error": self.message,
            "status_code": self.status_code,
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload
