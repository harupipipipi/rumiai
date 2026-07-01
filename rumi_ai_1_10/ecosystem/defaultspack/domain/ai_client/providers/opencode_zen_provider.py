from __future__ import annotations

import os
import ssl
from typing import Any, Dict, List

from .anthropic_provider import AnthropicProvider


_OPENCODE_ZEN_MODEL_SPECS: List[Dict[str, Any]] = [
    {
        "model_id": "minimax-m3-free",
        "display_name": "MiniMax M3 Free via OpenCode Zen",
        "priority": 1,
        "defaults": {"chat": True, "coding": True, "reasoning": True},
        "context_window": 200000,
        "max_tokens": 32000,
        "min_output_tokens": 96,
        "transport": "anthropic_messages",
        "endpoint_path": "/v1/messages",
        "source": "opencode_zen_minimax_m3_free",
    },
]


def _known_model_entry(spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": f"opencode-zen/{spec['model_id']}",
        "category": "llm_model",
        "version": "1",
        "provider": "opencode-zen",
        "provider_id": "opencode-zen",
        "model_id": spec["model_id"],
        "name": spec["display_name"],
        "display_name": spec["display_name"],
        "type": "chat",
        "enabled": True,
        "priority": spec["priority"],
        "defaults": dict(spec.get("defaults", {})),
        "capabilities": {
            "chat": True,
            "streaming": True,
            "tool_calls": True,
            "vision": True,
            "reasoning": True,
        },
        "context_window": spec["context_window"],
        "max_context_tokens": spec["context_window"],
        "max_tokens": spec["max_tokens"],
        "metadata": {
            "transport": spec["transport"],
            "endpoint_path": spec["endpoint_path"],
            "source": spec["source"],
            "pricing": "free_promotion_or_account_policy",
            "quirks": {
                "supports_stream_tool_calls": False,
            },
            "min_output_tokens": spec["min_output_tokens"],
            "token_floor_reason": "MiniMax M3 can emit reasoning before final text; short caps may return thinking-only output.",
        },
    }


class OpencodeZenProvider(AnthropicProvider):
    """OpenCode Zen Anthropic-compatible provider for curated Zen models."""

    provider_name = "opencode-zen"
    display_name = "OpenCode Zen"
    DEFAULT_BASE_URL = "https://opencode.ai/zen"
    MODEL_IDS = {"minimax-m3-free"}
    KNOWN_MODELS = [_known_model_entry(spec) for spec in _OPENCODE_ZEN_MODEL_SPECS]

    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENCODE_ZEN_API_KEY", "")
        self._ssl_ctx = ssl.create_default_context()
        self.BASE_URL = os.environ.get("OPENCODE_ZEN_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")

    @classmethod
    def _normalize_model_id(cls, model: str) -> str:
        model_id = str(model or "").strip()
        if model_id.startswith("opencode-zen/"):
            model_id = model_id.split("/", 1)[1]
        if model_id.startswith("opencode/"):
            model_id = model_id.split("/", 1)[1]
        return model_id

    @classmethod
    def _assert_supported_model(cls, model: str) -> str:
        model_id = cls._normalize_model_id(model)
        if model_id not in cls.MODEL_IDS:
            supported = ", ".join(sorted(cls.MODEL_IDS))
            raise RuntimeError(
                "opencode-zen: unsupported model. "
                f"defaultspack supports only: {supported}"
            )
        return model_id

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Bearer " + self._api_key,
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "RumiAI/1.0",
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [dict(model) for model in self.KNOWN_MODELS]

    @staticmethod
    def _params_with_token_floor(params: Dict[str, Any] | None) -> Dict[str, Any]:
        next_params = dict(params or {})
        try:
            requested = int(next_params.get("max_tokens", 4096) or 4096)
        except (TypeError, ValueError):
            requested = 4096
        next_params["max_tokens"] = max(requested, 96)
        return next_params

    def complete(self, model, messages, tools, params):
        model_id = self._assert_supported_model(model)
        return super().complete(model_id, messages, tools or [], self._params_with_token_floor(params))

    def stream(self, model, messages, tools, params):
        model_id = self._assert_supported_model(model)
        yield from super().stream(model_id, messages, tools or [], self._params_with_token_floor(params))
