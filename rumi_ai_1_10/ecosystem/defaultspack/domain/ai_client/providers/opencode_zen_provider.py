from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider


_OPENCODE_ZEN_MODEL_SPECS: List[Dict[str, Any]] = [
    {
        "model_id": "mimo-v2.5-free",
        "display_name": "MiMo V2.5 Free via OpenCode Zen",
        "priority": 0,
        "defaults": {"chat": True, "coding": True, "reasoning": True, "agent": True},
        "context_window": 200000,
        "max_tokens": 32000,
        "min_output_tokens": 512,
        "transport": "openai_chat_completions",
        "endpoint_path": "/v1/chat/completions",
        "source": "opencode_zen_docs",
        "tool_calls": True,
        "reasoning": True,
        "reasoning_effort": True,
        "vision": True,
        "pricing": "free_limited_time",
        "privacy": "free_period_prompts_and_responses_may_be_used_for_feedback_and_improvement",
        "token_floor_reason": "MiMo V2.5 Free may emit reasoning before final text; short caps can return thinking-only or empty length-capped output.",
    },
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
        "token_floor_reason": "MiniMax M3 can emit reasoning before final text; short caps may return thinking-only output.",
    },
]


def _known_model_entry(spec: Dict[str, Any]) -> Dict[str, Any]:
    tool_calls = bool(spec.get("tool_calls", False))
    reasoning = bool(spec.get("reasoning", True))
    vision = bool(spec.get("vision", True))
    metadata = {
        "transport": spec["transport"],
        "endpoint_path": spec["endpoint_path"],
        "source": spec["source"],
        "pricing": spec.get("pricing", "free_promotion_or_account_policy"),
    }
    if spec.get("privacy"):
        metadata["privacy"] = spec["privacy"]
    if spec.get("reasoning_effort"):
        metadata["reasoning_effort_verified"] = True
    if spec.get("min_output_tokens"):
        metadata["min_output_tokens"] = spec["min_output_tokens"]
        metadata["token_floor_reason"] = spec.get("token_floor_reason", "")
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
            "tool_calls": tool_calls,
            "vision": vision,
            "reasoning": reasoning,
        },
        "supports_thinking": reasoning,
        "thinking_levels": ["low", "medium", "high"] if reasoning else [],
        "default_thinking_level": "medium" if reasoning else None,
        "context_window": spec["context_window"],
        "max_context_tokens": spec["context_window"],
        "max_tokens": spec["max_tokens"],
        "metadata": metadata,
    }


