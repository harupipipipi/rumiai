from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RumiInputEnvelope:
    role: str
    input: str
    chat: dict[str, Any]
    source: dict[str, Any]
    target: dict[str, Any] = field(default_factory=dict)
    delivery: dict[str, Any] = field(default_factory=dict)
    attachments: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    tools: list[Any] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "input": self.input,
            "chat": dict(self.chat),
            "source": dict(self.source),
            "target": dict(self.target),
            "delivery": dict(self.delivery),
            "attachments": list(self.attachments),
            "metadata": dict(self.metadata),
            "params": dict(self.params),
            "tools": list(self.tools),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RumiInputEnvelope":
        delivery = dict(value.get("delivery") if isinstance(value.get("delivery"), dict) else {})
        delivery.setdefault("action_id", str(delivery.get("action_id") or value.get("action_id") or "chat.message"))
        return cls(
            role=str(value.get("role") or "user"),
            input=str(value.get("input") or value.get("content") or ""),
            chat=dict(value.get("chat") if isinstance(value.get("chat"), dict) else {}),
            source=dict(value.get("source") if isinstance(value.get("source"), dict) else {}),
            target=dict(value.get("target") if isinstance(value.get("target"), dict) else {}),
            delivery=delivery,
            attachments=list(value.get("attachments") if isinstance(value.get("attachments"), list) else []),
            metadata=dict(value.get("metadata") if isinstance(value.get("metadata"), dict) else {}),
            params=dict(value.get("params") if isinstance(value.get("params"), dict) else {}),
            tools=list(value.get("tools") if isinstance(value.get("tools"), list) else []),
        )
