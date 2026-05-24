from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from domain.ai_client.capabilities.quirks import merged_quirks
from domain.ai_client.capabilities.schema import ProviderCapabilities, merge_capabilities


_MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"


class ProviderCapabilityRegistry:
    def __init__(self, manifest_dir: Path | None = None) -> None:
        self.manifest_dir = manifest_dir or _MANIFEST_DIR
        self._manifests = self._load_manifests()

    def _load_manifests(self) -> dict[str, dict[str, Any]]:
        manifests: dict[str, dict[str, Any]] = {}
        if not self.manifest_dir.exists():
            return manifests
        for path in sorted(self.manifest_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            provider_id = str(raw.get("provider_id") or raw.get("id") or path.stem).strip()
            if provider_id:
                manifests[provider_id] = raw
        return manifests

    def provider_ids(self) -> list[str]:
        return sorted(self._manifests)

    def get(self, provider_id: str, model_metadata: dict[str, Any] | None = None) -> ProviderCapabilities:
        provider_key = str(provider_id or "unknown").split("/", 1)[0] or "unknown"
        raw = dict(self._manifests.get(provider_key) or self._manifests.get("openai_compatible") or {})
        if not raw:
            raw = {"provider_id": provider_key, "api_family": "unknown"}
        raw.setdefault("provider_id", provider_key)
        caps = ProviderCapabilities.from_dict(raw)
        model_quirks = {}
        if isinstance(model_metadata, dict):
            metadata = model_metadata.get("metadata") if isinstance(model_metadata.get("metadata"), dict) else {}
            model_quirks = metadata.get("quirks") if isinstance(metadata.get("quirks"), dict) else {}
        caps.quirks = merged_quirks(caps.quirks, model_quirks)
        return merge_capabilities(caps, model_metadata)

    def for_model(self, model: str, model_metadata: dict[str, Any] | None = None) -> ProviderCapabilities:
        provider_id = str(model or "").split("/", 1)[0] if "/" in str(model or "") else "unknown"
        if isinstance(model_metadata, dict):
            provider_id = str(model_metadata.get("provider_id") or model_metadata.get("provider") or provider_id)
        caps = self.get(provider_id, model_metadata)
        model_id = str(model or "").split("/", 1)[1] if "/" in str(model or "") else str(model or "")
        if caps.provider_id == "google" and model_id.startswith("gemma-4"):
            caps.api_family = "google_native"
        return caps


@lru_cache(maxsize=1)
def default_registry() -> ProviderCapabilityRegistry:
    return ProviderCapabilityRegistry()


def get_provider_capabilities(provider_id: str, model_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return default_registry().get(provider_id, model_metadata).to_dict()


def get_model_provider_capabilities(model: str, model_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return default_registry().for_model(model, model_metadata).to_dict()
