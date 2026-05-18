from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..components import get_domain_component_registry


_CATEGORY = "webhooks"


def _manifest_for_kind(kind: str) -> dict[str, Any] | None:
    registry = get_domain_component_registry()
    component = registry.get(_CATEGORY, str(kind or "").strip().lower())
    if component is not None:
        return component.as_dict()
    fallback = registry.get(_CATEGORY, "generic")
    return fallback.as_dict() if fallback is not None else None


def _default_security_from_manifest(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    security = manifest.get("security") if isinstance(manifest, dict) else None
    if not isinstance(security, dict):
        return None
    default = security.get("default")
    return deepcopy(default) if isinstance(default, dict) and default else None


def default_security_for_kind(kind: str) -> dict[str, Any]:
    security = _default_security_from_manifest(_manifest_for_kind(kind))
    if security is not None:
        return security
    generic_security = _default_security_from_manifest(_manifest_for_kind("generic"))
    return generic_security or {"mode": "shared_secret"}


def default_endpoint_payloads() -> list[dict[str, Any]]:
    registry = get_domain_component_registry()
    payloads: list[tuple[int, str, dict[str, Any]]] = []
    for component in registry.list(_CATEGORY):
        manifest = component.as_dict()
        defaults = manifest.get("defaults")
        endpoint = defaults.get("endpoint") if isinstance(defaults, dict) else None
        if not isinstance(endpoint, dict):
            continue
        endpoint_id = str(endpoint.get("id") or "").strip()
        if not endpoint_id:
            continue
        order = manifest.get("order")
        sort_order = int(order) if isinstance(order, int) else 1000
        payloads.append((sort_order, endpoint_id, deepcopy(endpoint)))
    payloads.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in payloads]


def default_endpoint_id_for_provider(provider: str) -> str:
    manifest = _manifest_for_kind(provider)
    defaults = manifest.get("defaults") if isinstance(manifest, dict) else None
    if not isinstance(defaults, dict):
        return ""
    return str(defaults.get("endpoint_id") or "").strip()
