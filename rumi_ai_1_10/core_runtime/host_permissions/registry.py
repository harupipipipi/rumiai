"""Host permission registry helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import HOST_PERMISSION_IDS, LEGACY_HOST_PERMISSION_ALIASES, HostPermissionDefinition


REGISTRY_PATH = Path(__file__).with_name("default_registry.json")


def normalize_host_permission_id(permission_id: str) -> str:
    raw = str(permission_id or "").strip()
    return LEGACY_HOST_PERMISSION_ALIASES.get(raw, raw)


@lru_cache(maxsize=1)
def load_host_permission_registry() -> dict[str, HostPermissionDefinition]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("host permission registry must be an object")
    registry: dict[str, HostPermissionDefinition] = {}
    for permission_id, definition in data.items():
        normalized = normalize_host_permission_id(permission_id)
        if normalized not in HOST_PERMISSION_IDS:
            raise ValueError(f"unknown host permission in registry: {permission_id}")
        if not isinstance(definition, dict):
            raise ValueError(f"host permission definition must be object: {permission_id}")
        registry[normalized] = HostPermissionDefinition.from_dict(normalized, definition)
    missing = sorted(HOST_PERMISSION_IDS.difference(registry))
    if missing:
        raise ValueError(f"host permission registry missing ids: {', '.join(missing)}")
    return registry


def get_host_permission_definition(permission_id: str) -> HostPermissionDefinition | None:
    return load_host_permission_registry().get(normalize_host_permission_id(permission_id))


def list_host_permission_definitions() -> list[HostPermissionDefinition]:
    return [load_host_permission_registry()[permission_id] for permission_id in sorted(HOST_PERMISSION_IDS)]


def host_permission_exists(permission_id: str) -> bool:
    return get_host_permission_definition(permission_id) is not None
