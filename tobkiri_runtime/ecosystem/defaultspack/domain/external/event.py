from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .principal import ExternalPrincipal, principal_from
from .redaction import redact_sensitive


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class ExternalEvent:
    provider: str
    workspace: ExternalPrincipal
    scope: ExternalPrincipal
    actor: ExternalPrincipal
    conversation: ExternalPrincipal
    event: dict[str, Any]
    payload: dict[str, Any]
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    received_at: int = field(default_factory=_now_ms)

    def as_dict(self, *, redact: bool = True) -> dict[str, Any]:
        payload = dict(self.payload)
        metadata = dict(self.metadata)
        if redact:
            payload = redact_sensitive(payload)
            metadata = redact_sensitive(metadata)
        return {
            "provider": self.provider,
            "workspace": self.workspace.as_dict(),
            "scope": self.scope.as_dict(),
            "actor": self.actor.as_dict(),
            "conversation": self.conversation.as_dict(),
            "event": dict(self.event),
            "payload": payload,
            "verified": bool(self.verified),
            "metadata": metadata,
            "received_at": self.received_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExternalEvent":
        return cls(
            provider=str(value.get("provider") or ""),
            workspace=principal_from(value.get("workspace"), default_type="unknown"),
            scope=principal_from(value.get("scope"), default_type="unknown"),
            actor=principal_from(value.get("actor"), default_type="unknown"),
            conversation=principal_from(value.get("conversation"), default_type="external"),
            event=dict(value.get("event") if isinstance(value.get("event"), dict) else {}),
            payload=dict(value.get("payload") if isinstance(value.get("payload"), dict) else {}),
            verified=bool(value.get("verified")),
            metadata=dict(value.get("metadata") if isinstance(value.get("metadata"), dict) else {}),
            received_at=int(value.get("received_at") or _now_ms()),
        )
