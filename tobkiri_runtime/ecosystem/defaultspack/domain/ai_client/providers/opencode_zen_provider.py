from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

from ..api_key_store import read_provider_api_key
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
        "defaults": {"chat": True, "cheap": True},
        "transport": "openai_chat_completions",
        "endpoint_path": "/v1/chat/completions",
        "source": "opencode_zen_mimo_v2_5_free",
        "free_tier": True,
    },
]


def _known_model_entry(spec: Dict[str, Any]) -> Dict[str, Any]:
    reasoning = bool(spec.get("reasoning", spec["transport"] == "anthropic_messages"))
    vision = bool(spec.get("vision", spec["transport"] == "anthropic_messages"))
    metadata = {
        "transport": spec["transport"],
        "endpoint_path": spec["endpoint_path"],
        "source": spec["source"],
        "pricing": "free_promotion_or_account_policy",
    }
    if "min_output_tokens" in spec:
        metadata["min_output_tokens"] = spec["min_output_tokens"]
        metadata["token_floor_reason"] = (
            "MiniMax M3 can emit reasoning before final text; "
            "short caps may return thinking-only output."
        )
    if "free_tier" in spec:
        metadata["free_tier"] = bool(spec["free_tier"])
    entry = {
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
            "tool_calls": False,
            "vision": vision,
            "reasoning": reasoning,
        },
        "metadata": metadata,
    }
    if "context_window" in spec:
        entry["context_window"] = spec["context_window"]
        entry["max_context_tokens"] = spec["context_window"]
    if "max_tokens" in spec:
        entry["max_tokens"] = spec["max_tokens"]
    if reasoning:
        entry["supports_thinking"] = True
        entry["thinking_levels"] = ["low", "medium", "high", "xhigh"]
        entry["default_thinking_level"] = "medium"
    return entry


