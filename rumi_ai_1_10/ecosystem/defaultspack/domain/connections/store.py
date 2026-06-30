from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core_runtime.connections.credential_store import CredentialEnvelope
from core_runtime.connections.import_service import ConnectionImportService
from core_runtime.connections.permission_resolver import resolve_connection_permissions

_PREFIX = "RUMICONN"
_SLUG_PATTERN = re.compile(r"[^A-Za-z0-9_]+")


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _connection_manifest_root(pack_root: Path | None = None) -> Path:
    candidate = (pack_root or _pack_root()) / "config" / "settings_control_center" / "providers"
    if candidate.exists():
        return candidate
    return _pack_root() / "config" / "settings_control_center" / "providers"


def _connection_registry(pack_root: Path | None = None):
    from core_runtime.connections.registry import ConnectionsRegistry

    registry = ConnectionsRegistry()
    root = _connection_manifest_root(pack_root)
    if root.exists():
        registry.load_manifest_dir(root)
    return registry


def _connection_provider(provider_id: str, *, pack_root: Path | None = None):
    provider_id = str(provider_id or "").strip()
    if not provider_id:
        return None
    try:
        return _connection_registry(pack_root).get(provider_id)
    except KeyError:
        return None


def _secrets_dir(pack_root: Path | None = None) -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_SECRETS_DIR", "").strip()
    if override:
        return Path(override)
    return (pack_root or _pack_root()) / "user_data" / "secrets"


def _metadata_path(pack_root: Path | None = None) -> Path:
    return _secrets_dir(pack_root) / "connection_credentials.json"


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(value: str, *, fallback: str, max_length: int) -> str:
    normalized = _SLUG_PATTERN.sub("_", str(value or "").strip()).strip("_").upper()
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        normalized = fallback
    return normalized[:max_length]


def connection_secret_key(provider_id: str, connection_id: str = "default", material_type: str = "credential_bundle") -> str:
    provider_slug = _slug(provider_id, fallback="PROVIDER", max_length=16)
    material_slug = _slug(material_type, fallback="CREDENTIAL", max_length=22)
    connection_slug = _slug(connection_id, fallback="DEFAULT", max_length=18)
    return f"{_PREFIX}_{provider_slug}_{material_slug}_{connection_slug}"[:64]


def _read_metadata(pack_root: Path | None = None) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(_metadata_path(pack_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)}


