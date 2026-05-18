from __future__ import annotations

import re
from typing import Any

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-/]{1,256}$")
_STATUSES = {"experimental", "stable", "legacy"}
_OBJECT_FIELDS = {
    "entrypoints",
    "security",
    "ui",
    "policy",
    "capabilities",
    "compatibility",
}
_LIST_FIELDS = {
    "routes",
    "profiles",
    "conversion_targets",
}


class ComponentManifestError(ValueError):
    pass


def _require_string(manifest: dict[str, Any], key: str) -> str:
    value = str(manifest.get(key) or "").strip()
    if not value:
        raise ComponentManifestError(f"manifest.{key} is required")
    return value


def _optional_object(manifest: dict[str, Any], key: str) -> dict[str, Any]:
    value = manifest.get(key)
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise ComponentManifestError(f"manifest.{key} must be an object")


def _optional_list(manifest: dict[str, Any], key: str) -> list[Any]:
    value = manifest.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    raise ComponentManifestError(f"manifest.{key} must be an array")


def validate_component_manifest(
    raw: dict[str, Any],
    *,
    expected_category: str | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ComponentManifestError("manifest root must be an object")

    manifest = dict(raw)
    component_id = _require_string(manifest, "id")
    if not _ID_PATTERN.match(component_id):
        raise ComponentManifestError("manifest.id contains unsupported characters")

    category = _require_string(manifest, "category")
    if expected_category and category != expected_category:
        raise ComponentManifestError(
            f"manifest.category mismatch: expected={expected_category}, actual={category}"
        )

    kind = _require_string(manifest, "kind")
    version = _require_string(manifest, "version")
    status = _require_string(manifest, "status").lower()
    if status not in _STATUSES:
        raise ComponentManifestError(
            "manifest.status must be one of experimental, stable, legacy"
        )

    normalized = dict(manifest)
    normalized["id"] = component_id
    normalized["category"] = category
    normalized["kind"] = kind
    normalized["version"] = version
    normalized["status"] = status
    normalized["display_name"] = str(manifest.get("display_name") or component_id)
    normalized["description"] = str(manifest.get("description") or "")
    normalized["owner"] = str(manifest.get("owner") or manifest.get("source_pack_id") or "")

    for key in _OBJECT_FIELDS:
        if key in manifest:
            normalized[key] = _optional_object(manifest, key)
    for key in _LIST_FIELDS:
        if key in manifest:
            normalized[key] = _optional_list(manifest, key)

    aliases = manifest.get("aliases")
    if aliases is not None and not isinstance(aliases, (dict, list)):
        raise ComponentManifestError("manifest.aliases must be an object or array")
    if isinstance(aliases, list):
        normalized["aliases"] = [str(item).strip() for item in aliases if str(item).strip()]
    elif isinstance(aliases, dict):
        normalized["aliases"] = dict(aliases)

    return normalized
