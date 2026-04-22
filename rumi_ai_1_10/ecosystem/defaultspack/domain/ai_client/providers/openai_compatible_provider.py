import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import ssl
import urllib.error
import urllib.request

from domain.ai_client.base_provider import BaseProvider
from domain.ai_client.providers.profile_catalog import merge_curated_and_profiles, profile_dir_for


class OpenAICompatibleProvider(BaseProvider):
    provider_name = ""
    display_name = ""
    env_vars = ()
    base_url_env_vars = ()
    default_base_url = ""
    supports_embeddings = False
    curated_models = []
    extra_headers = {}
    timeout = 120

    def __init__(self):
        self._api_key = self._resolve_api_key()
        self._base_url = self._resolve_base_url()
        self._ssl_ctx = ssl.create_default_context()

    @classmethod
    def profile_dir(cls):
        return profile_dir_for(cls.provider_name, __file__)

    @classmethod
    def list_curated_models(cls):
        return [dict(item) for item in cls.curated_models]

    @classmethod
    def list_profile_models(cls):
        return merge_curated_and_profiles(cls.provider_name, cls.curated_models, cls.profile_dir())

    @classmethod
    def list_models(cls):
        return cls.list_profile_models()

    def _resolve_api_key(self):
        for env_var in self.env_vars:
            value = os.environ.get(env_var, "")
            if value:
                return value
        return ""

    def _resolve_base_url(self):
        for env_var in self.base_url_env_vars:
            value = os.environ.get(env_var, "")
            if value:
                return value.rstrip("/")
        return self.default_base_url.rstrip("/")

    def _headers(self, content_type="application/json"):
        headers = {"Authorization": "Bearer " + self._api_key}
        if content_type:
            headers["Content-Type"] = content_type
        for key, value in self.extra_headers.items():
            headers.setdefault(key, value)
        return headers

    def _request_json(self, path, body):
        if not self._api_key:
            raise RuntimeError("{} API key is not set.".format(self.display_name or self.provider_name))
        url = self._base_url + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=self.timeout) as resp:
                raw_bytes = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError("{} API error {}: {}".format(self.display_name or self.provider_name, e.code, err_body))
        except urllib.error.URLError as e:
            raise RuntimeError("{} API connection error: {}".format(self.display_name or self.provider_name, e.reason))
        try:
            return json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError("{} API returned invalid JSON: {}".format(self.display_name or self.provider_name, raw_bytes[:500]))

    def _request_stream(self, path, body):
        if not self._api_key:
            raise RuntimeError("{} API key is not set.".format(self.display_name or self.provider_name))
        url = self._base_url + path
        body["stream"] = True
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        try:
            return urllib.request.urlopen(req, context=self._ssl_ctx, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError("{} API error {}: {}".format(self.display_name or self.provider_name, e.code, err_body))
        except urllib.error.URLError as e:
            raise RuntimeError("{} API connection error: {}".format(self.display_name or self.provider_name, e.reason))

    @staticmethod
    def _parse_sse_lines(resp):
        buf = b""
        for chunk in iter(lambda: resp.read(4096), b""):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", errors="replace").strip()
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        return
                    yield payload

    def build_request(self, messages):
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append({"type": "text", "text": item.get("text", "")})
                    elif item.get("type") == "image_url":
                        parts.append({"type": "image_url", "image_url": item.get("image_url", {})})
                    elif item.get("type") == "image" and item.get("source"):
                        source = item["source"]
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:{};base64,{}".format(
                                        source.get("media_type", "image/png"),
                                        source.get("data", ""),
                                    )
                                },
                            }
                        )
                    else:
                        parts.append(item)
                converted.append({"role": role, "content": parts})
            else:
                converted.append({"role": role, "content": content})
        return converted

    def parse_response(self, raw):
        choice = raw.get("choices", [{}])[0]
        message = choice.get("message", {})
        text = message.get("content", "") or ""
        finish = choice.get("finish_reason", "stop") or "stop"
        usage_raw = raw.get("usage", {})
        usage = {
            "input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0),
            "total_tokens": usage_raw.get("total_tokens", 0),
        }
        content = [{"type": "text", "text": text}]
        tool_calls = message.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "input": tc.get("function", {}).get("arguments", "{}"),
                    }
                )
        return {
            "content": content,
            "finish_reason": finish,
            "usage": usage,
            "raw_extra": {"id": raw.get("id", ""), "model": raw.get("model", "")},
        }

    def complete(self, model, messages, tools, params):
        body = {"model": model, "messages": self.build_request(messages)}
        if tools:
            body["tools"] = tools
        for key in ("temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "stop", "response_format"):
            if key in params:
                body[key] = params[key]
        raw = self._request_json("/chat/completions", body)
        return self.parse_response(raw)

    def stream(self, model, messages, tools, params):
        body = {"model": model, "messages": self.build_request(messages)}
        if tools:
            body["tools"] = tools
        for key in ("temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty", "stop", "response_format"):
            if key in params:
                body[key] = params[key]
        body["stream_options"] = {"include_usage": True}
        resp = self._request_stream("/chat/completions", body)
        try:
            for payload in self._parse_sse_lines(resp):
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

    def embed(self, model, input_text):
        if not self.supports_embeddings:
            raise NotImplementedError("{} does not support embedding.".format(self.display_name or self.provider_name))
        if isinstance(input_text, str):
            input_text = [input_text]
        body = {"model": model, "input": input_text}
        raw = self._request_json("/embeddings", body)
        embeddings = [item["embedding"] for item in raw.get("data", [])]
        usage_raw = raw.get("usage", {})
        return {
            "embeddings": embeddings,
            "usage": {
                "input_tokens": usage_raw.get("prompt_tokens", 0),
                "total_tokens": usage_raw.get("total_tokens", 0),
            },
        }

    def image_gen(self, model, prompt, params):
        raise NotImplementedError("{} generic adapter does not support image generation.".format(self.display_name or self.provider_name))

    def image_analyze(self, model, image, prompt):
        if image.startswith("data:"):
            image_content = {"type": "image_url", "image_url": {"url": image}}
        elif image.startswith("http"):
            image_content = {"type": "image_url", "image_url": {"url": image}}
        else:
            image_content = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, image_content]}]
        body = {"model": model, "messages": self.build_request(messages)}
        raw = self._request_json("/chat/completions", body)
        text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"text": text}

    def transcribe(self, model, audio, params):
        raise NotImplementedError("{} generic adapter does not support transcription.".format(self.display_name or self.provider_name))

    def tts(self, model, text, voice):
        raise NotImplementedError("{} generic adapter does not support TTS.".format(self.display_name or self.provider_name))
