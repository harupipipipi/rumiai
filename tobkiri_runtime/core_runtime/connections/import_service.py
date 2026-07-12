from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from .adapter import load_connection_adapter
from .credential_store import CredentialEnvelope
from .models import ConnectionProvider
from .permission_resolver import resolve_connection_permissions
from .registry import ConnectionsRegistry
from .templates import CredentialBundle


class CredentialBundleStore(Protocol):
    def put(self, provider_id: str, connection_id: str, material_type: str, secret_material: dict[str, Any]) -> CredentialEnvelope: ...
    def get(self, credential_id: str) -> dict[str, Any]: ...
    def delete(self, credential_id: str) -> None: ...


class ConnectionImportService:
    def __init__(self, registry: ConnectionsRegistry, credential_store: CredentialBundleStore) -> None:
        self.registry = registry
        self.credential_store = credential_store

    def import_connection(self, raw_bundle: str | Mapping[str, Any]) -> dict[str, Any]:
        payload = json.loads(raw_bundle) if isinstance(raw_bundle, str) else dict(raw_bundle)
        bundle = CredentialBundle.from_dict(payload)
        provider = self.registry.get(bundle.provider_id)
        if not provider.token_import_supported:
            raise ValueError(f"provider {provider.provider_id} does not support token import")
        secret_material = bundle.secret_material()
        if not secret_material.get("credentials"):
            raise ValueError("credential bundle does not include credential material")
        adapter = load_connection_adapter(provider.adapter)
        token_metadata = adapter.normalize_token_metadata(
            provider=provider,
            credential_bundle=bundle,
            secret_material=secret_material,
        )
        resolved = resolve_connection_permissions(provider, token_metadata)
        secret_material["token_metadata"] = {
            **dict(secret_material.get("token_metadata") or {}),
            **token_metadata,
            "scopes": list(resolved.scopes),
            "capabilities": list(resolved.capabilities),
            "approval_required_capabilities": list(resolved.approval_required_capabilities),
            "rejected_capabilities": list(resolved.rejected_capabilities),
        }
        envelope = self.credential_store.put(
            provider.provider_id,
            bundle.connection_id,
            bundle.material_type,
            secret_material,
        )
        return safe_import_result(
            provider=provider,
            envelope=envelope,
            token_metadata=token_metadata,
            scopes=resolved.scopes,
            capabilities=resolved.capabilities,
            approval_required_capabilities=resolved.approval_required_capabilities,
            rejected_capabilities=resolved.rejected_capabilities,
        )


def safe_import_result(
    *,
    provider: ConnectionProvider,
    envelope: CredentialEnvelope,
    token_metadata: Mapping[str, Any],
    scopes: list[str],
    capabilities: list[str],
    approval_required_capabilities: list[str],
    rejected_capabilities: list[str],
) -> dict[str, Any]:
    return {
        "success": True,
        "provider_id": provider.provider_id,
        "connection_id": envelope.connection_id,
        "credential_ref": {
            "credential_id": envelope.credential_id,
            "provider_id": envelope.provider_id,
            "connection_id": envelope.connection_id,
            "key_version": envelope.key_version,
        },
        "scopes": list(scopes),
        "capabilities": list(capabilities),
        "approval_required_capabilities": list(approval_required_capabilities),
        "rejected_capabilities": list(rejected_capabilities),
        "expires_at": str(token_metadata.get("expires_at") or ""),
        "status": str(token_metadata.get("status") or "connected"),
        "account_label": str(token_metadata.get("account_label") or provider.provider_id),
    }