class OpencodeZenProvider(AnthropicProvider):
    """OpenCode Zen provider for curated Anthropic and OpenAI-compatible models."""

    provider_name = "opencode-zen"
    display_name = "OpenCode Zen"
    DEFAULT_BASE_URL = "https://opencode.ai/zen"
    MODEL_INVENTORY_TTL_SECONDS = 300
    ANTHROPIC_MESSAGES_MODELS = {"minimax-m3-free"}
    OPENAI_CHAT_MODELS = {"mimo-v2.5-free"}
    MODEL_IDS = ANTHROPIC_MESSAGES_MODELS | OPENAI_CHAT_MODELS
    CURATED_MODELS = [_known_model_entry(spec) for spec in _OPENCODE_ZEN_MODEL_SPECS]
    KNOWN_MODELS: List[Dict[str, Any]] = []
    _OPENAI_CHAT_PARAM_KEYS = {
        "temperature",
        "top_p",
        "max_tokens",
        "max_completion_tokens",
        "stop",
        "stream_options",
    }
    _message_reasoning_content = staticmethod(OpenAIProvider._message_reasoning_content)

    def __init__(self) -> None:
        self._api_key = str(
            read_provider_api_key("opencode-zen", "default") or ""
        )
        self._ssl_ctx = ssl.create_default_context()
        self.BASE_URL = os.environ.get("OPENCODE_ZEN_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")
        self._model_inventory_cache: List[Dict[str, Any]] = []
        self._model_inventory_expires_at = 0.0

    @classmethod
    def _normalize_model_id(cls, model: str) -> str:
        model_id = str(model or "").strip()
        if model_id.startswith("opencode-zen/"):
            model_id = model_id.split("/", 1)[1]
        if model_id.startswith("opencode/"):
            model_id = model_id.split("/", 1)[1]
        return model_id

    def _assert_supported_model(self, model: str) -> str:
        model_id = self._normalize_model_id(model)
        discovered = {
            str(item.get("model_id") or "").strip()
            for item in self._model_inventory_cache
            if isinstance(item, dict)
        }
        if model_id not in self.MODEL_IDS | discovered:
            raise RuntimeError(f"unsupported model: {model_id}")
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

    def _openai_headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Bearer " + self._api_key,
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "RumiAI/1.0",
        }

    def _request_openai_json(self, path, body, *, timeout=120.0):
        url = self.BASE_URL + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._openai_headers(), method="POST")
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout) as resp:
                raw_bytes = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("OpenCode Zen API error {}: {}".format(exc.code, err_body))
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenCode Zen API connection error: {}".format(exc.reason))
        try:
            return json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError("OpenCode Zen API returned invalid JSON: {}".format(raw_bytes[:500]))

    def _request_openai_stream(self, path, body, *, timeout=120.0):
        url = self.BASE_URL + path
        body["stream"] = True
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._openai_headers(), method="POST")
        try:
            return urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("OpenCode Zen API error {}: {}".format(exc.code, err_body))
        except urllib.error.URLError as exc:
            raise RuntimeError("OpenCode Zen API connection error: {}".format(exc.reason))

    def list_models(self) -> List[Dict[str, Any]]:
        now = time.monotonic()
        if self._model_inventory_cache and now < self._model_inventory_expires_at:
            return [dict(model) for model in self._model_inventory_cache]
        fallback_reason = "missing_credential"
        if not self._api_key:
            return self._curated_model_fallback(fallback_reason)
        request = urllib.request.Request(
            self.BASE_URL + "/v1/models",
            headers=self._openai_headers(),
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, context=self._ssl_ctx, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError:
            return self._inventory_fallback("http_error")
        except urllib.error.URLError:
            return self._inventory_fallback("connection_error")
        except TimeoutError:
            return self._inventory_fallback("timeout")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return self._inventory_fallback("invalid_response")
        records = payload.get("data") if isinstance(payload, dict) else []
        models = []
        curated_by_id = {model["model_id"]: model for model in self.CURATED_MODELS}
        for raw in records if isinstance(records, list) else []:
            item = raw if isinstance(raw, dict) else {"id": raw}
            model_id = str(item.get("id") or item.get("model_id") or item.get("name") or "").strip()
            if not model_id or any(model["model_id"] == model_id for model in models):
                continue
            display_name = str(item.get("display_name") or item.get("displayName") or model_id)
            model = dict(curated_by_id.get(model_id) or {})
            metadata = dict(model.get("metadata") or {})
            metadata.update(
                {
                    "source": "openai_models_endpoint",
                    "source_endpoint": "/v1/models",
                    "inventory_source": "live",
                    "visibility_scope": "account",
                }
            )
            model.update(
                {
                    "id": f"opencode-zen/{model_id}",
                    "model_id": model_id,
                    "provider_id": "opencode-zen",
                    "provider": "opencode-zen",
                    "name": display_name,
                    "display_name": display_name,
                    "type": "chat",
                    "capabilities": dict(
                        model.get("capabilities")
                        or {
                            "chat": True,
                            "text_input": True,
                            "text_output": True,
                            "streaming": True,
                        }
                    ),
                    "metadata": metadata,
                }
            )
            models.append(model)
        if models:
            self._model_inventory_cache = [dict(model) for model in models]
            self._model_inventory_expires_at = now + self.MODEL_INVENTORY_TTL_SECONDS
            return [dict(model) for model in models]
        return self._inventory_fallback("empty_inventory")

    def _inventory_fallback(self, reason: str) -> List[Dict[str, Any]]:
        if self._model_inventory_cache:
            models: List[Dict[str, Any]] = []
            for raw in self._model_inventory_cache:
                model = dict(raw)
                metadata = dict(model.get("metadata") or {})
                metadata.update(
                    {
                        "inventory_source": "last_known_good",
                        "inventory_fallback_reason": reason,
                        "inventory_stale": True,
                    }
                )
                model["metadata"] = metadata
                models.append(model)
            return models
        return self._curated_model_fallback(reason)

    @classmethod
    def _curated_model_fallback(cls, reason: str) -> List[Dict[str, Any]]:
        models: List[Dict[str, Any]] = []
        for raw in cls.CURATED_MODELS:
            model = dict(raw)
            metadata = dict(model.get("metadata") or {})
            metadata.update(
                {
                    "source": "curated_fallback",
                    "inventory_source": "curated_fallback",
                    "inventory_fallback_reason": reason,
                    "visibility_scope": "curated",
                }
            )
            model["metadata"] = metadata
            models.append(model)
        return models

    @staticmethod
    def _params_with_token_floor(params: Dict[str, Any] | None) -> Dict[str, Any]:
        next_params = dict(params or {})
        try:
            requested = int(next_params.get("max_tokens", 4096) or 4096)
        except (TypeError, ValueError):
            requested = 4096
        next_params["max_tokens"] = max(requested, 96)
        return next_params

    @classmethod
    def _openai_params(cls, params: Dict[str, Any] | None) -> Dict[str, Any]:
        raw = dict(params or {})
        translated = {key: raw[key] for key in cls._OPENAI_CHAT_PARAM_KEYS if key in raw}
        for key in ("request_timeout", "timeout"):
            if key in raw:
                translated[key] = raw[key]
        return translated

    @staticmethod
    def _request_timeout(params: Dict[str, Any] | None) -> float:
        raw = dict(params or {})
        value = raw.get("request_timeout", raw.get("timeout", 120))
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            timeout = 120.0
        return max(2.0, min(timeout, 120.0))

    def _request_timeout_kwargs(self, params: Dict[str, Any] | None) -> Dict[str, float]:
        raw = dict(params or {})
        if "request_timeout" not in raw and "timeout" not in raw:
            return {}
        return {"timeout": self._request_timeout(raw)}

    @classmethod
    def _copy_openai_chat_params(cls, body: Dict[str, Any], params: Dict[str, Any]) -> None:
        for key in cls._OPENAI_CHAT_PARAM_KEYS:
            if key in params:
                body[key] = params[key]

    def _complete_openai_chat(self, model_id, messages, params):
        params = self._openai_params(params)
        body = {"model": model_id, "messages": OpenAIProvider.build_request(self, messages)}
        self._copy_openai_chat_params(body, params)
        raw = self._request_openai_json(
            "/v1/chat/completions",
            body,
            **self._request_timeout_kwargs(params),
        )
        return OpenAIProvider.parse_response(self, raw)

    def _stream_openai_chat(self, model_id, messages, params):
        params = self._openai_params(params)
        body = {"model": model_id, "messages": OpenAIProvider.build_request(self, messages)}
        self._copy_openai_chat_params(body, params)
        body.setdefault("stream_options", {"include_usage": True})
        resp = self._request_openai_stream(
            "/v1/chat/completions",
            body,
            **self._request_timeout_kwargs(params),
        )
        tool_call_state = {}
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        saw_stream_end = False
        try:
            for payload in OpenAIProvider._parse_sse_lines(resp):
                payload = str(payload or "").strip()
                if not payload:
                    continue
                if payload == "[DONE]":
                    if not saw_stream_end:
                        yield {
                            "type": "stream_end",
                            "finish_reason": "stop",
                            "usage": usage,
                        }
                        saw_stream_end = True
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                usage_raw = obj.get("usage") or {}
                if usage_raw:
                    usage = {
                        "input_tokens": usage_raw.get("prompt_tokens", 0),
                        "output_tokens": usage_raw.get("completion_tokens", 0),
                        "total_tokens": usage_raw.get("total_tokens", 0),
                    }
                choices = obj.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield {"type": "content_delta", "delta": {"type": "text", "text": text}}
                reasoning_text = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or delta.get("thinking")
                )
                if reasoning_text:
                    yield {
                        "type": "reasoning_delta",
                        "delta": {"type": "text", "text": str(reasoning_text)},
                    }
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
                    yield {
                        "type": "stream_end",
                        "finish_reason": finish,
                        "usage": usage,
                    }
                    saw_stream_end = True
            if not saw_stream_end:
                yield {
                    "type": "stream_end",
                    "finish_reason": "stop",
                    "usage": usage,
                }
        finally:
            resp.close()

    def complete(self, model, messages, tools, params):
        model_id = self._assert_supported_model(model)
        if model_id in self.ANTHROPIC_MESSAGES_MODELS:
            del tools
            return super().complete(model_id, messages, [], self._params_with_token_floor(params))
        return self._complete_openai_chat(model_id, messages, params)

    def stream(self, model, messages, tools, params):
        model_id = self._assert_supported_model(model)
        if model_id in self.ANTHROPIC_MESSAGES_MODELS:
            del tools
            yield from super().stream(model_id, messages, [], self._params_with_token_floor(params))
            return
        yield from self._stream_openai_chat(model_id, messages, params)
