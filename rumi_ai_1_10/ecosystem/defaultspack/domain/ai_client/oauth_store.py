from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_GOOGLE_DEFAULT_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/generative-language",
]
_GOOGLE_IDENTITY_SCOPES = ["openid", "email", "profile"]
_GOOGLE_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
_GOOGLE_GMAIL_LABELS_SCOPE = "https://www.googleapis.com/auth/gmail.labels"
_GOOGLE_GMAIL_METADATA_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"
_GOOGLE_GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_GOOGLE_SCOPE_MODES = {
    "google_identity": list(_GOOGLE_IDENTITY_SCOPES),
    "google_ai": list(_GOOGLE_DEFAULT_SCOPES),
    "google_workspace": [*_GOOGLE_IDENTITY_SCOPES, _GOOGLE_DRIVE_FILE_SCOPE, _GOOGLE_GMAIL_LABELS_SCOPE],
    "google_drive": [*_GOOGLE_IDENTITY_SCOPES, _GOOGLE_DRIVE_FILE_SCOPE],
    "google_gmail_labels": [*_GOOGLE_IDENTITY_SCOPES, _GOOGLE_GMAIL_LABELS_SCOPE],
    "google_gmail_metadata": [*_GOOGLE_IDENTITY_SCOPES, _GOOGLE_GMAIL_METADATA_SCOPE],
    "google_gmail_readonly": [*_GOOGLE_IDENTITY_SCOPES, _GOOGLE_GMAIL_READONLY_SCOPE],
}
_GOOGLE_SCOPE_MODE_DETAILS = {
    "google_identity": {
        "label": "Google identity",
        "description": "Basic Google sign-in identity only.",
        "services": ["identity"],
        "surface": "accounts_connections",
    },
    "google_drive": {
        "label": "Google Drive selected files",
        "description": "Drive file scope for files created, opened, or explicitly shared with Rumi.",
        "services": ["identity", "drive_file"],
        "surface": "accounts_connections",
    },
    "google_gmail_labels": {
        "label": "Gmail labels",
        "description": "Low-friction Gmail labels access without message bodies.",
        "services": ["identity", "gmail_labels"],
        "surface": "accounts_connections",
    },
    "google_gmail_metadata": {
        "label": "Gmail metadata/search",
        "description": "Restricted Gmail metadata scope for search and message metadata.",
        "services": ["identity", "gmail_metadata"],
        "restricted": True,
        "warning": "Restricted Gmail scopes require explicit self-host acknowledgement or Google verification review.",
        "surface": "accounts_connections",
    },
    "google_gmail_readonly": {
        "label": "Gmail read-only bodies",
        "description": "Restricted Gmail read-only scope for message bodies.",
        "services": ["identity", "gmail_readonly"],
        "restricted": True,
        "warning": "Restricted Gmail scopes can expose message content and may require Google security review.",
        "surface": "accounts_connections",
    },
    "google_ai": {
        "label": "Google AI",
        "description": "Gemini / Generative Language API access for model calls.",
        "services": ["identity", "generative_language"],
        "surface": "models_api",
    },
}

_CLIENT_CONFIG_SECRET_KEYS = {
    "google": "RUMIOAUTH_GOOGLE_CLIENT_CONFIG",
}
_ACCESS_TOKEN_SECRET_KEYS = {
    "google": "RUMIOAUTH_GOOGLE_ACCESS_TOKEN",
}
_REFRESH_TOKEN_SECRET_KEYS = {
    "google": "RUMIOAUTH_GOOGLE_REFRESH_TOKEN",
}
_ID_TOKEN_SECRET_KEYS = {
    "google": "RUMIOAUTH_GOOGLE_ID_TOKEN",
}

_OAUTH_RUNTIME_PROVIDER_IDS = {"google"}
_PENDING_STATE_TTL_SECONDS = 600
_ACCESS_TOKEN_SKEW_SECONDS = 60
_pending_states: dict[str, dict[str, Any]] = {}


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


