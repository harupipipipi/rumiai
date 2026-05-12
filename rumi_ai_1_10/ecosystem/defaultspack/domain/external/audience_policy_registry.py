from __future__ import annotations

from copy import deepcopy
from typing import Any

from .event import ExternalEvent
from .source_store import ExternalSourceStore
from .targeting import origin_from_external_event


DEFAULT_AUDIENCE_POLICIES: dict[str, dict[str, Any]] = {
    "line.production": {
        "id": "line.production",
        "provider": "line",
        "default": "deny",
        "require": {"verified": True, "message_types": ["text"]},
        "rate_limit": {"per_actor_per_minute": 10, "per_scope_per_minute": 30},
        "allow_saved_sources": True,
        "allow": [],
        "deny": [],
    },
    "discord.production": {
        "id": "discord.production",
        "provider": "discord",
        "default": "allow",
        "require": {"verified": True},
    },
    "slack.production": {
        "id": "slack.production",
        "provider": "slack",
        "default": "allow",
        "require": {"verified": True},
    },
}


class AudiencePolicyRegistry:
    def __init__(self, source_store: ExternalSourceStore | None = None) -> None:
        self.source_store = source_store or ExternalSourceStore()

    def resolve(self, policy_id: str, *, event: ExternalEvent | None = None) -> dict[str, Any]:
        policy = deepcopy(DEFAULT_AUDIENCE_POLICIES.get(str(policy_id or "").strip()) or {"default": "allow"})
        if event is not None and bool(policy.get("allow_saved_sources")):
            origin = origin_from_external_event(event)
            if origin.source_id and self.source_store.is_enabled(origin):
                allow = policy.setdefault("allow", [])
                if isinstance(allow, list):
                    allow.append(
                        {
                            "id": "saved-source:" + origin.source_type + ":" + origin.source_id,
                            "provider": origin.provider,
                            "scope": {"type": origin.source_type, "id": origin.source_id},
                        }
                    )
        return policy
