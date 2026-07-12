from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping


HANDOFF_STATES = (
    "PLANNED",
    "PREFLIGHT",
    "PRESYNCING",
    "QUIESCING_SOURCE",
    "FINAL_CHECKPOINT",
    "TRANSFERRING",
    "PROVISIONING_DESTINATION",
    "RESTORING",
    "PROVIDER_PROBE",
    "MODEL_PROBE",
    "TOOL_HEALTH_CHECK",
    "AWAITING_CUTOVER",
    "CUTOVER",
    "COMPLETED",
)

FAILURE_STATES = (
    "PAUSED_USER_ACTION",
    "RETRYABLE_FAILURE",
    "ROLLING_BACK",
    "ROLLED_BACK",
    "CANCELLED",
    "FAILED",
)

TERMINAL_STATES = frozenset({"COMPLETED", "CANCELLED", "FAILED", "ROLLED_BACK", "PAUSED_USER_ACTION"})


def canonical_json(value: Any) -> str:
    return json.dumps(to_plain(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ProviderRouteRef:
    provider_id: str
    api_id: str
    model_id: str
    adapter_id: str
    provider_extension_ref: str | None
    base_url: str | None
    auth_scheme: str
    header_profile: str | None
    allowed_models: tuple[str, ...]
    capability_hash: str
    endpoint_class: str
    credential_ref: str
    fallback_routes: tuple[str, ...] = ()
    portable: bool = False
    blocked_reason: str | None = None
    route_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_models", tuple(self.allowed_models))
        object.__setattr__(self, "fallback_routes", tuple(self.fallback_routes))
        if not self.route_id:
            route_id = content_hash(
                {
                    "provider_id": self.provider_id,
                    "api_id": self.api_id,
                    "model_id": self.model_id,
                    "base_url": self.base_url,
                    "credential_ref": self.credential_ref,
                }
            )[:24]
            object.__setattr__(self, "route_id", route_id)

    @property
    def qualified_route(self) -> str:
        return f"{self.provider_id}/{self.api_id}/{self.model_id}"

    def as_dict(self) -> dict[str, Any]:
        payload = to_plain(self)
        payload["qualified_route"] = self.qualified_route
        return payload


@dataclass(frozen=True)
class RumiNodeDescriptor:
    node_id: str
    display_name: str
    device_public_key: str
    signing_public_key: str
    platform: str
    architecture: str
    online: bool
    last_seen_at: str
    app_version: str
    protocol_version: int
    runtime_providers: tuple[str, ...] = ()
    sandbox_capabilities: tuple[str, ...] = ()
    available_cpu: float | None = None
    available_memory_mb: int | None = None
    available_disk_mb: int | None = None
    desktop_capacity: int = 0
    network_reachability_classes: tuple[str, ...] = ("public_https",)
    provider_extension_digests: tuple[str, ...] = ()
    destination_kind: str = "rumi_node"

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_providers", tuple(self.runtime_providers))
        object.__setattr__(self, "sandbox_capabilities", tuple(self.sandbox_capabilities))
        object.__setattr__(self, "network_reachability_classes", tuple(self.network_reachability_classes))
        object.__setattr__(self, "provider_extension_digests", tuple(self.provider_extension_digests))

    def as_dict(self) -> dict[str, Any]:
        return to_plain(self)


@dataclass(frozen=True)
class CredentialEnvelope:
    envelope_id: str
    source_node_id: str
    destination_node_id: str
    provider_id: str
    api_id: str
    allowed_model_ids: tuple[str, ...]
    allowed_base_url_hash: str
    permissions: tuple[str, ...]
    expires_at: str
    created_at: str
    ephemeral_public_key: str
    nonce: str
    ciphertext: str
    source_signing_public_key: str
    source_signature: str
    algorithm: str = "x25519-hkdf-sha256-aesgcm-ed25519"
    max_requests: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_model_ids", tuple(self.allowed_model_ids))
        object.__setattr__(self, "permissions", tuple(self.permissions))

    def unsigned_payload(self) -> dict[str, Any]:
        data = self.as_dict()
        data.pop("source_signature", None)
        return data

    def as_dict(self) -> dict[str, Any]:
        return to_plain(self)


@dataclass(frozen=True)
class ContinuityCheckpointManifest:
    schema_version: int
    checkpoint_id: str
    sandbox_id: str
    source_node_id: str
    source_generation: int
    base_runtime_digest: str
    template_id: str
    architecture: str
    workspace_chunk_root: str | None
    home_overlay_chunk_root: str | None
    browser_state_ref: str | None
    terminal_sessions: tuple[dict[str, Any], ...]
    task_state_ref: str | None
    conversation_state_ref: str | None
    tool_state_ref: str | None
    provider_route_ref: dict[str, Any]
    credential_envelope_id: str | None
    desktop_spec: dict[str, Any]
    created_at: str
    consistency_marker: str
    encryption_metadata: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "terminal_sessions", tuple(self.terminal_sessions))

    def as_dict(self) -> dict[str, Any]:
        return to_plain(self)


@dataclass(frozen=True)
class ContinuityPreflightResult:
    ok: bool
    route: dict[str, Any] | None = None
    destination: dict[str, Any] | None = None
    checks: tuple[dict[str, Any], ...] = ()
    errors: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "errors", tuple(self.errors))

    def as_dict(self) -> dict[str, Any]:
        return to_plain(self)


@dataclass(frozen=True)
class HandoffPlan:
    plan_id: str
    mode: str
    sandbox_id: str
    destination_node_id: str
    provider_route_ref: dict[str, Any]
    fallback_route_refs: tuple[dict[str, Any], ...]
    credential_delegation: dict[str, Any]
    checkpoint_estimate: dict[str, Any]
    resource_preflight: dict[str, Any]
    cutover: dict[str, Any]
    status: str
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fallback_route_refs", tuple(self.fallback_route_refs))

    def as_dict(self) -> dict[str, Any]:
        return to_plain(self)
