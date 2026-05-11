from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RumiResponse:
    text: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> "RumiResponse":
        return cls(
            text=str(result.get("assistant_text") or result.get("text") or ""),
            artifacts=list(result.get("artifacts") if isinstance(result.get("artifacts"), list) else []),
            metadata=dict(result.get("metadata") if isinstance(result.get("metadata"), dict) else {}),
        )
