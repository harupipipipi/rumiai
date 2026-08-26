from __future__ import annotations

import json
from typing import Any, Dict, List

from .openai_compatible_provider import OpenAICompatibleProvider


_OPENCODE_ZEN_MODEL_SPECS: List[Dict[str, Any]] = [
    {
        "model_id": "mimo-v2.5-free",
        "display_name": "MiMo V2.5 Free via OpenCode Zen",
        "priority": 1,
        "default_for": ["chat", "coding", "reasoning"],
        "context_window": 131072,
        "max_tokens": 32768,
        "transport": "openai_chat_completions",
        "endpoint_path": "/v1/chat/completions",
        "source": "opencode_zen_mimo_v2_5_free",
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
        "routing": {"default_for": list(spec.get("default_for", []))},
        "capabilities": {
            "text_input": True,
            "text_output": True,
            "streaming": True,
            "thinking": True,
            "tool_calling": False,
            "parallel_tool_calls": False,
            "json_schema": False,
            "structured_output": False,
            "image_input": False,
            "audio_input": False,
        },
        "context_window": spec["context_window"],
        "thinking": {
            "supported": True,
            "levels": ["low", "medium", "high"],
            "default_level": "medium",
            "provider_mapping": {
                "low": {"reasoning_effort": "low"},
                "medium": {"reasoning_effort": "medium"},
                "high": {"reasoning_effort": "high"},
                "none": {},
            },
        },
        "metadata": {
            "transport": spec["transport"],
            "api_compatibility": spec["transport"],
            "endpoint_path": spec["endpoint_path"],
            "source": spec["source"],
            "pricing": "free_promotion_or_account_policy",
            "max_output_tokens": spec["max_tokens"],
            "capabilities": {
                "tool_calling": False,
                "thinking": True,
                "reasoning": True,
                "vision": False,
            },
        },
    }


class OpencodeZenProvider(OpenAICompatibleProvider):
    """OpenCode Zen free OpenAI-compatible provider."""

    provider_name = "opencode-zen"
    display_name = "OpenCode Zen"
    DEFAULT_BASE_URL = "https://opencode.ai/zen"
    BASE_URL = DEFAULT_BASE_URL
    MODEL_IDS = {"mimo-v2.5-free"}
    KNOWN_MODELS = [_known_model_entry(spec) for spec in _OPENCODE_ZEN_MODEL_SPECS]
    _CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
    _CHAT_PARAM_KEYS = {
        "temperature",
        "max_tokens",
        "max_completion_tokens",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "response_format",
        "reasoning_effort",
        "stream_options",
    }

    def __init__(self) -> None:
        super().__init__(
            provider_id="opencode-zen",
            display_name="OpenCode Zen",
            api_key_env="OPENCODE_ZEN_API_KEY",
            base_url_env="OPENCODE_ZEN_BASE_URL",
            default_base_url=self.DEFAULT_BASE_URL,
            credential_required=True,
            known_models=self.KNOWN_MODELS,
        )

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

    @staticmethod
    def _translate_params(params):
        raw = dict(params or {})
        translated = {
            key: raw[key]
            for key in OpencodeZenProvider._CHAT_PARAM_KEYS
            if key in raw
        }
        for key in ("request_timeout", "timeout"):
            if key in raw:
                translated[key] = raw[key]
        return translated

    @staticmethod
    def _copy_chat_params(body, params):
        for key in OpencodeZenProvider._CHAT_PARAM_KEYS:
            if key in params:
                body[key] = params[key]

    @staticmethod
    def _message_text(message: Dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if content in (None, ""):
            return ""
        if isinstance(content, list):
            chunks: List[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        chunks.append(str(part.get("text", "")))
                    elif isinstance(part.get("content"), str):
                        chunks.append(part["content"])
                elif part is not None:
                    chunks.append(str(part))
            return "".join(chunks)
        return str(content)

    def parse_response(self, raw):
        choices = raw.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = choice.get("message", {}) if isinstance(choice.get("message"), dict) else {}
        normalized = dict(raw)
        normalized["choices"] = [
            {
                **choice,
                "message": {
                    **message,
                    "content": self._message_text(message),
                },
            }
        ]
        return super().parse_response(normalized)

    def complete(self, model, messages, tools, params):
        del tools
        model_id = self._assert_supported_model(model)
        params = self._translate_params(params)
        body = {"model": model_id, "messages": self.build_request(messages)}
        self._copy_chat_params(body, params)
        raw = self._request_json(self._CHAT_COMPLETIONS_PATH, body, **self._request_timeout_kwargs(params))
        return self.parse_response(raw)

    def stream(self, model, messages, tools, params):
        del tools
        model_id = self._assert_supported_model(model)
        params = self._translate_params(params)
        body = {"model": model_id, "messages": self.build_request(messages)}
        self._copy_chat_params(body, params)
        body.setdefault("stream_options", {"include_usage": True})
        resp = self._request_stream(self._CHAT_COMPLETIONS_PATH, body, **self._request_timeout_kwargs(params))
        yield from self._stream_from_response(resp)

    @staticmethod
    def _parse_sse_lines(resp):
        """Yield Zen SSE payloads as soon as each event line arrives."""
        while True:
            raw_line = resp.readline()
            if not raw_line:
                return
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].lstrip()
            if payload == "[DONE]":
                return
            if payload:
                yield payload

    def _stream_from_response(self, resp):
        tool_call_state = {}
        finish_reason = ""
        saw_content = False
        reasoning_parts: List[str] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        try:
            for payload in self._parse_sse_lines(resp):
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                usage_raw = obj.get("usage") or {}
                if usage_raw:
                    usage = {
                        "input_tokens": usage_raw.get("prompt_tokens", usage["input_tokens"]),
                        "output_tokens": usage_raw.get("completion_tokens", usage["output_tokens"]),
                        "total_tokens": usage_raw.get("total_tokens", usage["total_tokens"]),
                    }
                choices = obj.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content")
                if text:
                    saw_content = True
                    yield {"type": "content_delta", "delta": {"type": "text", "text": text}}
                reasoning_text = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking")
                if reasoning_text:
                    normalized_reasoning = str(reasoning_text)
                    reasoning_parts.append(normalized_reasoning)
                    yield {
                        "type": "reasoning_delta",
                        "delta": {"type": "text", "text": normalized_reasoning},
                    }
                yield from self._stream_tool_call_events(delta, tool_call_state)
                finish = choices[0].get("finish_reason")
                if finish:
                    finish_reason = str(finish)

            for current in tool_call_state.values():
                if current.get("started") and not current.get("ended"):
                    current["ended"] = True
                    yield {
                        "type": "tool_call_end",
                        "id": current.get("id", ""),
                        "name": current.get("name", ""),
                    }
            if not saw_content and reasoning_parts:
                yield {
                    "type": "content_delta",
                    "delta": {"type": "text", "text": "".join(reasoning_parts)},
                }
            yield {
                "type": "stream_end",
                "finish_reason": finish_reason or "stop",
                "usage": usage,
            }
        finally:
            resp.close()
