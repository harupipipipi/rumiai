from __future__ import annotations

import json
import os
import ssl
from typing import Any, Dict, List

from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider


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
    {
        "model_id": "mimo-v2.5-free",
        "display_name": "MiMo V2.5 Free via OpenCode Zen",
        "priority": 2,
        "defaults": {"chat": True},
        "context_window": 0,
        "max_tokens": 0,
        "min_output_tokens": 0,
        "transport": "openai_chat_completions",
        "endpoint_path": "/v1/chat/completions",
        "source": "opencode_zen_mimo_v2_5_free",
        "free_tier": True,
        "tool_calls": True,
        "reasoning": True,
    },
]


def _known_model_entry(spec: Dict[str, Any]) -> Dict[str, Any]:
    transport = spec["transport"]
    is_anthropic = transport == "anthropic_messages"
    tool_calls = bool(spec.get("tool_calls", False))
    reasoning = bool(spec.get("reasoning", is_anthropic))
    capabilities = {
        "chat": True,
        "streaming": True,
        "tool_calls": tool_calls,
        "vision": bool(spec.get("vision", is_anthropic)),
        "reasoning": reasoning,
    }
    metadata = {
        "transport": transport,
        "endpoint_path": spec["endpoint_path"],
        "source": spec["source"],
    }
    if spec.get("free_tier"):
        metadata["free_tier"] = True
    if tool_calls:
        metadata["tool_calls_verified"] = True
    if reasoning and transport == "openai_chat_completions":
        metadata["reasoning_effort_verified"] = True
    if spec.get("min_output_tokens"):
        metadata.update(
            {
                "pricing": "free_promotion_or_account_policy",
                "min_output_tokens": spec["min_output_tokens"],
                "token_floor_reason": "MiniMax M3 can emit reasoning before final text; short caps may return thinking-only output.",
            }
        )

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
        "capabilities": capabilities,
        "context_window": spec.get("context_window", 0),
        "max_context_tokens": spec.get("context_window", 0),
        "max_tokens": spec.get("max_tokens", 0),
        "supports_thinking": reasoning,
        "thinking_levels": ["low", "medium", "high"] if reasoning else [],
        "default_thinking_level": "medium" if reasoning else None,
        "metadata": metadata,
    }


class OpencodeZenProvider(AnthropicProvider):
    """OpenCode Zen Anthropic-compatible provider for curated Zen models."""

    provider_name = "opencode-zen"
    display_name = "OpenCode Zen"
    DEFAULT_BASE_URL = "https://opencode.ai/zen"
    OPENAI_CHAT_MODELS = {"mimo-v2.5-free"}
    ANTHROPIC_MESSAGES_MODELS = {"minimax-m3-free"}
    MODEL_IDS = OPENAI_CHAT_MODELS | ANTHROPIC_MESSAGES_MODELS
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

    @staticmethod
    def _openai_params(params: Dict[str, Any] | None) -> Dict[str, Any]:
        raw = OpenAIProvider._translate_params(dict(params or {}))
        return {
            key: raw[key]
            for key in (
                "temperature",
                "max_tokens",
                "max_completion_tokens",
                "top_p",
                "stop",
                "response_format",
                "reasoning_effort",
                "tool_choice",
                "parallel_tool_calls",
                "stream_options",
            )
            if key in raw
        }

    @staticmethod
    def _copy_openai_chat_params(body: Dict[str, Any], params: Dict[str, Any]) -> None:
        OpenAIProvider._copy_chat_params(body, params)

    def _complete_openai_chat(self, model_id, messages, tools, params):
        params = self._openai_params(params)
        body = {"model": model_id, "messages": OpenAIProvider.build_request(self, messages)}
        if tools:
            body["tools"] = tools
        self._copy_openai_chat_params(body, params)
        raw = self._request_json("/v1/chat/completions", body)
        return OpenAIProvider.parse_response(self, raw)

    def _stream_openai_chat(self, model_id, messages, tools, params):
        params = self._openai_params(params)
        body = {"model": model_id, "messages": OpenAIProvider.build_request(self, messages)}
        if tools:
            body["tools"] = tools
        self._copy_openai_chat_params(body, params)
        body.setdefault("stream_options", {"include_usage": True})
        resp = self._request_stream("/v1/chat/completions", body)
        tool_call_state = {}
        try:
            for payload in OpenAIProvider._parse_sse_lines(resp):
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield {"type": "content_delta", "delta": {"type": "text", "text": text}}
                reasoning_text = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking")
                if reasoning_text:
                    yield {"type": "reasoning_delta", "delta": {"type": "text", "text": str(reasoning_text)}}
                yield from OpenAIProvider._stream_tool_call_events(delta, tool_call_state)
                finish = choices[0].get("finish_reason")
                if finish:
                    for current in tool_call_state.values():
                        if current.get("started") and not current.get("ended"):
                            current["ended"] = True
                            yield {"type": "tool_call_end", "id": current.get("id", ""), "name": current.get("name", "")}
                    usage_raw = obj.get("usage") or {}
                    yield {
                        "type": "stream_end",
                        "finish_reason": finish,
                        "usage": {
                            "input_tokens": usage_raw.get("prompt_tokens", 0),
                            "output_tokens": usage_raw.get("completion_tokens", 0),
                            "total_tokens": usage_raw.get("total_tokens", 0),
                        },
                    }
        finally:
            resp.close()

    def complete(self, model, messages, tools, params):
        model_id = self._assert_supported_model(model)
        if model_id in self.OPENAI_CHAT_MODELS:
            return self._complete_openai_chat(model_id, messages, tools, params)
        del tools
        return super().complete(model_id, messages, [], self._params_with_token_floor(params))

    def stream(self, model, messages, tools, params):
        model_id = self._assert_supported_model(model)
        if model_id in self.OPENAI_CHAT_MODELS:
            yield from self._stream_openai_chat(model_id, messages, tools, params)
            return
        del tools
        yield from super().stream(model_id, messages, [], self._params_with_token_floor(params))
