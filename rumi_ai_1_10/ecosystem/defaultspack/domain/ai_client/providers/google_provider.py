from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from .openai_compatible_provider import OpenAICompatibleProvider
from .profile_catalog import merge_curated_and_profiles, profile_dir_for


class GoogleProvider(OpenAICompatibleProvider):
    """Google Gemini provider using Google's OpenAI-compatible Gemini endpoint."""

    provider_name = "google"
    display_name = "Google"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
    PROFILE_DIR = profile_dir_for("google", __file__)

    curated_models: List[Dict[str, Any]] = [
        {
            "id": "google/gemini-2.5-pro",
            "model_id": "gemini-2.5-pro",
            "name": "Gemini 2.5 Pro",
            "display_name": "Gemini 2.5 Pro",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
            "supports_thinking": True,
            "thinking_levels": ["none", "low", "medium", "high"],
            "default_thinking_level": "medium",
            "defaults": {"chat": True, "large": True},
        },
        {
            "id": "google/gemini-2.5-flash",
            "model_id": "gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "display_name": "Gemini 2.5 Flash",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
            "supports_thinking": True,
            "thinking_levels": ["none", "low", "medium", "high"],
            "default_thinking_level": "medium",
            "defaults": {"fast": True},
        },
        {
            "id": "google/gemini-3-pro-preview",
            "model_id": "gemini-3-pro-preview",
            "name": "Gemini 3 Pro Preview",
            "display_name": "Gemini 3 Pro Preview",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
            "supports_thinking": True,
            "thinking_levels": ["low", "high"],
            "default_thinking_level": "high",
        },
        {
            "id": "google/gemini-3-flash-preview",
            "model_id": "gemini-3-flash-preview",
            "name": "Gemini 3 Flash Preview",
            "display_name": "Gemini 3 Flash Preview",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
            "supports_thinking": True,
            "thinking_levels": ["none", "low", "medium", "high"],
            "default_thinking_level": "medium",
        },
        {
            "id": "google/gemini-2.5-flash-lite",
            "model_id": "gemini-2.5-flash-lite",
            "name": "Gemini 2.5 Flash-Lite",
            "display_name": "Gemini 2.5 Flash-Lite",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
            "supports_thinking": True,
            "thinking_levels": ["none", "low", "medium", "high"],
            "default_thinking_level": "medium",
        },
        {
            "id": "google/gemini-2.0-flash-lite",
            "model_id": "gemini-2.0-flash-lite",
            "name": "Gemini 2.0 Flash-Lite",
            "display_name": "Gemini 2.0 Flash-Lite",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
        },
        {
            "id": "google/gemma-4-31b-it",
            "model_id": "gemma-4-31b-it",
            "name": "Gemma 4 31B IT",
            "display_name": "Gemma 4 31B IT",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
            "supports_thinking": True,
            "thinking_levels": ["low", "high"],
            "default_thinking_level": "high",
        },
        {
            "id": "google/gemma-4-26b-a4b-it",
            "model_id": "gemma-4-26b-a4b-it",
            "name": "Gemma 4 26B A4B IT",
            "display_name": "Gemma 4 26B A4B IT",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "tool_calls", "vision"],
            "supports_thinking": True,
            "thinking_levels": ["low", "high"],
            "default_thinking_level": "high",
        },
        {
            "id": "google/gemma-3-27b-it",
            "model_id": "gemma-3-27b-it",
            "name": "Gemma 3 27B IT",
            "display_name": "Gemma 3 27B IT",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "vision"],
        },
        {
            "id": "google/gemma-3n-e4b-it",
            "model_id": "gemma-3n-e4b-it",
            "name": "Gemma 3n E4B IT",
            "display_name": "Gemma 3n E4B IT",
            "provider": "google",
            "provider_id": "google",
            "type": "chat",
            "capabilities": ["chat", "vision"],
        },
        {
            "id": "google/gemini-embedding-001",
            "model_id": "gemini-embedding-001",
            "name": "Gemini Embedding 001",
            "display_name": "Gemini Embedding 001",
            "provider": "google",
            "provider_id": "google",
            "type": "embedding",
            "defaults": {"embedding": True},
        },
        {
            "id": "google/text-embedding-004",
            "model_id": "text-embedding-004",
            "name": "Text Embedding 004",
            "display_name": "Text Embedding 004",
            "provider": "google",
            "provider_id": "google",
            "type": "embedding",
        },
    ]
    CURATED_MODELS = curated_models
    KNOWN_MODELS = curated_models

    def __init__(self):
        super().__init__(
            provider_id="google",
            display_name="Google",
            api_key_env=["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            base_url_env="GOOGLE_BASE_URL",
            default_base_url=self.BASE_URL,
            known_models=self.curated_models,
        )

    @classmethod
    def _load_profile_models(cls):
        return merge_curated_and_profiles("google", cls.curated_models, cls.PROFILE_DIR)

    def list_models(self):
        return self._normalize_known_models(self._load_profile_models())

    @staticmethod
    def _translate_thinking_level(model: str, thinking_level: str) -> str | None:
        model_id = str(model or "").strip()
        level = str(thinking_level or "").strip().lower()
        if not level:
            return None
        if level == "xhigh":
            level = "high"

        if model_id.startswith("gemini-3-pro"):
            if level == "low":
                return "low"
            if level in {"medium", "high"}:
                return "high"
            return None

        if model_id.startswith("gemini-3-flash"):
            if level == "none":
                return "minimal"
            if level in {"low", "medium", "high"}:
                return level
            return None

        if model_id.startswith("gemini-2.5"):
            if level == "none" and model_id.startswith("gemini-2.5-pro"):
                return None
            if level in {"none", "low", "medium", "high"}:
                return level
            return None

        if model_id.startswith("gemma-4"):
            if level == "low":
                return "low"
            if level in {"medium", "high"}:
                return "high"
            return None

        return None

    @classmethod
    def _translate_params(cls, params, model: str = ""):
        translated = dict(params or {})
        thinking_level = str(translated.pop("thinking_level", "") or "").strip()
        reasoning_effort = cls._translate_thinking_level(model, thinking_level)
        if reasoning_effort and "reasoning_effort" not in translated:
            translated["reasoning_effort"] = reasoning_effort
        return translated

    @staticmethod
    def _copy_chat_params(body, params):
        for key in (
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "response_format",
            "reasoning_effort",
        ):
            if key in params:
                body[key] = params[key]

    @staticmethod
    def _normalize_image_detail(value: Any) -> str | None:
        detail = str(value or "").strip().lower()
        if detail in {"auto", "low", "high"}:
            return detail
        return None

    @classmethod
    def _normalize_image_url_details(cls, messages):
        for message in messages:
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "image_url":
                    continue
                image_url = block.get("image_url")
                if not isinstance(image_url, dict):
                    continue
                detail = cls._normalize_image_detail(
                    image_url.get("detail")
                    or image_url.get("image_detail")
                    or image_url.get("vision_detail")
                    or block.get("image_detail")
                    or block.get("vision_detail")
                )
                for key in ("image_detail", "vision_detail"):
                    image_url.pop(key, None)
                    block.pop(key, None)
                if detail:
                    image_url["detail"] = detail
                else:
                    image_url.pop("detail", None)
        return messages

    def build_request(self, messages):
        return self._normalize_image_url_details(super().build_request(messages))

    @staticmethod
    def _split_inline_thoughts(text: str) -> tuple[list[str], str]:
        thoughts: list[str] = []

        def collect(match: re.Match[str]) -> str:
            thought = str(match.group(1) or "").strip()
            if thought:
                thoughts.append(thought)
            return ""

        visible = re.sub(r"<thought>(.*?)</thought>", collect, str(text or ""), flags=re.DOTALL).strip()
        return thoughts, visible

    def parse_response(self, raw):
        parsed = super().parse_response(raw)
        thinking_parts: list[str] = []
        for block in parsed.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                thoughts, visible = self._split_inline_thoughts(str(block.get("text") or ""))
                thinking_parts.extend(thoughts)
                block["text"] = visible
        if thinking_parts:
            metadata = dict(parsed.get("metadata") or {})
            existing = metadata.get("thinking") if isinstance(metadata.get("thinking"), dict) else {}
            metadata["thinking"] = {
                **existing,
                "state": "completed",
                "transcript": "\n\n".join(thinking_parts),
                "source": "google_inline_thought",
            }
            parsed["metadata"] = metadata
        return parsed

    @staticmethod
    def _sanitize_tool(tool: Any) -> Dict[str, Any] | None:
        """Return the OpenAI-compatible function-tool shape Google accepts."""
        if not isinstance(tool, dict):
            return None
        function_def = tool.get("function")
        if not isinstance(function_def, dict):
            return None
        name = str(function_def.get("name") or "").strip()
        if not name:
            return None
        sanitized_function: Dict[str, Any] = {"name": name}
        description = function_def.get("description")
        if isinstance(description, str) and description:
            sanitized_function["description"] = description
        parameters = function_def.get("parameters")
        if isinstance(parameters, dict):
            sanitized_function["parameters"] = parameters
        else:
            sanitized_function["parameters"] = {"type": "object", "properties": {}, "required": []}
        return {"type": "function", "function": sanitized_function}

    @classmethod
    def _sanitize_tools(cls, tools: Any) -> List[Dict[str, Any]]:
        if not isinstance(tools, list):
            return []
        sanitized: List[Dict[str, Any]] = []
        for tool in tools:
            item = cls._sanitize_tool(tool)
            if item is not None:
                sanitized.append(item)
        return sanitized

    def complete(self, model, messages, tools, params):
        translated = self._translate_params(params, model)
        body = {"model": model, "messages": self.build_request(messages)}
        sanitized_tools = self._sanitize_tools(tools)
        if sanitized_tools:
            body["tools"] = sanitized_tools
        self._copy_chat_params(body, translated)
        raw = self._request_json("/chat/completions", body)
        return self.parse_response(raw)

    def stream(self, model, messages, tools, params):
        translated = self._translate_params(params, model)
        body = {"model": model, "messages": self.build_request(messages)}
        sanitized_tools = self._sanitize_tools(tools)
        if sanitized_tools:
            body["tools"] = sanitized_tools
        self._copy_chat_params(body, translated)
        resp = self._request_stream("/chat/completions", body)
        try:
            for payload in self._parse_sse_lines(resp):
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
                finish = choices[0].get("finish_reason")
                if finish:
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
