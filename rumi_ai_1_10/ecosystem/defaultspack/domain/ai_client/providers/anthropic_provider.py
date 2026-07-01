import json
import os
import ssl
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from ..base_provider import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic API provider."""

    BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    KNOWN_MODELS = [
        {"id": "anthropic/claude-opus-4-6", "name": "Claude Opus 4.6", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-haiku-4-5", "name": "Claude Haiku 4.5", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-sonnet-4-20250514", "name": "Claude Sonnet 4 snapshot", "provider": "anthropic", "type": "chat"},
    ]

    def __init__(self):
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._ssl_ctx = ssl.create_default_context()

    def _headers(self):
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    def _request_json(self, path, body):
        url = self.BASE_URL + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120) as resp:
                raw_bytes = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("Anthropic API error {}: {}".format(exc.code, err_body))
        except urllib.error.URLError as exc:
            raise RuntimeError("Anthropic API connection error: {}".format(exc.reason))
        try:
            return json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError("Anthropic API returned invalid JSON: {}".format(raw_bytes[:500]))

    def _request_stream(self, path, body):
        url = self.BASE_URL + path
        body["stream"] = True
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("Anthropic API error {}: {}".format(exc.code, err_body))
        except urllib.error.URLError as exc:
            raise RuntimeError("Anthropic API connection error: {}".format(exc.reason))
        return resp

    @staticmethod
    def _parse_sse(resp):
        """Yield SSE event/data pairs from an HTTPResponse."""
        buf = b""
        current_event = ""
        for chunk in iter(lambda: resp.read(4096), b""):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", errors="replace").strip()
                if line.startswith("event: "):
                    current_event = line[7:]
                elif line.startswith("data: "):
                    yield current_event, line[6:]
                    current_event = ""
                elif line == "":
                    pass

    @staticmethod
    def _anthropic_stream_tool_call_events(event_type, obj, state):
        """Translate Anthropic Messages tool_use SSE blocks into stream tool-call events."""
        if event_type == "content_block_start":
            block = obj.get("content_block") if isinstance(obj.get("content_block"), dict) else {}
            if block.get("type") != "tool_use":
                return
            index = str(obj.get("index", len(state)))
            current = state.setdefault(index, {"id": "", "name": "", "started": False, "ended": False})
            if block.get("id"):
                current["id"] = str(block.get("id"))
            if block.get("name"):
                current["name"] = str(block.get("name"))
            call_id = current["id"] or "tool_call_" + index
            if not current["id"]:
                current["id"] = call_id
            if not current["started"]:
                current["started"] = True
                yield {"type": "tool_call_start", "id": call_id, "name": current["name"]}
            input_value = block.get("input")
            if input_value not in (None, "", {}):
                yield {
                    "type": "tool_call_delta",
                    "id": call_id,
                    "name": current["name"],
                    "arguments_chunk": json.dumps(input_value, ensure_ascii=False)
                    if not isinstance(input_value, str)
                    else input_value,
                }
            return
        if event_type == "content_block_delta":
            delta = obj.get("delta") if isinstance(obj.get("delta"), dict) else {}
            if delta.get("type") != "input_json_delta":
                return
            index = str(obj.get("index", len(state)))
            current = state.setdefault(index, {"id": "", "name": "", "started": False, "ended": False})
            call_id = current["id"] or "tool_call_" + index
            if not current["id"]:
                current["id"] = call_id
            if not current["started"]:
                current["started"] = True
                yield {"type": "tool_call_start", "id": call_id, "name": current["name"]}
            chunk = delta.get("partial_json")
            if chunk not in (None, ""):
                yield {
                    "type": "tool_call_delta",
                    "id": call_id,
                    "name": current["name"],
                    "arguments_chunk": str(chunk),
                }
            return
        if event_type == "content_block_stop":
            index = str(obj.get("index", ""))
            current = state.get(index)
            if current and current.get("started") and not current.get("ended"):
                current["ended"] = True
                yield {"type": "tool_call_end", "id": current.get("id", ""), "name": current.get("name", "")}

    @staticmethod
    def _anthropic_stream_tool_call_end_events(state):
        for current in state.values():
            if current.get("started") and not current.get("ended"):
                current["ended"] = True
                yield {"type": "tool_call_end", "id": current.get("id", ""), "name": current.get("name", "")}

    @staticmethod
    def _anthropic_role(role):
        return "assistant" if role == "assistant" else "user"

    @staticmethod
    def _tool_use_parts(tool_calls):
        parts = []
        for tool_call in tool_calls or []:
            if not isinstance(tool_call, dict):
                continue
            function_def = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
            tool_name = str(function_def.get("name") or tool_call.get("name") or "").strip()
            if not tool_name:
                continue
            arguments = function_def.get("arguments", tool_call.get("input", {}))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"value": arguments}
            elif not isinstance(arguments, dict):
                arguments = {"value": arguments}
            parts.append(
                {
                    "type": "tool_use",
                    "id": str(tool_call.get("id") or tool_call.get("tool_call_id") or "").strip(),
                    "name": tool_name,
                    "input": arguments,
                }
            )
        return parts

    @staticmethod
    def _tool_result_part(message):
        content = message.get("content", "")
        if isinstance(content, list):
            result_content = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = str(part.get("text", ""))
                else:
                    text = json.dumps(part, ensure_ascii=False)
                if text:
                    result_content.append({"type": "text", "text": text})
        else:
            result_content = str(content or "")
        return {
            "type": "tool_result",
            "tool_use_id": str(message.get("tool_call_id") or message.get("id") or "").strip(),
            "content": result_content,
        }

    @staticmethod
    def _content_parts(content):
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []
        if not isinstance(content, list):
            if content in (None, ""):
                return []
            return [{"type": "text", "text": str(content)}]
        parts = []
        for part in content:
            if part.get("type") == "text":
                parts.append({"type": "text", "text": part.get("text", "")})
            elif part.get("type") == "image" and part.get("source"):
                parts.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": part["source"].get("media_type", "image/png"),
                            "data": part["source"].get("data", ""),
                        },
                    }
                )
            elif part.get("type") == "image_url":
                img_url = part.get("image_url", {}).get("url", "")
                if img_url.startswith("data:"):
                    header, b64 = img_url.split(",", 1) if "," in img_url else ("", img_url)
                    media = "image/png"
                    if "image/jpeg" in header:
                        media = "image/jpeg"
                    elif "image/gif" in header:
                        media = "image/gif"
                    elif "image/webp" in header:
                        media = "image/webp"
                    parts.append(
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media, "data": b64},
                        }
                    )
                else:
                    parts.append({"type": "image", "source": {"type": "url", "url": img_url}})
            elif part.get("type") in {"tool_result", "tool_use"}:
                parts.append(part)
            else:
                parts.append(part)
        return parts

    def build_request(self, messages):
        """Translate standard messages to Anthropic Messages payload shape."""
        system_parts = []
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            anthropic_role = self._anthropic_role(role)
            if role == "system":
                if isinstance(content, str):
                    system_parts.append({"type": "text", "text": content})
                elif isinstance(content, list):
                    system_parts.extend(content)
                continue
            if role == "tool":
                converted.append({"role": "user", "content": [self._tool_result_part(msg)]})
                continue
            tool_use_parts = self._tool_use_parts(msg.get("tool_calls"))
            if tool_use_parts:
                parts = self._content_parts(content)
                parts.extend(tool_use_parts)
                converted.append({"role": "assistant", "content": parts})
                continue
            if isinstance(content, str):
                converted.append({"role": anthropic_role, "content": content})
            elif isinstance(content, list):
                converted.append({"role": anthropic_role, "content": self._content_parts(content)})
            else:
                converted.append({"role": anthropic_role, "content": content})
        return system_parts, converted

    def parse_response(self, raw):
        """Translate Anthropic Messages JSON to the standard response shape."""
        content_blocks = raw.get("content", [])
        content = []
        for block in content_blocks:
            if block.get("type") == "text":
                content.append({"type": "text", "text": block.get("text", "")})
            elif block.get("type") == "tool_use":
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": block.get("input", {}),
                    }
                )
            else:
                content.append(block)
        stop = raw.get("stop_reason", "end_turn") or "end_turn"
        finish_map = {"end_turn": "stop", "max_tokens": "length", "stop_sequence": "stop", "tool_use": "tool_calls"}
        finish = finish_map.get(stop, stop)
        usage_raw = raw.get("usage", {})
        usage = {
            "input_tokens": usage_raw.get("input_tokens", 0),
            "output_tokens": usage_raw.get("output_tokens", 0),
            "total_tokens": usage_raw.get("input_tokens", 0) + usage_raw.get("output_tokens", 0),
        }
        return {
            "content": content,
            "finish_reason": finish,
            "usage": usage,
            "raw_extra": {"id": raw.get("id", ""), "model": raw.get("model", "")},
        }

    @staticmethod
    def _translate_params(params):
        translated = dict(params or {})
        thinking_level = str(translated.pop("thinking_level", "") or "").strip()
        if thinking_level in {"low", "medium", "high", "xhigh"} and "thinking" not in translated:
            budgets = {"low": 1024, "medium": 4096, "high": 8192, "xhigh": 16384}
            translated["thinking"] = {
                "type": "enabled",
                "budget_tokens": budgets[thinking_level],
            }
            translated["max_tokens"] = max(
                int(translated.get("max_tokens", 4096) or 4096),
                budgets[thinking_level] + 1024,
            )
        return translated

    @staticmethod
    def _copy_chat_params(body, params):
        for key in ("temperature", "top_p", "top_k", "stop_sequences", "thinking"):
            if key in params:
                body[key] = params[key]
        if "metadata" in params:
            body["metadata"] = params["metadata"]

    @staticmethod
    def _normalize_tools(tools):
        normalized = []
        for tool in tools or []:
            if not isinstance(tool, dict):
                continue
            function_def = tool.get("function") if isinstance(tool.get("function"), dict) else None
            if function_def is not None:
                normalized.append(
                    {
                        "name": function_def.get("name", ""),
                        "description": function_def.get("description", ""),
                        "input_schema": function_def.get("parameters", {"type": "object", "properties": {}}),
                    }
                )
                continue
            normalized.append(dict(tool))
        return normalized

    def complete(self, model, messages, tools, params):
        params = self._translate_params(params)
        system_parts, converted = self.build_request(messages)
        body = {"model": model, "messages": converted, "max_tokens": params.get("max_tokens", 4096)}
        if system_parts:
            body["system"] = system_parts
        normalized_tools = self._normalize_tools(tools)
        if normalized_tools:
            body["tools"] = normalized_tools
        self._copy_chat_params(body, params)
        raw = self._request_json("/v1/messages", body)
        return self.parse_response(raw)

    def stream(self, model, messages, tools, params):
        params = self._translate_params(params)
        system_parts, converted = self.build_request(messages)
        body = {"model": model, "messages": converted, "max_tokens": params.get("max_tokens", 4096)}
        if system_parts:
            body["system"] = system_parts
        normalized_tools = self._normalize_tools(tools)
        if normalized_tools:
            body["tools"] = normalized_tools
        self._copy_chat_params(body, params)
        resp = self._request_stream("/v1/messages", body)
        usage_accum = {"input_tokens": 0, "output_tokens": 0}
        tool_call_state = {}
        try:
            for event_type, data_str in self._parse_sse(resp):
                try:
                    obj = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if event_type == "message_start":
                    msg = obj.get("message", {})
                    usage = msg.get("usage", {})
                    usage_accum["input_tokens"] = usage.get("input_tokens", 0)
                elif event_type == "content_block_start":
                    yield from self._anthropic_stream_tool_call_events(event_type, obj, tool_call_state)
                elif event_type == "content_block_delta":
                    delta = obj.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield {"type": "content_delta", "delta": {"type": "text", "text": delta.get("text", "")}}
                    yield from self._anthropic_stream_tool_call_events(event_type, obj, tool_call_state)
                elif event_type == "content_block_stop":
                    yield from self._anthropic_stream_tool_call_events(event_type, obj, tool_call_state)
                elif event_type == "message_delta":
                    delta = obj.get("delta", {})
                    usage = obj.get("usage", {})
                    usage_accum["output_tokens"] = usage.get("output_tokens", 0)
                    stop = delta.get("stop_reason", "end_turn") or "end_turn"
                    finish_map = {"end_turn": "stop", "max_tokens": "length", "stop_sequence": "stop", "tool_use": "tool_calls"}
                    finish = finish_map.get(stop, stop)
                    yield from self._anthropic_stream_tool_call_end_events(tool_call_state)
                    yield {
                        "type": "stream_end",
                        "finish_reason": finish,
                        "usage": {
                            "input_tokens": usage_accum["input_tokens"],
                            "output_tokens": usage_accum["output_tokens"],
                            "total_tokens": usage_accum["input_tokens"] + usage_accum["output_tokens"],
                        },
                    }
                elif event_type == "message_stop":
                    pass
        finally:
            resp.close()

    def embed(self, model, input_text):
        raise NotImplementedError("Anthropic does not support embedding. Use openai/text-embedding-3-small instead.")

    def image_gen(self, model, prompt, params):
        raise NotImplementedError("Anthropic does not support image generation. Use openai/dall-e-3 instead.")

    def image_analyze(self, model, image, prompt):
        """Analyze an image with an Anthropic vision model."""
        if image.startswith("data:"):
            header, b64 = image.split(",", 1) if "," in image else ("", image)
            media = "image/png"
            if "image/jpeg" in header:
                media = "image/jpeg"
            elif "image/gif" in header:
                media = "image/gif"
            elif "image/webp" in header:
                media = "image/webp"
        elif image.startswith("http"):
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "url", "url": image}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            body = {"model": model, "messages": messages, "max_tokens": 4096}
            raw = self._request_json("/v1/messages", body)
            text = ""
            for block in raw.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            return {"text": text}
        else:
            b64 = image
            media = "image/png"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        body = {"model": model, "messages": messages, "max_tokens": 4096}
        raw = self._request_json("/v1/messages", body)
        text = ""
        for block in raw.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        return {"text": text}

    def transcribe(self, model, audio, params):
        raise NotImplementedError("Anthropic does not support audio transcription. Use openai/whisper-1 instead.")

    def tts(self, model, text, voice):
        raise NotImplementedError("Anthropic does not support text-to-speech. Use openai/tts-1 instead.")
