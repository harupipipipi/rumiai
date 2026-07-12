from __future__ import annotations

import importlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


AUDIO_CAPABILITY = "audio"
MULTIMODAL_NO_AUDIO_CAPABILITY = "multimodal_no_audio"
TEXT_CAPABILITY = "text"
_BUILTIN_PROVIDER_DIR = Path(__file__).resolve().parents[1] / "ai_client" / "providers"


def create_transcription_client() -> Any:
    """Create the configured AI client behind the input-domain boundary."""

    from domain.ai_client.client import AIClient

    return AIClient()


def model_input_capability(model_ref: str) -> dict[str, Any]:
    """Return a conservative, privacy-safe input capability classification.

    Ambient dispatch must not rebuild the complete provider/extension catalog for
    every recorded utterance. Built-in model metadata is read directly from the
    relevant provider module (or a small ``models.json`` manifest when present),
    and the result is cached. Unknown models are deliberately treated as
    text-only so raw microphone bytes are never sent merely because a provider
    family happens to expose another audio-capable model.
    """

    return dict(_cached_model_input_capability(str(model_ref or "").strip()))


@lru_cache(maxsize=256)
def _cached_model_input_capability(model_ref: str) -> dict[str, Any]:
    if not model_ref:
        return _capability_result(
            model_ref,
            TEXT_CAPABILITY,
            False,
            False,
            configured=False,
        )

    provider_id, model_id = _model_identity(model_ref)
    metadata = _built_in_model_metadata(model_ref) or _static_provider_model_metadata(model_ref)
    if metadata is None:
        metadata = {
            "qualified_model_id": model_ref,
            "provider_id": provider_id,
            "model_id": model_id,
            "type": "chat",
        }

    from domain.ai_client.audio_capability import metadata_supports_audio_input
    from domain.ai_client.model_capability_inference import infer_model_capabilities

    inferred = infer_model_capabilities(metadata).to_dict()
    combined = {**metadata, **inferred}
    supports_audio = provider_id != "stub" and metadata_supports_audio_input(combined)
    supports_image = _metadata_supports_image_input(combined)

    if supports_audio:
        kind = AUDIO_CAPABILITY
    elif supports_image or _metadata_is_multimodal(combined):
        kind = MULTIMODAL_NO_AUDIO_CAPABILITY
    else:
        kind = TEXT_CAPABILITY

    return _capability_result(
        model_ref,
        kind,
        supports_audio,
        supports_image,
        configured=provider_id not in {"", "stub", "unknown"},
        provider_id=provider_id,
    )


@lru_cache(maxsize=256)
def _built_in_model_metadata(model_ref: str) -> dict[str, Any] | None:
    provider_id, model_id = _model_identity(model_ref)
    if not provider_id or not model_id:
        return None

    provider_aliases = [provider_id]
    if provider_id == "gemini":
        provider_aliases.append("google")
    aliases = {model_ref, model_id}
    aliases.update(f"{provider}/{model_id}" for provider in provider_aliases)

    for provider in provider_aliases:
        models_path = _BUILTIN_PROVIDER_DIR / provider / "models.json"
        try:
            payload = json.loads(models_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        models = payload.get("models") if isinstance(payload, dict) else payload
        if not isinstance(models, list):
            continue
        for item in models:
            if not isinstance(item, dict):
                continue
            item_aliases = _model_aliases(item)
            if aliases.intersection(item_aliases):
                return dict(item)
    return None


@lru_cache(maxsize=256)
def _static_provider_model_metadata(model_ref: str) -> dict[str, Any] | None:
    """Read a provider module's curated model metadata without catalog rebuilds."""

    provider_id, model_id = _model_identity(model_ref)
    canonical_provider = {"gemini": "google"}.get(provider_id, provider_id)
    module_id = canonical_provider.replace("-", "_")
    if not module_id or not module_id.replace("_", "").isalnum():
        return None
    try:
        module = importlib.import_module(
            f"domain.ai_client.providers.{module_id}_provider"
        )
    except (ImportError, ModuleNotFoundError):
        return None

    aliases = {
        model_ref,
        model_id,
        f"{provider_id}/{model_id}",
        f"{canonical_provider}/{model_id}",
    }
    for candidate in vars(module).values():
        if not isinstance(candidate, type):
            continue
        candidate_provider = str(
            getattr(candidate, "provider_name", "")
            or getattr(candidate, "provider_id", "")
            or ""
        ).strip()
        if candidate_provider and candidate_provider not in {
            provider_id,
            canonical_provider,
        }:
            continue
        models = (
            getattr(candidate, "KNOWN_MODELS", None)
            or getattr(candidate, "curated_models", None)
            or getattr(candidate, "CURATED_MODELS", None)
        )
        if not isinstance(models, list):
            continue
        for item in models:
            if not isinstance(item, dict):
                continue
            if aliases.intersection(_model_aliases(item)):
                return dict(item)
    return None


def _model_aliases(item: dict[str, Any]) -> set[str]:
    aliases = {
        str(item.get("id") or "").strip(),
        str(item.get("profile_id") or "").strip(),
        str(item.get("qualified_model_id") or "").strip(),
        str(item.get("model_id") or item.get("model") or "").strip(),
    }
    provider = str(item.get("provider_id") or item.get("provider") or "").strip()
    model_id = str(item.get("model_id") or item.get("model") or "").strip()
    if provider and model_id:
        aliases.add(f"{provider}/{model_id}")
    return {alias for alias in aliases if alias}


def _model_identity(model_ref: str) -> tuple[str, str]:
    if "/" not in model_ref:
        if model_ref == "stub/default":
            return "stub", "default"
        return "unknown", model_ref
    provider_id, model_id = model_ref.split("/", 1)
    return provider_id.strip(), model_id.strip()


def _capability_result(
    model_ref: str,
    kind: str,
    supports_audio: bool,
    supports_image: bool,
    *,
    configured: bool,
    provider_id: str = "",
) -> dict[str, Any]:
    return {
        "model_ref": model_ref,
        "kind": kind,
        "supports_audio_input": supports_audio,
        "supports_image_input": supports_image,
        "configured": configured,
        "provider_id": provider_id,
    }


def _metadata_supports_image_input(value: dict[str, Any]) -> bool:
    if any(
        bool(value.get(key))
        for key in (
            "supports_vision",
            "supports_image",
            "supports_image_input",
            "image_input",
            "vision",
        )
    ):
        return True
    for container_key in (
        "capabilities",
        "features",
        "capability_tags",
        "tags",
        "input_modalities",
        "modalities",
    ):
        if _tokens_include(
            value.get(container_key),
            {"vision", "image", "image_input"},
        ):
            return True
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return bool(metadata) and _metadata_supports_image_input(metadata)


def _metadata_is_multimodal(value: dict[str, Any]) -> bool:
    for container_key in (
        "capability_tags",
        "tags",
        "capabilities",
        "features",
    ):
        if _tokens_include(
            value.get(container_key),
            {"multimodal", "multi_modal"},
        ):
            return True
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return bool(metadata) and _metadata_is_multimodal(metadata)


def _tokens_include(value: Any, expected: set[str]) -> bool:
    if isinstance(value, str):
        return _normalize_token(value) in expected
    if isinstance(value, dict):
        return any(
            (_normalize_token(key) in expected and bool(item))
            or _tokens_include(item, expected)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_tokens_include(item, expected) for item in value)
    return False


def _normalize_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
