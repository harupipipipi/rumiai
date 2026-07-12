from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ...components import get_domain_component_registry
from ..metadata_json import load_strict_metadata_json
from ..model_metadata_schema import validate_model_catalog_source


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
    path = (Path(source_path).parent / rel_path).resolve()
    try:
        return load_strict_metadata_json(path)
    except OSError:
        return None


def _trusted_provider_component_root() -> Path:
    return Path(__file__).resolve().parents[3] / "domain" / "providers"


def _is_trusted_runtime_provider_component(component: Any) -> bool:
    """Return whether a provider component may supply executable runtime config.

    Domain component discovery intentionally catalogs sibling packs and explicit extra
    roots for metadata, but provider manifests are executable runtime configuration:
    an entrypoint is imported and instantiated during provider auto-detection.  Only
    provider components bundled inside the canonical defaultspack provider directory
    are trusted to contribute those runtime manifests.
    """
    try:
        manifest_path = Path(component.manifest_path).resolve()
        manifest_path.relative_to(_trusted_provider_component_root().resolve())
    except (AttributeError, OSError, ValueError):
        return False
    return True


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
        if raw_models is not None and _is_trusted_runtime_provider_component(component):
            source_path = manifest.get("source_path", "")
            rel_path = (manifest.get("entrypoints") or {}).get("models") if isinstance(manifest.get("entrypoints"), dict) else ""
            validate_model_catalog_source(
                raw_models,
                path=(Path(source_path).parent / rel_path).resolve() if source_path and rel_path else source_path,
            )
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
