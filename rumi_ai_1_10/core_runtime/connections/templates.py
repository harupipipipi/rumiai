from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .models import ConnectionProvider

PROVIDER_TEMPLATE_SCHEMA = "rumi.connection.provider.v1"
CREDENTIAL_BUNDLE_SCHEMA = "rumi.connection.credential_bundle.v1"

_SECRET_FIELDS = {
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "token",
    "client_secret",
    "private_key",
    "app_private_key",
    "app_server_secret",
    "shared_secret",
    "ws_token",
}


@dataclass(frozen=True)
class ConnectionTemplate:
    provider: ConnectionProvider
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ConnectionTemplate":
        payload = dict(raw)
        schema = str(payload.get("schema") or "").strip()
        if schema != PROVIDER_TEMPLATE_SCHEMA:
            raise ValueError(f"unsupported connection provider schema: {schema or '<missing>'}")
        return cls(provider=ConnectionProvider.from_dict(payload), raw=payload)

    @classmethod
    def from_json(cls, raw_value: str) -> "ConnectionTemplate":
        return cls.from_dict(json.loads(raw_value))

    @property
    def provider_id(self) -> str:
        return self.provider.provider_id

    @property
    def token_import_supported(self) -> bool:
        return self.provider.token_import_supported


@dataclass(frozen=True)
class CredentialBundle:
    provider_id: str
    connection_id: str
    account_label: str
    material_type: str
    credentials: dict[str, Any]
    token_metadata: dict[str, Any] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)
    expires_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CredentialBundle":
        payload = dict(raw)
        schema = str(payload.get("schema") or CREDENTIAL_BUNDLE_SCHEMA).strip()
        if schema != CREDENTIAL_BUNDLE_SCHEMA:
            raise ValueError(f"unsupported credential bundle schema: {schema or '<missing>'}")
        provider_id = str(payload.get("provider_id") or "").strip()
        if not provider_id:
            raise ValueError("credential bundle provider_id is required")
        connection_id = str(payload.get("connection_id") or payload.get("account_id") or "default").strip() or "default"
        token_metadata = _dict_value(payload.get("token_metadata") or payload.get("metadata"))
        credentials = _extract_credentials(payload)
        scopes = _normalize_scopes(payload.get("scopes") or payload.get("scope") or token_metadata.get("scopes") or token_metadata.get("scope"))
        expires_at = str(payload.get("expires_at") or token_metadata.get("expires_at") or "").strip()
        expires_at = expires_at or _expires_at_from_seconds(payload.get("expires_in") or token_metadata.get("expires_in"))
        material_type = str(
            payload.get("material_type")
            or payload.get("credential_type")
            or payload.get("kind")
            or _infer_material_type(credentials)
        ).strip()
        return cls(
            provider_id=provider_id,
            connection_id=connection_id,
            account_label=str(payload.get("account_label") or payload.get("name") or "").strip(),
            material_type=material_type or "credential_bundle",
            credentials=credentials,
            token_metadata=token_metadata,
            scopes=scopes,
            expires_at=expires_at,
            raw=payload,
        )

    @classmethod
    def from_json(cls, raw_value: str) -> "CredentialBundle":
        return cls.from_dict(json.loads(raw_value))

    def secret_material(self) -> dict[str, Any]:
        return {
            "schema": CREDENTIAL_BUNDLE_SCHEMA,
            "provider_id": self.provider_id,
            "connection_id": self.connection_id,
            "material_type": self.material_type,
            "credentials": dict(self.credentials),
            "token_metadata": dict(self.token_metadata),
            "scopes": list(self.scopes),
            "expires_at": self.expires_at,
        }

    def safe_metadata(self) -> dict[str, Any]:
        metadata = dict(self.token_metadata)
        metadata.pop("capabilities", None)
        metadata.pop("capabilities_granted", None)
        return {
            "provider_id": self.provider_id,
            "connection_id": self.connection_id,
            "account_label": self.account_label,
            "material_type": self.material_type,
            "scopes": list(self.scopes),
            "expires_at": self.expires_at,
            "token_metadata": metadata,
        }


def _extract_credentials(payload: Mapping[str, Any]) -> dict[str, Any]:
    credentials = _dict_value(payload.get("credentials") or payload.get("credential"))
    token_response = _dict_value(payload.get("token_response") or payload.get("oauth_token"))
    credentials.update({key: value for key, value in token_response.items() if key in _SECRET_FIELDS or key in {"scope", "expires_in", "token_type"}})
    for key in _SECRET_FIELDS:
        value = payload.get(key)
        if str(value or "").strip():
            credentials[key] = value
    return credentials


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalize_scopes(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item).strip()]
    return [item for item in text.replace(",", " ").split() if item]


def _expires_at_from_seconds(value: Any) -> str:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return ""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _infer_material_type(credentials: Mapping[str, Any]) -> str:
    if "access_token" in credentials or "refresh_token" in credentials:
        return "oauth2_token"
    if "client_secret" in credentials:
        return "oauth2_client_config"
    if "app_private_key" in credentials or "private_key" in credentials:
        return "app_private_key"
    if "app_server_secret" in credentials or "shared_secret" in credentials or "ws_token" in credentials:
        return "app_server_secret"
    if "api_key" in credentials or "token" in credentials:
        return "access_token"
    return "credential_bundle"
