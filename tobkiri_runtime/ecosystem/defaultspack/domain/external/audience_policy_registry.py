from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .component_profiles import audience_policy_specs_from_components
from .event import ExternalEvent
from .source_store import ExternalSourceStore
from .targeting import origin_from_external_event


class AudiencePolicyRegistry:
    def __init__(self, source_store: ExternalSourceStore | None = None, pack_root: Path | None = None) -> None:
        self.source_store = source_store or ExternalSourceStore()
        self.pack_root = pack_root or Path(__file__).resolve().parents[2]

    def resolve(self, policy_id: str, *, event: ExternalEvent | None = None) -> dict[str, Any]:
        policies = audience_policy_specs_from_components(self.pack_root)
        policy = deepcopy(policies.get(str(policy_id or "").strip()) or {"default": "allow"})
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
