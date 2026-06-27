from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from ...components import get_domain_component_registry


def _provider_id(component_manifest: dict[str, Any]) -> str:
    return str(component_manifest.get("provider_id") or component_manifest.get("id") or "").strip()


def _load_json_entrypoint(component_manifest: dict[str, Any], key: str) -> Any:
    entrypoints = component_manifest.get("entrypoints")
    rel_path = entrypoints.get(key) if isinstance(entrypoints, dict) else None
    if not isinstance(rel_path, str) or not rel_path.strip():
        return None
    source_path = component_manifest.get("source_path")
    if not isinstance(source_path, str) or not source_path:
        return None
    base = _lexical_absolute_path(Path(source_path).parent)
    path = _lexical_absolute_path(Path(source_path).parent / rel_path)
    if not _path_is_within(path, base):
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _trusted_provider_component_root() -> Path:
    return Path(__file__).parents[3] / "domain" / "providers"


def _lexical_absolute_path(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.path.normpath(os.fspath(path))))


def _normalized_path_text(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(str(_lexical_absolute_path(path)))


def _path_is_within(path: Path, root: Path) -> bool:
    candidate = _normalized_path_text(path)
    boundary = _normalized_path_text(root)
    if candidate == boundary:
        return True
    return candidate.startswith(boundary.rstrip("\\/") + os.sep)


def _is_trusted_runtime_provider_component(component: Any) -> bool:
    """Return whether a provider component may supply executable runtime config.

    Domain component discovery intentionally catalogs sibling packs and explicit extra
    roots for metadata, but provider manifests are executable runtime configuration:
    an entrypoint is imported and instantiated during provider auto-detection.  Only
    provider components bundled inside the canonical defaultspack provider directory
    are trusted to contribute those runtime manifests.
    """
    try:
        manifest_path = Path(component.manifest_path)
    except (AttributeError, TypeError, ValueError):
        return False
    return _path_is_within(manifest_path, _trusted_provider_component_root())


def provider_component_metadata_map() -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    registry = get_domain_component_registry()
    for component in registry.list("providers"):
        manifest = component.as_dict()
        provider_id = _provider_id(manifest)
        if not provider_id:
            continue
        metadata = manifest.get("provider_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        provider_manifest = manifest.get("provider_manifest")
        if (
            not isinstance(provider_manifest, dict)
            or not _is_trusted_runtime_provider_component(component)
        ):
            provider_manifest = {}
        items[provider_id] = {
            **deepcopy(metadata),
            "component_id": component.id,
            "component_manifest_path": manifest.get("source_path", ""),
            "source_pack_id": component.source_pack_id,
            "provider_manifest": deepcopy(provider_manifest),
        }
    return items


def provider_manifests_from_components() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for provider_id, metadata in provider_component_metadata_map().items():
        provider_manifest = metadata.get("provider_manifest")
        if not isinstance(provider_manifest, dict) or not provider_manifest:
            continue
        manifest = deepcopy(provider_manifest)
        manifest.setdefault("id", provider_id)
        manifest.setdefault("source_pack_id", metadata.get("source_pack_id", ""))
        manifest.setdefault("component_manifest_path", metadata.get("component_manifest_path", ""))
        manifests[provider_id] = manifest
    return manifests


def model_manifests_from_provider_components(provider_id: str) -> list[dict[str, Any]]:
    provider_id = str(provider_id or "").strip()
    if not provider_id:
        return []
    registry = get_domain_component_registry()
    models: list[dict[str, Any]] = []
    for component in registry.list("providers"):
        manifest = component.as_dict()
        if _provider_id(manifest) != provider_id:
            continue
        raw_models = _load_json_entrypoint(manifest, "models")
        if isinstance(raw_models, dict):
            raw_models = raw_models.get("models")
        if not isinstance(raw_models, list):
            continue
        for raw in raw_models:
            if not isinstance(raw, dict):
                continue
            item = deepcopy(raw)
            item.setdefault("provider_id", provider_id)
            item.setdefault("provider", provider_id)
            metadata = dict(item.get("metadata", {})) if isinstance(item.get("metadata"), dict) else {}
            metadata.setdefault("component_id", component.id)
            metadata.setdefault("component_manifest_path", manifest.get("source_path", ""))
            metadata.setdefault("source_pack_id", component.source_pack_id)
            item["metadata"] = metadata
            models.append(item)
    return models
