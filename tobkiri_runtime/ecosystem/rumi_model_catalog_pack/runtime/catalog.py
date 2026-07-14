"""Load immutable model catalogs without importing provider execution code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

CATALOG_REVISION = (
    "sha256:88d96e4fd84af79a636730cdb5633895e61348f7369572cb21462901fa753fcc"
)
_ROOT = Path(__file__).resolve().parents[1] / "catalog" / "providers"
_EXTENSION_ROOT = (
    Path(__file__).resolve().parents[1] / "extensions" / "llm" / "providers"
)


def create_model_catalog_operation(client: Any):
    """Create a read-only catalog operation independent of adapter runtime."""
    del client

    def operation(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if name not in {"list", "get", "providers"}:
            raise ValueError(f"unknown model catalog operation: {name}")
        providers, models = _load_catalog()
        provider_id = str(payload.get("provider_id") or "").strip()
        model_id = str(payload.get("model_id") or "").strip()
        if provider_id:
            providers = [
                item for item in providers if item["provider_id"] == provider_id
            ]
            models = [item for item in models if item["provider_id"] == provider_id]
        if model_id:
            models = [item for item in models if item["model_id"] == model_id]
        return {
            "catalog_revision": CATALOG_REVISION,
            "providers": providers,
            "models": models,
        }

    return operation


def _load_catalog() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if _catalog_revision() != CATALOG_REVISION:
        raise RuntimeError("model catalog integrity mismatch")
    provider_items: dict[str, dict[str, Any]] = {}
    model_items: dict[tuple[str, str], dict[str, Any]] = {}
    for manifest_path in sorted(_ROOT.glob("*/manifest.json")):
        manifest = _read_json(manifest_path)
        provider_id = str(
            manifest.get("provider_id") or manifest.get("id") or ""
        ).strip()
        if not provider_id:
            raise ValueError("model catalog provider ID is missing")
        provider_metadata = manifest.get("provider_metadata")
        provider_metadata = (
            provider_metadata if isinstance(provider_metadata, Mapping) else {}
        )
        provider_manifest = manifest.get("provider_manifest")
        provider_manifest = (
            provider_manifest if isinstance(provider_manifest, Mapping) else {}
        )
        provider_items[provider_id] = {
                "provider_id": provider_id,
                "display_name": str(
                    provider_metadata.get("display_name")
                    or manifest.get("display_name")
                    or provider_id
                ),
                "kind": str(provider_metadata.get("kind") or "unknown"),
                "capabilities": _strings(
                    provider_metadata.get("catalog_features")
                    or manifest.get("catalog_features")
                ),
                "execution_provider_instance_id": "provider.compatibility",
                "available": bool(provider_manifest.get("enabled", True)),
                "catalog_revision": CATALOG_REVISION,
        }
        model_path = manifest_path.parent / "models.json"
        if not model_path.is_file():
            continue
        raw_models = _read_json(model_path)
        raw_models = (
            raw_models.get("models") if isinstance(raw_models, Mapping) else None
        )
        if not isinstance(raw_models, list):
            raise ValueError("model catalog models payload is invalid")
        for raw in raw_models:
            if isinstance(raw, Mapping):
                item = _model(provider_id, raw, provider_manifest)
                model_items[(provider_id, item["model_id"])] = item
    for manifest_path in sorted(_EXTENSION_ROOT.glob("*/manifest.json")):
        manifest = _read_json(manifest_path)
        provider_id = str(manifest.get("id") or "").strip()
        if not provider_id:
            raise ValueError("extension model catalog provider ID is missing")
        provider_items[provider_id] = {
            "provider_id": provider_id,
            "display_name": str(manifest.get("display_name") or provider_id),
            "kind": str(manifest.get("kind") or "unknown"),
            "capabilities": _strings(manifest.get("catalog_features")),
            "execution_provider_instance_id": "provider.compatibility",
            "available": bool(manifest.get("enabled", True)),
            "catalog_revision": CATALOG_REVISION,
        }
        for model_path in sorted((manifest_path.parent / "models").glob("*.json")):
            raw = _read_json(model_path)
            item = _model(provider_id, raw, manifest)
            model_items[(provider_id, item["model_id"])] = item
    providers = list(provider_items.values())
    models = list(model_items.values())
    providers.sort(key=lambda item: item["provider_id"])
    models.sort(
        key=lambda item: (
            int(item["priority"]),
            item["provider_id"],
            item["model_id"],
        )
    )
    return providers, models


def _model(
    provider_id: str,
    value: Mapping[str, Any],
    provider_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    raw_model_id = str(value.get("model_id") or value.get("id") or "").strip()
    if not raw_model_id:
        raise ValueError("model catalog model ID is missing")
    capability_map = value.get("capabilities")
    capability_map = capability_map if isinstance(capability_map, Mapping) else {}
    capabilities = sorted(
        str(key) for key, enabled in capability_map.items() if enabled is True
    )
    modalities = ["text"]
    if capability_map.get("image_input"):
        modalities.append("image")
    if capability_map.get("audio_input"):
        modalities.append("audio")
    context_length = value.get("context_length", value.get("context_window", 0))
    pricing = value.get("pricing")
    pricing = pricing if isinstance(pricing, Mapping) else {}
    return {
        "model_id": str(value.get("id") or f"{provider_id}/{raw_model_id}"),
        "provider_model_id": raw_model_id,
        "provider_id": provider_id,
        "execution_provider_instance_id": "provider.compatibility",
        "health_provider_instance_id": f"provider.{provider_id}",
        "display_name": str(value.get("display_name") or raw_model_id),
        "capabilities": capabilities,
        "modalities": modalities,
        "context_length": _integer(context_length),
        "input_cost": _number(pricing.get("input")),
        "output_cost": _number(pricing.get("output")),
        "priority": _integer(value.get("priority"), default=100),
        "available": bool(
            value.get("enabled", True) and provider_manifest.get("enabled", True)
        ),
        "data_residency": str(value.get("data_residency") or "unknown"),
        "catalog_revision": CATALOG_REVISION,
    }


def _catalog_revision() -> str:
    lines = []
    pack_root = _ROOT.parent.parent
    paths = list(_ROOT.glob("*/*.json"))
    paths.extend(_EXTENSION_ROOT.glob("**/*.json"))
    for path in sorted(paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(pack_root)}\n")
    return "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("model catalog resource is not an object")
    return value


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item) for item in value if str(item).strip()})


def _integer(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
