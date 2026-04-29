from __future__ import annotations

import os
from typing import Any, Dict, List

from .openai_compatible_provider import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider limited to the Rumi-approved free Hy3 preview model."""

    MODEL_ID = "tencent/hy3-preview:free"
    KNOWN_MODELS = [
        {
            "id": f"openrouter/{MODEL_ID}",
            "model_id": MODEL_ID,
            "name": "Tencent Hy3 preview (free)",
            "display_name": "Tencent Hy3 preview (free)",
            "provider": "openrouter",
            "provider_id": "openrouter",
            "type": "chat",
            "defaults": {"chat": True, "fast": True},
            "metadata": {
                "source": "openrouter",
                "restriction": "only supported OpenRouter model in defaultspack",
            },
        }
    ]

    def __init__(self) -> None:
        super().__init__(
            provider_id="openrouter",
            display_name="OpenRouter",
            api_key_env="OPENROUTER_API_KEY",
            base_url_env="OPENROUTER_BASE_URL",
            default_base_url="https://openrouter.ai/api/v1",
            credential_required=True,
            known_models=self.KNOWN_MODELS,
            extra_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "https://github.com/harupipipipi/rumiai"),
                "X-Title": os.environ.get(
                    "OPENROUTER_X_TITLE",
                    os.environ.get("OPENROUTER_X_OPENROUTER_TITLE", "rumiai-defaultspack"),
                ),
            },
        )

    @classmethod
    def _assert_supported_model(cls, model: str) -> None:
        if str(model or "").strip() != cls.MODEL_ID:
            raise RuntimeError(
                "openrouter: unsupported model. "
                f"defaultspack supports only {cls.MODEL_ID}"
            )

    def list_models(self) -> List[Dict[str, Any]]:
        return [dict(model) for model in self.KNOWN_MODELS]

    def complete(self, model, messages, tools, params):
        self._assert_supported_model(model)
        return super().complete(model, messages, tools, params)

    def stream(self, model, messages, tools, params):
        self._assert_supported_model(model)
        return super().stream(model, messages, tools, params)
