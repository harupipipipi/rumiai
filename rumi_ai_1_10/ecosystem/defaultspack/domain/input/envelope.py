from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RumiInputEnvelope:
    role: str
    input: str
    chat: dict[str, Any]
    source: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    tools: list[Any] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "input": self.input,
            "chat": dict(self.chat),
            "source": dict(self.source),
            "metadata": dict(self.metadata),
            "params": dict(self.params),
            "tools": list(self.tools),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RumiInputEnvelope":
        return cls(
            role=str(value.get("role") or "user"),
            input=str(value.get("input") or value.get("content") or ""),
            chat=dict(value.get("chat") if isinstance(value.get("chat"), dict) else {}),
            source=dict(value.get("source") if isinstance(value.get("source"), dict) else {}),
            metadata=dict(value.get("metadata") if isinstance(value.get("metadata"), dict) else {}),
            params=dict(value.get("params") if isinstance(value.get("params"), dict) else {}),
            tools=list(value.get("tools") if isinstance(value.get("tools"), list) else []),
        )
