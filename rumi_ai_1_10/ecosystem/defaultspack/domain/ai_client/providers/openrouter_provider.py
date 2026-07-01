from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from ..metadata_json import MetadataJsonError, load_strict_metadata_json
from ..model_metadata_schema import ModelMetadataSchemaError, validate_model_catalog_source
from .openai_compatible_provider import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider backed by the bundled curated model allowlist."""

    MODEL_ID = "tencent/hy3-preview:free"
    OPENROUTER_PARAM_KEYS = {
        "temperature",
        "top_p",
        "max_tokens",
        "max_completion_tokens",
        "stop",
        "response_format",
        "structured_outputs",
        "tool_choice",
        "parallel_tool_calls",
        "reasoning",
        "reasoning_effort",
        "include_reasoning",
        "provider",
        "models",
        "web_search_options",
    }
    LEGACY_MODEL = {
        "id": f"openrouter/{MODEL_ID}",
        "model_id": MODEL_ID,
        "name": "Tencent Hy3 preview (free)",
        "display_name": "Tencent Hy3 preview (free)",
        "provider": "openrouter",
        "provider_id": "openrouter",
        "type": "chat",
        "defaults": {"legacy": True},
        "metadata": {
            "source": "legacy_openrouter_allowlist",
            "legacy_default": True,
        },
    }
    KNOWN_MODELS: List[Dict[str, Any]] = [
        {
            "id": "openrouter/cohere/north-mini-code:free",
            "model_id": "cohere/north-mini-code:free",
            "name": "Cohere North Mini Code (free)",
            "display_name": "Cohere North Mini Code (free)",
            "provider": "openrouter",
            "provider_id": "openrouter",
            "type": "chat",
            "defaults": {"chat": True, "fast": True},
            "metadata": {
                "source": "openrouter_curated_fallback",
                "free": True,
            },
        }
    ]

    def __init__(self, known_models: List[Dict[str, Any]] | None = None) -> None:
        models = self._catalog_models() if known_models is None else known_models
        if not models:
            models = self.KNOWN_MODELS
        super().__init__(
            provider_id="openrouter",
            display_name="OpenRouter",
            api_key_env="OPENROUTER_API_KEY",
            base_url_env="OPENROUTER_BASE_URL",
            default_base_url="https://openrouter.ai/api/v1",
            credential_required=True,
            known_models=models,
            extra_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "https://github.com/harupipipipi/rumiai"),
                "X-Title": os.environ.get(
                    "OPENROUTER_X_TITLE",
                    os.environ.get("OPENROUTER_X_OPENROUTER_TITLE", "rumiai-defaultspack"),
                ),
            },
        )

    @classmethod
    def _catalog_models(cls) -> List[Dict[str, Any]]:
        path = Path(__file__).resolve().parents[2] / "providers" / "openrouter" / "models.json"
        try:
            payload = load_strict_metadata_json(path)
            validate_model_catalog_source(payload, path=path)
        except (MetadataJsonError, ModelMetadataSchemaError):
            return [dict(model) for model in cls.KNOWN_MODELS]
        raw_models = payload.get("models") if isinstance(payload, dict) else []
        if not isinstance(raw_models, list):
            return [dict(model) for model in cls.KNOWN_MODELS]
        models = [dict(model) for model in raw_models if isinstance(model, dict)]
        model_ids = {str(model.get("model_id") or "").strip() for model in models}
        if cls.MODEL_ID not in model_ids:
            models.append(dict(cls.LEGACY_MODEL))
        return models

    @classmethod
    def _assert_supported_model(cls, model: str) -> None:
        model_ref = str(model or "").strip()
        provider_model_id = cls._provider_model_id(model_ref)
        catalog_models = cls._catalog_models()
        supported = {
            str(item.get("model_id") or "").strip()
            for item in catalog_models
            if str(item.get("model_id") or "").strip()
        }
        supported.update(
            str(item.get("id") or "").strip()
            for item in catalog_models
            if str(item.get("id") or "").strip()
        )
        if model_ref not in supported and provider_model_id not in supported:
            raise RuntimeError(
                "openrouter: unsupported model. "
                f"defaultspack supports: {', '.join(sorted(supported))}"
            )

    @classmethod
    def _provider_model_id(cls, model: str) -> str:
        model_ref = str(model or "").strip()
        prefix = "openrouter/"
        if model_ref.startswith(prefix):
            return model_ref[len(prefix):]
        return model_ref

    @staticmethod
    def _copy_chat_params(body: Dict[str, Any], params: Dict[str, Any]) -> None:
        raw = dict(params or {})
        extra_body = raw.pop("extra_body", None)
        OpenAICompatibleProvider._copy_chat_params(body, raw)
        for key in OpenRouterProvider.OPENROUTER_PARAM_KEYS:
            if key in raw:
                body[key] = raw[key]
        if isinstance(extra_body, dict):
            body.update(extra_body)

    def list_models(self) -> List[Dict[str, Any]]:
        return [dict(model) for model in self.KNOWN_MODELS]

    def complete(self, model, messages, tools, params):
        self._assert_supported_model(model)
        return super().complete(self._provider_model_id(model), messages, tools, params)

    def stream(self, model, messages, tools, params):
        self._assert_supported_model(model)
        return super().stream(self._provider_model_id(model), messages, tools, params)
