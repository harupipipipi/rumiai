import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import urllib.request
import urllib.error
import base64
import ssl

from domain.ai_client.base_provider import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic API プロバイダー (Claude 4 Opus, Claude 4 Sonnet 等)"""

    BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    KNOWN_MODELS = [
        {"id": "anthropic/claude-opus-4-0", "name": "Claude Opus 4", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-sonnet-4-0", "name": "Claude Sonnet 4", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-3-opus-20240229", "name": "Claude 3 Opus", "provider": "anthropic", "type": "chat"},
        {"id": "anthropic/claude-3-haiku-20240307", "name": "Claude 3 Haiku", "provider": "anthropic", "type": "chat"},
    ]

    def __init__(self):
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._ssl_ctx = ssl.create_default_context()

    # ── internal helpers ────────────────────────────────────────────────

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
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError("Anthropic API error {}: {}".format(e.code, err_body))
        except urllib.error.URLError as e:
            raise RuntimeError("Anthropic API connection error: {}".format(e.reason))
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
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError("Anthropic API error {}: {}".format(e.code, err_body))
        except urllib.error.URLError as e:
            raise RuntimeError("Anthropic API connection error: {}".format(e.reason))
        return resp

    @staticmethod
    def _parse_sse(resp):
        """HTTPResponse から SSE の event/data ペアを yield"""
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

    # ── build_request / parse_response ──────────────────────────────────

    def build_request(self, messages):
        """StandardMessage → Anthropic 形式に変換。system を分離する。"""
        system_parts = []
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                if isinstance(content, str):
                    system_parts.append({"type": "text", "text": content})
                elif isinstance(content, list):
                    system_parts.extend(content)
                continue
            if isinstance(content, str):
                converted.append({"role": role, "content": content})
            elif isinstance(content, list):
                parts = []
                for c in content:
                    if c.get("type") == "text":
                        parts.append({"type": "text", "text": c.get("text", "")})
                    elif c.get("type") == "image" and c.get("source"):
                        parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": c["source"].get("media_type", "image/png"),
                                "data": c["source"].get("data", ""),
                            },
                        })
                    elif c.get("type") == "image_url":
                        img_url = c.get("image_url", {}).get("url", "")
                        if img_url.startswith("data:"):
                            header, b64 = img_url.split(",", 1) if "," in img_url else ("", img_url)
                            media = "image/png"
                            if "image/jpeg" in header:
                                media = "image/jpeg"
                            elif "image/gif" in header:
                                media = "image/gif"
                            elif "image/webp" in header:
                                media = "image/webp"
                            parts.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": media, "data": b64},
                            })
                        else:
                            parts.append({
                                "type": "image",
                                "source": {"type": "url", "url": img_url},
                            })
                    elif c.get("type") == "tool_result":
                        parts.append(c)
                    elif c.get("type") == "tool_use":
                        parts.append(c)
                    else:
                        parts.append(c)
                converted.append({"role": role, "content": parts})
            else:
                converted.append({"role": role, "content": content})
        return system_parts, converted

    def parse_response(self, raw):
        """Anthropic messages JSON → StandardResponse"""
        content_blocks = raw.get("content", [])
        content = []
        for block in content_blocks:
            if block.get("type") == "text":
                content.append({"type": "text", "text": block.get("text", "")})
            elif block.get("type") == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input", {}),
                })
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

    # ── 9 required methods ──────────────────────────────────────────────

    def complete(self, model, messages, tools, params):
        system_parts, converted = self.build_request(messages)
        body = {"model": model, "messages": converted, "max_tokens": params.get("max_tokens", 4096)}
        if system_parts:
            body["system"] = system_parts
        if tools:
            body["tools"] = tools
        for k in ("temperature", "top_p", "top_k", "stop_sequences"):
            if k in params:
                body[k] = params[k]
        if "metadata" in params:
            body["metadata"] = params["metadata"]
        raw = self._request_json("/v1/messages", body)
        return self.parse_response(raw)

    def stream(self, model, messages, tools, params):
        system_parts, converted = self.build_request(messages)
        body = {"model": model, "messages": converted, "max_tokens": params.get("max_tokens", 4096)}
        if system_parts:
            body["system"] = system_parts
        if tools:
            body["tools"] = tools
        for k in ("temperature", "top_p", "top_k", "stop_sequences"):
            if k in params:
                body[k] = params[k]
        resp = self._request_stream("/v1/messages", body)
        usage_accum = {"input_tokens": 0, "output_tokens": 0}
        try:
            for event_type, data_str in self._parse_sse(resp):
                try:
                    obj = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if event_type == "message_start":
                    msg = obj.get("message", {})
                    u = msg.get("usage", {})
                    usage_accum["input_tokens"] = u.get("input_tokens", 0)
                elif event_type == "content_block_delta":
                    delta = obj.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield {"type": "content_delta", "delta": {"type": "text", "text": delta.get("text", "")}}
                elif event_type == "message_delta":
                    delta = obj.get("delta", {})
                    u = obj.get("usage", {})
                    usage_accum["output_tokens"] = u.get("output_tokens", 0)
                    stop = delta.get("stop_reason", "end_turn") or "end_turn"
                    finish_map = {"end_turn": "stop", "max_tokens": "length", "stop_sequence": "stop", "tool_use": "tool_calls"}
                    finish = finish_map.get(stop, stop)
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
        """Claude の vision 機能で画像解析"""
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
            messages = [{"role": "user", "content": [
                {"type": "image", "source": {"type": "url", "url": image}},
                {"type": "text", "text": prompt},
            ]}]
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
        messages = [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
            {"type": "text", "text": prompt},
        ]}]
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