class OpencodeZenProvider(AnthropicProvider):
    """OpenCode Zen provider for curated Zen free models."""

    provider_name = "opencode-zen"
    display_name = "OpenCode Zen"
    DEFAULT_BASE_URL = "https://opencode.ai/zen"
    OPENAI_CHAT_MODELS = {"mimo-v2.5-free"}
    ANTHROPIC_MESSAGES_MODELS = {"minimax-m3-free"}
    MODEL_IDS = OPENAI_CHAT_MODELS | ANTHROPIC_MESSAGES_MODELS
    TOOL_CALL_MODELS = {"mimo-v2.5-free"}
    REASONING_EFFORT_MODELS = {"mimo-v2.5-free"}
    MIN_OUTPUT_TOKEN_FLOORS = {"minimax-m3-free": 96, "mimo-v2.5-free": 512}
    KNOWN_MODELS = [_known_model_entry(spec) for spec in _OPENCODE_ZEN_MODEL_SPECS]
    _OPENAI_CHAT_PARAM_KEYS = {
        "temperature",
        "max_tokens",
        "max_completion_tokens",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "response_format",
        "reasoning_effort",
        "tool_choice",
        "parallel_tool_calls",
        "stream_options",
    }

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

    def _chat_headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Bearer " + self._api_key,
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "RumiAI/1.0",
        }

    def _redact_secret(self, text: str) -> str:
        if self._api_key:
            return text.replace(self._api_key, "[redacted]")
        return text

    def _request_chat_json(self, path, body, *, timeout=120.0):
        url = self.BASE_URL + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._chat_headers(), method="POST")
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout) as resp:
                raw_bytes = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("OpenCode Zen API error {}: {}".format(exc.code, self._redact_secret(err_body)))
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenCode Zen API connection error: {}".format(exc.reason))
        try:
            return json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError("OpenCode Zen API returned invalid JSON: {}".format(raw_bytes[:500]))

    def _request_chat_stream(self, path, body, *, timeout=120.0):
        body["stream"] = True
        url = self.BASE_URL + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._chat_headers(), method="POST")
        try:
            return urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("OpenCode Zen API error {}: {}".format(exc.code, self._redact_secret(err_body)))
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenCode Zen API connection error: {}".format(exc.reason))

    def list_models(self) -> List[Dict[str, Any]]:
        return [dict(model) for model in self.KNOWN_MODELS]

    @staticmethod
    def _params_with_token_floor(params: Dict[str, Any] | None, min_output_tokens: int = 96) -> Dict[str, Any]:
        next_params = dict(params or {})
        token_key = "max_completion_tokens" if "max_completion_tokens" in next_params else "max_tokens"
        try:
            requested = int(next_params.get(token_key, 4096) or 4096)
        except (TypeError, ValueError):
            requested = 4096
        next_params[token_key] = max(requested, int(min_output_tokens))
        return next_params

    @classmethod
    def _token_floor_for_model(cls, model_id: str) -> int:
        return int(cls.MIN_OUTPUT_TOKEN_FLOORS.get(model_id, 0) or 0)

    @staticmethod
    def _request_timeout_kwargs(params: Dict[str, Any] | None) -> Dict[str, Any]:
        raw = dict(params or {})
        if "request_timeout" not in raw and "timeout" not in raw:
            return {}
        return {"timeout": OpenAIProvider._request_timeout(raw)}

    @classmethod
    def _openai_chat_params(cls, params: Dict[str, Any] | None, *, supports_tools: bool, supports_reasoning: bool):
        translated = OpenAIProvider._translate_params(dict(params or {}))
        filtered = {
            key: translated[key]
            for key in cls._OPENAI_CHAT_PARAM_KEYS
            if key in translated
        }
        for key in ("request_timeout", "timeout"):
            if key in translated:
                filtered[key] = translated[key]
        if not supports_tools:
            filtered.pop("tool_choice", None)
            filtered.pop("parallel_tool_calls", None)
        if not supports_reasoning:
            filtered.pop("reasoning_effort", None)
        return filtered

    @classmethod
    def _copy_chat_params(cls, body, params):
        for key in cls._OPENAI_CHAT_PARAM_KEYS:
            if key in params:
                body[key] = params[key]

    @staticmethod
    def _message_reasoning_content(msg):
        return OpenAIProvider._message_reasoning_content(msg)

    def _complete_openai_chat(self, model_id, messages, tools, params):
        body = {"model": model_id, "messages": OpenAIProvider.build_request(self, messages)}
        if tools:
            body["tools"] = tools
        self._copy_chat_params(body, params)
        raw = self._request_chat_json(
            "/v1/chat/completions",
            body,
            **self._request_timeout_kwargs(params),
        )
        return OpenAIProvider.parse_response(self, raw)

    def _stream_openai_chat(self, model_id, messages, tools, params):
        body = {"model": model_id, "messages": OpenAIProvider.build_request(self, messages)}
        if tools:
            body["tools"] = tools
        self._copy_chat_params(body, params)
        body.setdefault("stream_options", {"include_usage": True})
        resp = self._request_chat_stream(
            "/v1/chat/completions",
            body,
            **self._request_timeout_kwargs(params),
        )
        tool_call_state = {}
        try:
            for payload in OpenAIProvider._parse_sse_lines(resp):
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices", [])
                if choices:
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
                                yield {
                                    "type": "tool_call_end",
                                    "id": current.get("id", ""),
                                    "name": current.get("name", ""),
                                }
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
        if model_id in self.ANTHROPIC_MESSAGES_MODELS:
            return super().complete(
                model_id,
                messages,
                [],
                self._params_with_token_floor(params, self._token_floor_for_model(model_id)),
            )
        supports_tools = model_id in self.TOOL_CALL_MODELS
        supports_reasoning = model_id in self.REASONING_EFFORT_MODELS
        forward_tools = tools if supports_tools else []
        forward_params = self._openai_chat_params(
            params,
            supports_tools=supports_tools,
            supports_reasoning=supports_reasoning,
        )
        forward_params = self._params_with_token_floor(
            forward_params,
            self._token_floor_for_model(model_id),
        )
        return self._complete_openai_chat(model_id, messages, forward_tools, forward_params)

    def stream(self, model, messages, tools, params):
        model_id = self._assert_supported_model(model)
        if model_id in self.ANTHROPIC_MESSAGES_MODELS:
            yield from super().stream(
                model_id,
                messages,
                [],
                self._params_with_token_floor(params, self._token_floor_for_model(model_id)),
            )
            return
        supports_tools = model_id in self.TOOL_CALL_MODELS
        supports_reasoning = model_id in self.REASONING_EFFORT_MODELS
        forward_tools = tools if supports_tools else []
        forward_params = self._openai_chat_params(
            params,
            supports_tools=supports_tools,
            supports_reasoning=supports_reasoning,
        )
        forward_params = self._params_with_token_floor(
            forward_params,
            self._token_floor_for_model(model_id),
        )
        yield from self._stream_openai_chat(model_id, messages, forward_tools, forward_params)
