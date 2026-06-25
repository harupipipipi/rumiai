from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..policy import validate_exec_payload


@dataclass(frozen=True)
class GuestExecRequest:
    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str]
    timeout_ms: int
    stdin: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "GuestExecRequest":
        return cls(**validate_exec_payload(payload))

    def to_agent_payload(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "env": dict(self.env),
            "timeout_ms": self.timeout_ms,
            "stdin": self.stdin,
        }
