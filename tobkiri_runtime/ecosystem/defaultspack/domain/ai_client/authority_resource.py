from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from domain.ai_client.providers import get_all_known_models, get_provider_catalog_map


DEFAULTSPACK_PACK_ID = "defaultspack"
DEFAULTSPACK_APP_DISPLAY_NAME = "defaultspack v2"


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _provider_catalog_entry(provider_id: str) -> dict[str, Any]:
    try:
        catalog = get_provider_catalog_map(active_provider_ids={provider_id})
    except Exception:
        catalog = {}
    entry = catalog.get(provider_id)
    return dict(entry or {})


def _provider_display_name(provider: Any, provider_id: str, entry: dict[str, Any]) -> str:
    for value in (
        getattr(provider, "display_name", ""),
        getattr(provider, "DISPLAY_NAME", ""),
        entry.get("display_name"),
        entry.get("name"),
        provider_id,
    ):
        cleaned = _clean_string(value)
        if cleaned:
            return cleaned
    return provider_id


def _model_candidates(provider: Any, provider_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if provider is not None and callable(getattr(provider, "list_models", None)):
        try:
            listed = provider.list_models() or []
        except Exception:
            listed = []
        candidates.extend(dict(item) for item in listed if isinstance(item, dict))
    if provider is not None and not candidates:
        known_models = getattr(provider, "KNOWN_MODELS", []) or []
        candidates.extend(dict(item) for item in known_models if isinstance(item, dict))
    try:
        candidates.extend(
            dict(item)
            for item in get_all_known_models(provider_id=provider_id, active_provider_ids={provider_id})
            if isinstance(item, dict)
        )
    except Exception:
        pass
    return candidates


def _model_entry(provider: Any, provider_id: str, model_id: str, model_ref: str) -> dict[str, Any]:
    model_id = _clean_string(model_id)
    model_ref = _clean_string(model_ref)
    qualified = model_ref if model_ref.startswith(f"{provider_id}/") else f"{provider_id}/{model_id}"
    for candidate in _model_candidates(provider, provider_id):
        candidate_id = _clean_string(candidate.get("model_id") or candidate.get("model_name"))
        candidate_qualified = _clean_string(candidate.get("id") or candidate.get("qualified_model_id"))
        names = {
            candidate_id,
            candidate_qualified,
            _clean_string(candidate.get("name")),
            _clean_string(candidate.get("display_name")),
        }
        if model_id in names or model_ref in names or qualified in names:
            return candidate
    return {}


def _base_url(provider: Any, entry: dict[str, Any], api_metadata: dict[str, Any]) -> str:
    for value in (
        api_metadata.get("base_url"),
        getattr(provider, "_base_url", ""),
        getattr(provider, "BASE_URL", ""),
        getattr(provider, "_default_base_url", ""),
        (entry.get("metadata") or {}).get("default_base_url") if isinstance(entry.get("metadata"), dict) else "",
        entry.get("default_base_url"),
    ):
        cleaned = _clean_string(value).rstrip("/")
        if cleaned:
            return cleaned
    return ""


def _endpoint_path(model_entry: dict[str, Any], api_metadata: dict[str, Any]) -> str:
    metadata = model_entry.get("metadata") if isinstance(model_entry.get("metadata"), dict) else {}
    path = _clean_string(api_metadata.get("endpoint_path") or metadata.get("endpoint_path"))
    if not path:
        path = "/chat/completions"
    return path if path.startswith("/") else f"/{path}"


def _endpoint_details(base_url: str, endpoint_path: str) -> dict[str, Any]:
    if not base_url:
        return {}
    endpoint_url = f"{base_url.rstrip('/')}{endpoint_path}"
    parsed = urlparse(endpoint_url)
    details: dict[str, Any] = {
        "endpoint_url": endpoint_url,
        "endpoint_path": endpoint_path,
    }
    if parsed.hostname:
        details["domain"] = parsed.hostname
    if parsed.scheme:
        details["transport"] = parsed.scheme
    if parsed.port is not None:
        details["port"] = parsed.port
    elif parsed.scheme == "https":
        details["port"] = 443
    elif parsed.scheme == "http":
        details["port"] = 80
    return details


def build_provider_authority_resource(
    *,
    permission_id: str,
    resource_kind: str,
    provider_id: str,
    api_id: str,
    model_id: str,
    model_ref: str,
    provider: Any = None,
    api_metadata: dict[str, Any] | None = None,
    stream: bool = False,
) -> dict[str, Any]:
    provider_id = _clean_string(provider_id)
    api_id = _clean_string(api_id) or "legacy"
    model_id = _clean_string(model_id)
    model_ref = _clean_string(model_ref)
    metadata = dict(api_metadata or {})
    entry = _provider_catalog_entry(provider_id)
    model = _model_entry(provider, provider_id, model_id, model_ref)
    model_metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    provider_display_name = _provider_display_name(provider, provider_id, entry)
    model_display_name = _clean_string(model.get("display_name") or model.get("name") or model_id)
    base_url = _base_url(provider, entry, metadata)
    endpoint_path = _endpoint_path(model, metadata)

    provider_metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    resource = {
        "kind": _clean_string(resource_kind or permission_id),
        "provider_id": provider_id,
        "api_id": api_id,
        "model_id": model_id,
        "model_ref": model_ref,
        "stream": bool(stream),
        "pack_id": DEFAULTSPACK_PACK_ID,
        "app_display_name": DEFAULTSPACK_APP_DISPLAY_NAME,
        "provider_display_name": provider_display_name,
        "model_display_name": model_display_name,
        "credential_label": f"{provider_display_name} API key",
        "provider_kind": _clean_string(provider_metadata.get("provider_kind") or entry.get("kind")),
    }
    if model_metadata.get("transport"):
        resource["provider_transport"] = _clean_string(model_metadata.get("transport"))
    resource.update(_endpoint_details(base_url, endpoint_path))
    return resource


def provider_authority_reason(permission_id: str, resource: dict[str, Any]) -> str:
    app_name = _clean_string(resource.get("app_display_name")) or DEFAULTSPACK_APP_DISPLAY_NAME
    provider_name = _clean_string(resource.get("provider_display_name") or resource.get("provider_id"))
    provider_subject = provider_name if provider_name.lower().endswith("provider") else f"{provider_name} provider"
    model_name = _clean_string(resource.get("model_display_name") or resource.get("model_id"))
    credential_label = _clean_string(resource.get("credential_label")) or f"{provider_name} API key"
    endpoint_url = _clean_string(resource.get("endpoint_url"))
    if permission_id == "api_key.use":
        return f"{app_name}: {credential_label} を {model_name} との通信に使います。"
    if permission_id == "network.egress":
        target = endpoint_url or _clean_string(resource.get("domain")) or provider_name
        return f"{app_name}: {provider_subject} が {target} へアクセスします。"
    return f"{app_name}: {provider_subject} を {model_name} との通信に使います。"