def _write_metadata(data: dict[str, dict[str, Any]], pack_root: Path | None = None) -> None:
    path = _metadata_path(pack_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _get_store(pack_root: Path | None = None):
    from core_runtime.secrets_store import SecretsStore

    return SecretsStore(str(_secrets_dir(pack_root)))


class DefaultspackConnectionCredentialStore:
    def __init__(self, *, pack_root: Path | None = None) -> None:
        self.pack_root = pack_root

    def put(self, provider_id: str, connection_id: str, material_type: str, secret_material: dict[str, Any]) -> CredentialEnvelope:
        key = connection_secret_key(provider_id, connection_id, material_type)
        now = _now_ts()
        metadata = _read_metadata(self.pack_root)
        existing = metadata.get(key, {})
        payload = {
            **dict(secret_material),
            "provider_id": str(provider_id or "").strip(),
            "connection_id": str(connection_id or "default").strip() or "default",
            "material_type": str(material_type or "credential_bundle").strip() or "credential_bundle",
        }
        result = _get_store(self.pack_root).set_secret(
            key,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            actor="defaultspack",
            reason=f"save connection credential {provider_id}:{material_type}",
        )
        if not result.success:
            raise RuntimeError(result.error or f"failed to save connection credential {key}")
        metadata[key] = {
            **existing,
            "credential_id": key,
            "provider_id": payload["provider_id"],
            "connection_id": payload["connection_id"],
            "material_type": payload["material_type"],
            "created_at": str(existing.get("created_at") or now),
            "updated_at": now,
            "key_version": "defaultspack-secrets-v1",
        }
        token_metadata = payload.get("token_metadata")
        if isinstance(token_metadata, dict):
            for field in ("scopes", "capabilities", "expires_at", "status", "account_label", "credential_kind"):
                if field in token_metadata:
                    metadata[key][field] = token_metadata[field]
        _write_metadata(metadata, self.pack_root)
        return CredentialEnvelope(
            credential_id=key,
            provider_id=payload["provider_id"],
            connection_id=payload["connection_id"],
            material_type=payload["material_type"],
            ciphertext="",
            key_version="defaultspack-secrets-v1",
        )

    def get(self, credential_id: str) -> dict[str, Any]:
        raw_value = _get_store(self.pack_root)._internal_read_value(
            str(credential_id or ""),
            caller_id=f"defaultspack.connections:{credential_id}",
        )
        if not raw_value:
            raise KeyError(f"Unknown credential: {credential_id}")
        payload = json.loads(raw_value)
        if not isinstance(payload, dict):
            raise KeyError(f"Invalid credential payload: {credential_id}")
        return payload

    def delete(self, credential_id: str) -> None:
        try:
            _get_store(self.pack_root).delete_secret(
                str(credential_id or ""),
                actor="defaultspack",
                reason="delete connection credential",
            )
        except Exception:
            pass
        metadata = _read_metadata(self.pack_root)
        if metadata.pop(str(credential_id or ""), None) is not None:
            _write_metadata(metadata, self.pack_root)


def save_connection_credential(
    provider_id: str,
    material_type: str,
    secret_material: dict[str, Any],
    *,
    connection_id: str = "default",
    token_metadata: dict[str, Any] | None = None,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    payload = dict(secret_material)
    if token_metadata:
        payload["token_metadata"] = dict(token_metadata)
    store = DefaultspackConnectionCredentialStore(pack_root=pack_root)
    envelope = store.put(provider_id, connection_id, material_type, payload)
    return {
        "success": True,
        "credential_ref": _credential_ref_from_envelope(envelope),
    }


def read_connection_credential(
    provider_id: str,
    material_type: str,
    *,
    connection_id: str = "default",
    pack_root: Path | None = None,
) -> dict[str, Any]:
    key = connection_secret_key(provider_id, connection_id, material_type)
    try:
        return DefaultspackConnectionCredentialStore(pack_root=pack_root).get(key)
    except Exception:
        return {}


def delete_connection_credential(
    provider_id: str,
    material_type: str,
    *,
    connection_id: str = "default",
    pack_root: Path | None = None,
) -> None:
    key = connection_secret_key(provider_id, connection_id, material_type)
    DefaultspackConnectionCredentialStore(pack_root=pack_root).delete(key)


def connection_credential_ref(
    provider_id: str,
    material_type: str,
    *,
    connection_id: str = "default",
    pack_root: Path | None = None,
) -> dict[str, str]:
    key = connection_secret_key(provider_id, connection_id, material_type)
    metadata = _read_metadata(pack_root).get(key, {})
    if not metadata:
        return {}
    try:
        exists = _get_store(pack_root).has_secret(key)
    except Exception:
        exists = False
    if not exists:
        return {}
    return {
        "credential_id": key,
        "provider_id": str(metadata.get("provider_id") or provider_id),
        "connection_id": str(metadata.get("connection_id") or connection_id),
        "key_version": str(metadata.get("key_version") or "defaultspack-secrets-v1"),
    }


def import_connection_bundle(raw_bundle: str | dict[str, Any], *, pack_root: Path | None = None) -> dict[str, Any]:
    registry = _connection_registry(pack_root)
    result = ConnectionImportService(
        registry,
        DefaultspackConnectionCredentialStore(pack_root=pack_root),
    ).import_connection(raw_bundle)
    return result


def resolve_capabilities_for_provider(provider_id: str, token_metadata: dict[str, Any], *, pack_root: Path | None = None) -> dict[str, Any]:
    provider = _connection_provider(provider_id, pack_root=pack_root)
    if provider is None:
        return {"scopes": [], "capabilities": []}
    resolved = resolve_connection_permissions(provider, token_metadata)
    return resolved.to_dict()


def _credential_ref_from_envelope(envelope: CredentialEnvelope) -> dict[str, str]:
    return {
        "credential_id": envelope.credential_id,
        "provider_id": envelope.provider_id,
        "connection_id": envelope.connection_id,
        "key_version": envelope.key_version,
    }
