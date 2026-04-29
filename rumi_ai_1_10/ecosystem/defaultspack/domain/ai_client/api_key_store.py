from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List


PROVIDER_SECRET_KEYS: Dict[str, List[str]] = {
    "openrouter": ["OPENROUTER_API_KEY"],
}


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


def _reset_ai_client() -> None:
    try:
        from domain.ai_client.client import AIClient

        AIClient._instance = None
    except Exception:
        pass


def provider_secret_key(provider_id: str) -> str:
    keys = PROVIDER_SECRET_KEYS.get(str(provider_id or "").strip(), [])
    return keys[0] if keys else ""


def provider_has_api_key(provider_id: str, *, pack_root: Path | None = None) -> bool:
    key = provider_secret_key(provider_id)
    if not key:
        return False
    if os.environ.get(key, "").strip():
        return True
    secret_path = _secrets_dir(pack_root) / f"{key}.json"
    if not secret_path.exists():
        return False
    return _get_store(pack_root).has_secret(key)


def set_provider_api_key(
    provider_id: str,
    value: str,
    *,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    key = provider_secret_key(provider_id)
    if not key:
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}

    cleaned = str(value or "").strip()
    if not cleaned:
        result = _get_store(pack_root).delete_secret(
            key,
            actor="defaultspack",
            reason=f"clear {provider_id} api key",
        )
        os.environ.pop(key, None)
        if result.success:
            _reset_ai_client()
        return {
            "success": bool(result.success),
            "provider_id": provider_id,
            "key": key,
            "configured": False,
            "cleared": True,
            "error": result.error,
        }

    result = _get_store(pack_root).set_secret(
        key,
        cleaned,
        actor="defaultspack",
        reason=f"set {provider_id} api key",
    )
    if result.success:
        os.environ[key] = cleaned
        _reset_ai_client()
    return {
        "success": bool(result.success),
        "provider_id": provider_id,
        "key": key,
        "configured": bool(result.success),
        "created": bool(result.created),
        "error": result.error,
    }


def load_provider_api_keys_into_env(*, pack_root: Path | None = None) -> dict[str, bool]:
    loaded: dict[str, bool] = {}
    for provider_id, keys in PROVIDER_SECRET_KEYS.items():
        configured = False
        for key in keys:
            if os.environ.get(key, "").strip():
                configured = True
                continue
            if not (_secrets_dir(pack_root) / f"{key}.json").exists():
                continue
            store = _get_store(pack_root)
            value = store._internal_read_value(
                key,
                caller_id=f"defaultspack.ai_client:{provider_id}",
            )
            if value:
                os.environ[key] = value
                configured = True
        loaded[provider_id] = configured
    return loaded


def provider_key_status(*, pack_root: Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "provider_id": provider_id,
            "key": keys[0],
            "configured": provider_has_api_key(provider_id, pack_root=pack_root),
        }
        for provider_id, keys in sorted(PROVIDER_SECRET_KEYS.items())
        if keys
    ]
