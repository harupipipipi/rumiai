"""Provider authority gating helpers."""

from __future__ import annotations

from typing import Any

from domain.ai_client.api_key_store import provider_has_api_key, provider_named_api_keys
from domain.ai_client.oauth_store import provider_has_oauth_connection


def provider_api_key_configured(provider_id: str, api_id: str = "legacy") -> bool:
    provider_id = str(provider_id or "").strip()
    api_id = str(api_id or "").strip() or "legacy"
    if not provider_id:
        return False
    if api_id not in {"", "main", "legacy"}:
        for item in provider_named_api_keys(provider_id):
            if str(item.get("api_id") or "").strip() == api_id and item.get("configured"):
                return True
    return provider_has_api_key(provider_id)


def provider_requires_authority(provider_id: str, *, provider: Any = None, api_id: str = "legacy") -> bool:
    provider_id = str(provider_id or "").strip()
    if not provider_id:
        return False
    if provider_id in {"stub", "rumi"}:
        return True
    try:
        if provider_api_key_configured(provider_id, api_id):
            return True
    except Exception:
        return True
    try:
        if provider_has_oauth_connection(provider_id):
            return True
    except Exception:
        return True
    if bool(getattr(provider, "_credential_required", False)):
        return True
    if bool(getattr(provider, "_api_key_envs", None)):
        return True
    return _catalog_requires_authority(provider_id, provider)


def _catalog_requires_authority(provider_id: str, provider: Any) -> bool:
    if provider is None:
        return False
    module_name = str(getattr(getattr(provider, "__class__", None), "__module__", ""))
    if not module_name.startswith("domain.ai_client.providers."):
        return False
    try:
        from domain.ai_client.providers import get_provider_catalog_map

        entry = get_provider_catalog_map().get(provider_id, {})
    except Exception:
        return True
    kind = str(entry.get("kind") or "").strip().lower()
    if kind in {"builtin", "local"}:
        return False
    default_base_url = str(entry.get("default_base_url") or "").strip().lower()
    if default_base_url.startswith(("local://", "http://127.0.0.1", "http://localhost")):
        return False
    return bool(kind or entry.get("credential_required", True))
