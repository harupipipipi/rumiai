from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.external.redaction import redact_sensitive


@dataclass
class WebhookEndpoint:
    id: str
    kind: str
    input_profile_id: str
    audience_policy_id: str = ""
    response_profile_id: str = ""
    security: dict[str, Any] = field(default_factory=dict)
    target: dict[str, Any] = field(default_factory=dict)
    default_delivery: dict[str, Any] = field(default_factory=dict)
    allowed_delivery_actions: list[str] = field(default_factory=list)
    ttl_seconds: int | None = None
    expires_at: int | None = None
    conversation: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    public_url: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, *, redact: bool = True) -> dict[str, Any]:
        security = dict(self.security)
        metadata = dict(self.metadata)
        if redact:
            security = redact_sensitive(security)
            metadata = redact_sensitive(metadata)
        return {
            "id": self.id,
            "kind": self.kind,
            "input_profile_id": self.input_profile_id,
            "audience_policy_id": self.audience_policy_id,
            "response_profile_id": self.response_profile_id,
            "security": security,
            "target": dict(self.target),
            "default_delivery": dict(self.default_delivery),
            "allowed_delivery_actions": list(self.allowed_delivery_actions),
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at,
            "conversation": dict(self.conversation),
            "response": dict(self.response),
            "enabled": bool(self.enabled),
            "public_url": dict(self.public_url),
            "metadata": metadata,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WebhookEndpoint":
        return cls(
            id=str(value.get("id") or ""),
            kind=str(value.get("kind") or "generic"),
            input_profile_id=str(value.get("input_profile_id") or "generic.webhook.default"),
            audience_policy_id=str(value.get("audience_policy_id") or ""),
            response_profile_id=str(value.get("response_profile_id") or ""),
            security=dict(value.get("security") if isinstance(value.get("security"), dict) else {}),
            target=dict(value.get("target") if isinstance(value.get("target"), dict) else {}),
            default_delivery=dict(value.get("default_delivery") if isinstance(value.get("default_delivery"), dict) else {}),
            allowed_delivery_actions=[
                str(item).strip()
                for item in (value.get("allowed_delivery_actions") if isinstance(value.get("allowed_delivery_actions"), list) else [])
                if str(item or "").strip()
            ],
            ttl_seconds=int(value.get("ttl_seconds")) if isinstance(value.get("ttl_seconds"), int) else None,
            expires_at=int(value.get("expires_at")) if isinstance(value.get("expires_at"), int) else None,
            conversation=dict(value.get("conversation") if isinstance(value.get("conversation"), dict) else {}),
            response=dict(value.get("response") if isinstance(value.get("response"), dict) else {}),
            enabled=bool(value.get("enabled", True)),
            public_url=dict(value.get("public_url") if isinstance(value.get("public_url"), dict) else {}),
            metadata=dict(value.get("metadata") if isinstance(value.get("metadata"), dict) else {}),
        )