def _connection_provider_ids(*, pack_root: Path | None = None) -> set[str]:
    root = _connection_manifest_root(pack_root)
    ids: set[str] = set()
    if not root.exists():
        return ids
    for path in root.rglob("*.connection.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        provider_id = str(payload.get("provider_id") or "").strip()
        if provider_id:
            ids.add(provider_id)
    return ids


def _secrets_dir(pack_root: Path | None = None) -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_SECRETS_DIR", "").strip()
    if override:
        return Path(override)
    return (pack_root or _pack_root()) / "user_data" / "secrets"


def _metadata_path(pack_root: Path | None = None) -> Path:
    return (pack_root or _pack_root()) / "user_data" / "settings" / "provider_oauth.json"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _cleanup_pending_states() -> None:
    cutoff = time.time() - _PENDING_STATE_TTL_SECONDS
    expired = [state for state, entry in _pending_states.items() if float(entry.get("created_at") or 0.0) < cutoff]
    for state in expired:
        _pending_states.pop(state, None)


def _read_metadata(pack_root: Path | None = None) -> dict[str, dict[str, Any]]:
    path = _metadata_path(pack_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(key): value
        for key, value in data.items()
        if isinstance(value, dict)
    }


def _write_metadata(data: dict[str, dict[str, Any]], pack_root: Path | None = None) -> None:
    path = _metadata_path(pack_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _get_store(pack_root: Path | None = None):
    from core_runtime.secrets_store import SecretsStore

    return SecretsStore(str(_secrets_dir(pack_root)))


def _secret_key(mapping: dict[str, str], provider_id: str) -> str:
    return str(mapping.get(str(provider_id or "").strip(), "")).strip()


def _read_secret(key: str, caller_id: str, *, pack_root: Path | None = None) -> str:
    if not key:
        return ""
    value = os.environ.get(key, "").strip()
    if value:
        return value
    try:
        secret = _get_store(pack_root)._internal_read_value(key, caller_id=caller_id)
    except Exception:
        return ""
    return str(secret or "").strip()


def _set_secret(key: str, value: str, *, actor: str, reason: str, pack_root: Path | None = None) -> None:
    result = _get_store(pack_root).set_secret(key, value, actor=actor, reason=reason)
    if not result.success:
        raise RuntimeError(result.error or f"failed to save secret {key}")


def _delete_secret(key: str, *, actor: str, reason: str, pack_root: Path | None = None) -> None:
    if not key:
        return
    try:
        _get_store(pack_root).delete_secret(key, actor=actor, reason=reason)
    except Exception:
        pass
    os.environ.pop(key, None)


def _reset_ai_client() -> None:
    try:
        from domain.ai_client.client import AIClient

        AIClient._instance = None
    except Exception:
        pass


def provider_supports_oauth(provider_id: str) -> bool:
    provider_id = str(provider_id or "").strip()
    provider = _connection_provider(provider_id)
    return provider_id in _OAUTH_RUNTIME_PROVIDER_IDS and provider is not None and provider.oauth is not None


def _client_id_label(client_id: str) -> str:
    client_id = str(client_id or "").strip()
    if not client_id:
        return ""
    if len(client_id) <= 18:
        return client_id
    return f"{client_id[:10]}...{client_id[-8:]}"


def _default_scopes(provider_id: str, scope_mode: str | None = None) -> list[str]:
    provider_id = str(provider_id or "").strip()
    if provider_id != "google":
        provider = _connection_provider(provider_id)
        return list(provider.oauth.default_scopes if provider and provider.oauth else [])
    mode = str(scope_mode or "google_identity").strip() or "google_identity"
    if mode == "default":
        mode = "google_identity"
    if mode not in _GOOGLE_SCOPE_MODES:
        raise ValueError(f"unsupported Google OAuth scope mode: {mode}")
    override = os.environ.get("RUMI_DEFAULTSPACK_GOOGLE_OAUTH_SCOPES", "").strip()
    if override and mode == "google_ai":
        return [item for item in override.split() if item]
    return list(_GOOGLE_SCOPE_MODES[mode])


def _google_scope_mode_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode in (
        "google_identity",
        "google_drive",
        "google_gmail_labels",
        "google_gmail_metadata",
        "google_gmail_readonly",
        "google_ai",
    ):
        details = dict(_GOOGLE_SCOPE_MODE_DETAILS[mode])
        rows.append(
            {
                "id": mode,
                "label": str(details.get("label") or mode),
                "description": str(details.get("description") or ""),
                "scopes": _default_scopes("google", mode),
                "services": list(details.get("services") or []),
                "restricted": bool(details.get("restricted")),
                "warning": str(details.get("warning") or ""),
                "surface": str(details.get("surface") or ""),
            }
        )
    return rows


def _normalize_requested_services(services: Any) -> list[str]:
    if not isinstance(services, list):
        return []
    normalized: list[str] = []
    for item in services:
        value = str(item or "").strip().lower().replace("-", "_")
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _scope_mode_from_services(provider_id: str, services: Any) -> str | None:
    if str(provider_id or "").strip() != "google":
        return None
    service_set = set(_normalize_requested_services(services))
    if not service_set:
        return None
    if service_set & {"gmail_readonly", "readonly_body", "gmail:readonly_body"}:
        return "google_gmail_readonly"
    if service_set & {"gmail_metadata", "metadata_search", "gmail:metadata_search"}:
        return "google_gmail_metadata"
    has_drive = bool(service_set & {"drive", "drive_file", "google_drive"})
    has_gmail_labels = bool(service_set & {"gmail", "gmail_labels", "labels_only", "gmail:labels_only"})
    if has_drive and has_gmail_labels:
        return "google_workspace"
    if has_drive:
        return "google_drive"
    if has_gmail_labels:
        return "google_gmail_labels"
    if service_set & {"ai", "google_ai", "generative_language"}:
        return "google_ai"
    if "identity" in service_set:
        return "google_identity"
    return None


def _load_env_client_config(provider_id: str) -> dict[str, Any] | None:
    provider_id = str(provider_id or "").strip()
    if provider_id != "google":
        return None
    raw_json = os.environ.get("RUMI_DEFAULTSPACK_GOOGLE_OAUTH_CLIENT_JSON", "").strip()
    raw_id = os.environ.get("RUMI_DEFAULTSPACK_GOOGLE_OAUTH_CLIENT_ID", "").strip()
    raw_secret = os.environ.get("RUMI_DEFAULTSPACK_GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if raw_json:
        return _parse_provider_client_config(provider_id, raw_json)
    if raw_id:
        return {
            "provider_id": provider_id,
            "client_id": raw_id,
            "client_secret": raw_secret,
            "redirect_uris": [],
            "source": "env",
        }
    return None


def _parse_google_client_config(raw_value: str) -> dict[str, Any]:
    text = str(raw_value or "").strip()
    if not text:
        raise ValueError("Google OAuth client config is required")
    client_id = ""
    client_secret = ""
    redirect_uris: list[str] = []
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Google OAuth client config must be valid JSON") from exc
        if isinstance(payload.get("installed"), dict):
            payload = payload["installed"]
        elif isinstance(payload.get("web"), dict):
            payload = payload["web"]
        if not isinstance(payload, dict):
            raise ValueError("Google OAuth client config JSON is invalid")
        client_id = str(payload.get("client_id") or "").strip()
        client_secret = str(payload.get("client_secret") or "").strip()
        redirect_uris = [
            str(item).strip()
            for item in (payload.get("redirect_uris") or [])
            if str(item).strip()
        ]
    else:
        client_id = text
    if not client_id:
        raise ValueError("Google OAuth client_id is required")
    return {
        "provider_id": "google",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": redirect_uris,
        "source": "stored",
    }


def _parse_provider_client_config(provider_id: str, raw_value: str) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    if provider_id == "google":
        return _parse_google_client_config(raw_value)
    raise ValueError(f"OAuth is not supported for provider '{provider_id}'")


def load_provider_client_config(provider_id: str, *, pack_root: Path | None = None) -> dict[str, Any] | None:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return None
    env_config = _load_env_client_config(provider_id)
    if env_config is not None:
        return env_config
    key = _secret_key(_CLIENT_CONFIG_SECRET_KEYS, provider_id)
    raw_value = _read_secret(key, f"defaultspack.oauth:{provider_id}:client", pack_root=pack_root)
    if not raw_value:
        return None
    config = _parse_provider_client_config(provider_id, raw_value)
    config["source"] = "secret_store"
    return config


def save_provider_oauth_client_config(
    provider_id: str,
    raw_value: str,
    *,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}
    config = _parse_provider_client_config(provider_id, raw_value)
    key = _secret_key(_CLIENT_CONFIG_SECRET_KEYS, provider_id)
    try:
        _set_secret(
            key,
            json.dumps(
                {
                    "client_id": config.get("client_id"),
                    "client_secret": config.get("client_secret"),
                    "redirect_uris": config.get("redirect_uris") or [],
                },
                ensure_ascii=False,
            ),
            actor="defaultspack",
            reason=f"save {provider_id} oauth client config",
            pack_root=pack_root,
        )
    except RuntimeError as exc:
        return {"success": False, "provider_id": provider_id, "error": str(exc)}
    return {
        "success": True,
        "provider_id": provider_id,
        "client_configured": True,
        "client_label": _client_id_label(str(config.get("client_id") or "")),
    }


def clear_provider_oauth_client_config(provider_id: str, *, pack_root: Path | None = None) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}
    _delete_secret(
        _secret_key(_CLIENT_CONFIG_SECRET_KEYS, provider_id),
        actor="defaultspack",
        reason=f"clear {provider_id} oauth client config",
        pack_root=pack_root,
    )
    disconnect_provider_oauth(provider_id, pack_root=pack_root)
    return {"success": True, "provider_id": provider_id, "client_configured": False, "connected": False}


def _provider_metadata(provider_id: str, *, pack_root: Path | None = None) -> dict[str, Any]:
    return dict(_read_metadata(pack_root).get(str(provider_id or "").strip(), {}))


def _write_provider_metadata(provider_id: str, payload: dict[str, Any], *, pack_root: Path | None = None) -> None:
    provider_id = str(provider_id or "").strip()
    metadata = _read_metadata(pack_root)
    metadata[provider_id] = dict(payload)
    _write_metadata(metadata, pack_root)


def _expires_at_text(expires_in: Any) -> str:
    try:
        seconds = int(expires_in or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return ""
    return _isoformat(_now_utc() + timedelta(seconds=seconds))


def save_provider_oauth_connection(
    provider_id: str,
    token_data: dict[str, Any],
    *,
    userinfo: dict[str, Any] | None = None,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}
    access_token = str(token_data.get("access_token") or "").strip()
    refresh_token = str(token_data.get("refresh_token") or "").strip()
    id_token = str(token_data.get("id_token") or "").strip()
    if not access_token and not refresh_token:
        return {"success": False, "provider_id": provider_id, "error": "token payload is missing access and refresh tokens"}

    if access_token:
        _set_secret(
            _secret_key(_ACCESS_TOKEN_SECRET_KEYS, provider_id),
            access_token,
            actor="defaultspack",
            reason=f"save {provider_id} oauth access token",
            pack_root=pack_root,
        )
    if refresh_token:
        _set_secret(
            _secret_key(_REFRESH_TOKEN_SECRET_KEYS, provider_id),
            refresh_token,
            actor="defaultspack",
            reason=f"save {provider_id} oauth refresh token",
            pack_root=pack_root,
        )
    if id_token:
        _set_secret(
            _secret_key(_ID_TOKEN_SECRET_KEYS, provider_id),
            id_token,
            actor="defaultspack",
            reason=f"save {provider_id} oauth id token",
            pack_root=pack_root,
        )

    existing = _provider_metadata(provider_id, pack_root=pack_root)
    scopes = [
        item
        for item in str(token_data.get("scope") or "").split()
        if item
    ] or list(existing.get("scopes") or [])
    expires_at = _expires_at_text(token_data.get("expires_in")) or str(existing.get("expires_at") or "")
    profile = dict(userinfo or {})
    metadata = {
        **existing,
        "provider_id": provider_id,
        "connected": True,
        "token_type": str(token_data.get("token_type") or existing.get("token_type") or "Bearer"),
        "scopes": scopes,
        "scope_mode": str(token_data.get("scope_mode") or existing.get("scope_mode") or "").strip(),
        "services": list(token_data.get("services") or existing.get("services") or []),
        "expires_at": expires_at,
        "connected_at": str(existing.get("connected_at") or _isoformat(_now_utc())),
        "updated_at": _isoformat(_now_utc()),
        "email": str(profile.get("email") or existing.get("email") or "").strip(),
        "display_name": str(profile.get("name") or existing.get("display_name") or "").strip(),
        "picture_url": str(profile.get("picture") or existing.get("picture_url") or "").strip(),
        "sub": str(profile.get("sub") or existing.get("sub") or "").strip(),
        "has_refresh_token": bool(refresh_token or existing.get("has_refresh_token")),
    }
    _write_provider_metadata(provider_id, metadata, pack_root=pack_root)
    _reset_ai_client()
    return {
        "success": True,
        "provider_id": provider_id,
        "connected": True,
        "email": metadata.get("email", ""),
        "display_name": metadata.get("display_name", ""),
        "scopes": list(metadata.get("scopes") or []),
        "scope_mode": metadata.get("scope_mode", ""),
        "services": list(metadata.get("services") or []),
        "expires_at": metadata.get("expires_at", ""),
        "has_refresh_token": bool(metadata.get("has_refresh_token")),
    }


def _has_valid_access_token(provider_id: str, *, pack_root: Path | None = None) -> bool:
    access_key = _secret_key(_ACCESS_TOKEN_SECRET_KEYS, provider_id)
    access_token = _read_secret(access_key, f"defaultspack.oauth:{provider_id}:access", pack_root=pack_root)
    if not access_token:
        return False
    metadata = _provider_metadata(provider_id, pack_root=pack_root)
    expires_at = _parse_datetime(metadata.get("expires_at"))
    if expires_at is None:
        return True
    return expires_at > _now_utc() + timedelta(seconds=_ACCESS_TOKEN_SKEW_SECONDS)


def provider_has_oauth_connection(provider_id: str, *, pack_root: Path | None = None) -> bool:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return False
    refresh_key = _secret_key(_REFRESH_TOKEN_SECRET_KEYS, provider_id)
    if _read_secret(refresh_key, f"defaultspack.oauth:{provider_id}:refresh", pack_root=pack_root):
        return True
    return _has_valid_access_token(provider_id, pack_root=pack_root)


def _build_redirect_uri(provider_id: str, request_headers: dict[str, Any] | None = None) -> str:
    provider_id = str(provider_id or "").strip()
    base_url = os.environ.get("RUMI_DEFAULTSPACK_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base_url:
        return f"{base_url}/api/ai/oauth/{urllib.parse.quote(provider_id, safe='')}/callback"
    headers = request_headers or {}
    origin = str(headers.get("Origin") or "").strip().rstrip("/")
    if origin.startswith("http://") or origin.startswith("https://"):
        return f"{origin}/api/ai/oauth/{urllib.parse.quote(provider_id, safe='')}/callback"
    host = str(headers.get("Host") or f"127.0.0.1:{os.environ.get('DEFAULTS_HTTP_PORT', '8766')}").strip()
    proto = str(headers.get("X-Forwarded-Proto") or "http").strip() or "http"
    return f"{proto}://{host}/api/ai/oauth/{urllib.parse.quote(provider_id, safe='')}/callback"


def start_provider_oauth(
    provider_id: str,
    *,
    request_headers: dict[str, Any] | None = None,
    scope_mode: str | None = None,
    services: list[str] | None = None,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    provider = _connection_provider(provider_id, pack_root=pack_root)
    if provider is None or provider.oauth is None:
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}
    if provider_id not in _OAUTH_RUNTIME_PROVIDER_IDS:
        if not provider.oauth.default_scopes:
            return {"success": False, "provider_id": provider_id, "error": "missing scope config", "status": "missing_scope_config"}
        return {"success": False, "provider_id": provider_id, "error": "official app required", "status": "needs_official_app"}
    client = load_provider_client_config(provider_id, pack_root=pack_root)
    if client is None:
        return {"success": False, "provider_id": provider_id, "error": "oauth client config is not saved"}
    resolved_scope_mode = str(scope_mode or _scope_mode_from_services(provider_id, services) or "google_identity").strip() or "google_identity"
    if resolved_scope_mode == "default":
        resolved_scope_mode = "google_identity"
    try:
        scopes = _default_scopes(provider_id, resolved_scope_mode)
    except ValueError as exc:
        return {"success": False, "provider_id": provider_id, "error": str(exc)}
    if not scopes:
        return {"success": False, "provider_id": provider_id, "error": "missing scope config", "status": "missing_scope_config"}
    requested_services = _normalize_requested_services(services) or list(_GOOGLE_SCOPE_MODE_DETAILS.get(resolved_scope_mode, {}).get("services") or [])
    redirect_uri = _build_redirect_uri(provider_id, request_headers=request_headers)
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    _cleanup_pending_states()
    _pending_states[state] = {
        "provider_id": provider_id,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "scope_mode": resolved_scope_mode,
        "services": list(requested_services),
        "scopes": list(scopes),
        "created_at": time.time(),
    }
    params = {
        "client_id": str(client.get("client_id") or ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    authorize_url = f"{_GOOGLE_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    return {
        "success": True,
        "provider_id": provider_id,
        "authorize_url": authorize_url,
        "state": state,
        "redirect_uri": redirect_uri,
        "scope_mode": resolved_scope_mode,
        "services": list(requested_services),
        "scopes": list(scopes),
    }


def _http_post_form(url: str, data: dict[str, str], *, timeout: float = 30.0) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_json(url: str, access_token: str, *, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    request.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _exchange_code_for_tokens(
    provider_id: str,
    code: str,
    *,
    redirect_uri: str,
    code_verifier: str,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    client = load_provider_client_config(provider_id, pack_root=pack_root)
    if client is None:
        raise RuntimeError("oauth client config is not saved")
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": str(client.get("client_id") or ""),
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    client_secret = str(client.get("client_secret") or "").strip()
    if client_secret:
        payload["client_secret"] = client_secret
    return _http_post_form(_GOOGLE_TOKEN_URL, payload)


def _refresh_access_token(provider_id: str, *, pack_root: Path | None = None) -> dict[str, Any]:
    client = load_provider_client_config(provider_id, pack_root=pack_root)
    if client is None:
        raise RuntimeError("oauth client config is not saved")
    refresh_token = _read_secret(
        _secret_key(_REFRESH_TOKEN_SECRET_KEYS, provider_id),
        f"defaultspack.oauth:{provider_id}:refresh",
        pack_root=pack_root,
    )
    if not refresh_token:
        raise RuntimeError("oauth refresh token is not available")
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": str(client.get("client_id") or ""),
    }
    client_secret = str(client.get("client_secret") or "").strip()
    if client_secret:
        payload["client_secret"] = client_secret
    token_data = _http_post_form(_GOOGLE_TOKEN_URL, payload)
    if "refresh_token" not in token_data:
        token_data["refresh_token"] = refresh_token
    return token_data


def _fetch_userinfo(provider_id: str, access_token: str) -> dict[str, Any]:
    del provider_id
    return _http_get_json(_GOOGLE_USERINFO_URL, access_token)


def finish_provider_oauth(
    provider_id: str,
    payload: dict[str, Any],
    *,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}
    error = str(payload.get("error") or "").strip()
    if error:
        return {
            "success": False,
            "provider_id": provider_id,
            "error": str(payload.get("error_description") or error),
            "status_code": 400,
        }
    code = str(payload.get("code") or "").strip()
    state = str(payload.get("state") or "").strip()
    if not code:
        return {"success": False, "provider_id": provider_id, "error": "missing authorization code", "status_code": 400}
    if not state:
        return {"success": False, "provider_id": provider_id, "error": "missing state", "status_code": 400}

    _cleanup_pending_states()
    pending = _pending_states.pop(state, None)
    if pending is None or str(pending.get("provider_id") or "") != provider_id:
        return {"success": False, "provider_id": provider_id, "error": "invalid or expired state", "status_code": 400}

    try:
        token_data = _exchange_code_for_tokens(
            provider_id,
            code,
            redirect_uri=str(pending.get("redirect_uri") or ""),
            code_verifier=str(pending.get("code_verifier") or ""),
            pack_root=pack_root,
        )
    except urllib.error.HTTPError as exc:
        try:
            details = exc.read().decode("utf-8", errors="replace")
        except Exception:
            details = ""
        return {
            "success": False,
            "provider_id": provider_id,
            "error": f"token exchange failed (HTTP {exc.code}) {details}".strip(),
            "status_code": 502,
        }
    except (urllib.error.URLError, OSError, RuntimeError) as exc:
        return {
            "success": False,
            "provider_id": provider_id,
            "error": f"token exchange failed: {exc}",
            "status_code": 502,
        }

    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        return {"success": False, "provider_id": provider_id, "error": "oauth token response did not include an access token", "status_code": 502}
    if not str(token_data.get("scope") or "").strip():
        token_data["scope"] = " ".join(str(item) for item in pending.get("scopes") or [] if str(item).strip())
    token_data["scope_mode"] = str(pending.get("scope_mode") or "")
    token_data["services"] = list(pending.get("services") or [])

    userinfo: dict[str, Any] = {}
    try:
        userinfo = _fetch_userinfo(provider_id, access_token)
    except Exception:
        userinfo = {}

    try:
        saved = save_provider_oauth_connection(provider_id, token_data, userinfo=userinfo, pack_root=pack_root)
    except RuntimeError as exc:
        return {"success": False, "provider_id": provider_id, "error": str(exc), "status_code": 500}
    return {
        **saved,
        "provider_id": provider_id,
        "success": True,
        "redirect_uri": str(pending.get("redirect_uri") or ""),
    }


def disconnect_provider_oauth(provider_id: str, *, pack_root: Path | None = None) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}
    _delete_secret(
        _secret_key(_ACCESS_TOKEN_SECRET_KEYS, provider_id),
        actor="defaultspack",
        reason=f"disconnect {provider_id} oauth access token",
        pack_root=pack_root,
    )
    _delete_secret(
        _secret_key(_REFRESH_TOKEN_SECRET_KEYS, provider_id),
        actor="defaultspack",
        reason=f"disconnect {provider_id} oauth refresh token",
        pack_root=pack_root,
    )
    _delete_secret(
        _secret_key(_ID_TOKEN_SECRET_KEYS, provider_id),
        actor="defaultspack",
        reason=f"disconnect {provider_id} oauth id token",
        pack_root=pack_root,
    )
    existing = _provider_metadata(provider_id, pack_root=pack_root)
    metadata = {
        **existing,
        "provider_id": provider_id,
        "connected": False,
        "expires_at": "",
        "updated_at": _isoformat(_now_utc()),
        "disconnected_at": _isoformat(_now_utc()),
        "has_refresh_token": False,
    }
    _write_provider_metadata(provider_id, metadata, pack_root=pack_root)
    _reset_ai_client()
    return {"success": True, "provider_id": provider_id, "connected": False}


def get_provider_access_token(provider_id: str, *, pack_root: Path | None = None) -> str | None:
    provider_id = str(provider_id or "").strip()
    if not provider_supports_oauth(provider_id):
        return None
    access_key = _secret_key(_ACCESS_TOKEN_SECRET_KEYS, provider_id)
    access_token = _read_secret(access_key, f"defaultspack.oauth:{provider_id}:access", pack_root=pack_root)
    if access_token and _has_valid_access_token(provider_id, pack_root=pack_root):
        return access_token
    refresh_key = _secret_key(_REFRESH_TOKEN_SECRET_KEYS, provider_id)
    if not _read_secret(refresh_key, f"defaultspack.oauth:{provider_id}:refresh", pack_root=pack_root):
        return access_token or None
    try:
        token_data = _refresh_access_token(provider_id, pack_root=pack_root)
        access_token = str(token_data.get("access_token") or "").strip()
        if not access_token:
            return None
        try:
            userinfo = _fetch_userinfo(provider_id, access_token)
        except Exception:
            userinfo = {}
        save_provider_oauth_connection(provider_id, token_data, userinfo=userinfo, pack_root=pack_root)
        return access_token
    except Exception:
        return access_token or None


def provider_oauth_status(provider_id: str, *, pack_root: Path | None = None) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    provider = _connection_provider(provider_id, pack_root=pack_root)
    supported = provider_supports_oauth(provider_id)
    client = load_provider_client_config(provider_id, pack_root=pack_root) if supported else None
    metadata = _provider_metadata(provider_id, pack_root=pack_root) if supported else {}
    connected = provider_has_oauth_connection(provider_id, pack_root=pack_root) if supported else False
    default_scopes = list(provider.oauth.default_scopes if provider and provider.oauth else [])
    if connected:
        connection_status = "connected"
        status_label = "Connected"
        disabled_reason = ""
    elif provider is None or provider.oauth is None:
        connection_status = "unsupported"
        status_label = "Unsupported"
        disabled_reason = "Official app required"
    elif provider_id not in _OAUTH_RUNTIME_PROVIDER_IDS:
        if not default_scopes:
            connection_status = "missing_scope_config"
            status_label = "Missing scope config"
            disabled_reason = "Configure self-host OAuth"
        else:
            connection_status = "needs_official_app"
            status_label = "Official app required"
            disabled_reason = "Official app required"
    elif client is None:
        connection_status = "missing_self_host_config"
        status_label = "Client config needed"
        disabled_reason = "Configure self-host OAuth"
    else:
        connection_status = "not_connected"
        status_label = "Ready to connect"
        disabled_reason = ""
    scope_mode = str(metadata.get("scope_mode") or "google_identity").strip() if provider_id == "google" else ""
    try:
        status_scopes = list(metadata.get("scopes") or _default_scopes(provider_id, scope_mode or None))
    except ValueError:
        status_scopes = list(metadata.get("scopes") or default_scopes)
    return {
        "supported": supported,
        "backend_supported": provider_id in _OAUTH_RUNTIME_PROVIDER_IDS,
        "provider_id": provider_id,
        "display_label": str(provider.display_name if provider else provider_id),
        "service_kind": str(provider.service_kind if provider else ""),
        "auth_type": str(provider.auth_type if provider else ""),
        "client_configured": client is not None,
        "client_label": _client_id_label(str((client or {}).get("client_id") or "")),
        "connected": connected,
        "connect_enabled": supported and client is not None,
        "connection_status": connection_status,
        "status_label": status_label,
        "disabled_reason": disabled_reason,
        "display_name": str(metadata.get("display_name") or "").strip(),
        "email": str(metadata.get("email") or "").strip(),
        "picture_url": str(metadata.get("picture_url") or "").strip(),
        "scopes": status_scopes,
        "default_scopes": default_scopes,
        "scope_mode": scope_mode,
        "scope_modes": _google_scope_mode_rows() if provider_id == "google" else [],
        "services": list(metadata.get("services") or []),
        "expires_at": str(metadata.get("expires_at") or ""),
        "has_refresh_token": bool(metadata.get("has_refresh_token")),
        "redirect_path": f"/api/ai/oauth/{provider_id}/callback" if supported else "",
        "config_hint": (
            "Paste a Google OAuth desktop client JSON or client ID to enable Google AI or Workspace browser login."
            if provider_id == "google"
            else "Cloudflare OAuth scopes are not configured for this build. Use the official app flow or configure a self-host OAuth client with explicit scopes."
            if connection_status == "missing_scope_config"
            else ""
        ),
    }


def provider_oauth_statuses(*, pack_root: Path | None = None) -> dict[str, dict[str, Any]]:
    return {
        provider_id: provider_oauth_status(provider_id, pack_root=pack_root)
        for provider_id in sorted(_connection_provider_ids(pack_root=pack_root) | _OAUTH_RUNTIME_PROVIDER_IDS)
    }
