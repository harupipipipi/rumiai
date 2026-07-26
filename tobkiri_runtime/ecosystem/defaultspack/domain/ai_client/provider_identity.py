from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_LEGACY_PROVIDER_ALIASES = {
    "llama_cpp": "llamacpp",
    "llama-cpp": "llamacpp",
    "openai-compatible": "openai_compatible",
}


@lru_cache(maxsize=1)
def provider_alias_map() -> dict[str, str]:
    """Return the canonical provider identity map owned by catalog manifests."""

    aliases = dict(_LEGACY_PROVIDER_ALIASES)
    catalog_root = (
        Path(__file__).resolve().parents[3]
        / "rumi_model_catalog_pack"
        / "catalog"
        / "providers"
    )
    for path in sorted(catalog_root.glob("*/manifest.json")):
        try:
            manifest: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        canonical = str(
            manifest.get("provider_id") or manifest.get("id") or ""
        ).strip()
        if not canonical:
            continue
        aliases.setdefault(canonical, canonical)
        alias_block = (
            manifest.get("aliases")
            if isinstance(manifest.get("aliases"), dict)
            else {}
        )
        for alias in alias_block.get("provider_ids", []):
            normalized = str(alias or "").strip()
            if normalized:
                aliases.setdefault(normalized, canonical)
    return aliases


def canonical_provider_id(value: Any) -> str:
    provider_id = str(value or "").strip()
    if not provider_id:
        return ""
    aliases = provider_alias_map()
    return aliases.get(provider_id, aliases.get(provider_id.casefold(), provider_id))


def provider_id_aliases(provider_id: Any) -> list[str]:
    canonical = canonical_provider_id(provider_id)
    aliases = [
        alias
        for alias, target in provider_alias_map().items()
        if target == canonical
    ]
    if canonical and canonical not in aliases:
        aliases.append(canonical)
    return sorted(set(aliases))


def canonical_model_ref(value: Any) -> str:
    model_ref = str(value or "").strip()
    if "/" not in model_ref:
        return model_ref
    provider_id, remainder = model_ref.split("/", 1)
    canonical = canonical_provider_id(provider_id)
    return f"{canonical}/{remainder}" if canonical else model_ref
