from __future__ import annotations

import os
from pathlib import Path
from typing import Any


_CODEX_TOKEN_KEY = "RUMICODEX_ACCESS_TOKEN"
_CODEX_TOKEN_ENV_KEYS = ("RUMI_CODEX_ACCESS_TOKEN", "CODEX_ACCESS_TOKEN")


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _secrets_dir(pack_root: Path | None = None) -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_SECRETS_DIR", "").strip()
    if override:
        return Path(override)
    return (pack_root or _pack_root()) / "user_data" / "secrets"


def _get_store(pack_root: Path | None = None):
    from core_runtime.secrets_store import SecretsStore

    return SecretsStore(str(_secrets_dir(pack_root)))


def _read_secret_value(pack_root: Path | None = None) -> str:
    for key in _CODEX_TOKEN_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return str(
            _get_store(pack_root)._internal_read_value(
                _CODEX_TOKEN_KEY,
                caller_id="defaultspack.codex:access_token",
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _stored_token_exists(pack_root: Path | None = None) -> bool:
    if not _secrets_dir(pack_root).exists():
        return False
    try:
        return any(
            meta.key == _CODEX_TOKEN_KEY and meta.exists and not meta.deleted
            for meta in _get_store(pack_root).list_keys()
        )
    except Exception:
        return False


def read_codex_access_token(*, pack_root: Path | None = None) -> str:
    return _read_secret_value(pack_root)


def save_codex_access_token(value: str, *, pack_root: Path | None = None) -> dict[str, Any]:
    token = str(value or "").strip()
    if not token:
        return {"success": False, "provider_id": "codex", "error": "codex access token is required"}
    result = _get_store(pack_root).set_secret(
        _CODEX_TOKEN_KEY,
        token,
        actor="defaultspack",
        reason="save codex access token",
    )
    if not result.success:
        return {"success": False, "provider_id": "codex", "error": result.error or "failed to save codex token"}
    return {
        "success": True,
        "provider_id": "codex",
        "configured": True,
        "created": bool(result.created),
        "status": codex_connection_status(pack_root=pack_root),
    }


def clear_codex_access_token(*, pack_root: Path | None = None) -> dict[str, Any]:
    result = _get_store(pack_root).delete_secret(
        _CODEX_TOKEN_KEY,
        actor="defaultspack",
        reason="clear codex access token",
    )
    return {
        "success": bool(result.success),
        "provider_id": "codex",
        "configured": False,
        "cleared": True,
        "error": result.error,
        "status": codex_connection_status(pack_root=pack_root),
    }


def codex_connection_status(*, pack_root: Path | None = None) -> dict[str, Any]:
    env_configured = any(bool(os.environ.get(key, "").strip()) for key in _CODEX_TOKEN_ENV_KEYS)
    stored_configured = _stored_token_exists(pack_root)
    configured = bool(env_configured or stored_configured or _read_secret_value(pack_root))
    connection_status = "connected" if configured else "missing_token"
    return {
        "supported": True,
        "backend_supported": True,
        "provider_id": "codex",
        "display_label": "Codex",
        "service_kind": "dev",
        "auth_type": "access_token",
        "credential_kind": "codex_access_token",
        "connected": configured,
        "configured": configured,
        "token_configured": configured,
        "token_source": "environment" if env_configured else "secret_store" if stored_configured else "missing",
        "can_clear": stored_configured,
        "connect_enabled": False,
        "connection_status": connection_status,
        "status_label": "Token saved" if configured else "Token needed",
        "disabled_reason": "" if configured else "Save Codex access token",
        "config_hint": "Save a Codex access token for local/programmatic workflow use. This is not a Platform API key or Workspace Agent token.",
    }
