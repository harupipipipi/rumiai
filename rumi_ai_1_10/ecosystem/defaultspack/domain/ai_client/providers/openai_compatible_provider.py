from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..base_provider import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    """Manifest-configurable OpenAI-compatible provider adapter."""

    def __init__(
        self,
        *,
        provider_id: str,
        display_name: str = "",
        api_key_env: str = "",
        base_url_env: str = "",
        default_base_url: str = "",
        credential_required: bool = True,
        known_models: Optional[List[Dict[str, Any]]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.provider_id = provider_id
        self.display_name = display_name or provider_id
        self._api_key_env = api_key_env
        self._base_url_env = base_url_env
        self._default_base_url = default_base_url.rstrip("/")
        self._credential_required = credential_required
        self._api_key = os.environ.get(api_key_env, "") if api_key_env else ""
        self._base_url = (
            os.environ.get(base_url_env, "").rstrip("/") if base_url_env else ""
        ) or self._default_base_url
        self._ssl_ctx = ssl.create_default_context()
        self._extra_headers = dict(extra_headers or {})
        self.KNOWN_MODELS = list(known_models or [])

    @classmethod
    def from_manifest(
        cls,
        manifest: Dict[str, Any],
        *,
        model_manifests: Optional[List[Dict[str, Any]]] = None,
    ) -> "OpenAICompatibleProvider":
        known_models: List[Dict[str, Any]] = []
        for item in model_manifests or []:
            model_id = str(item.get("model_id", "")).strip()
            if not model_id:
                continue
            known_models.append(
                {
                    "id": f"{manifest['id']}/{model_id}",
                    "name": item.get("display_name", model_id),
                    "provider": manifest["id"],
                    "type": item.get("type", "chat"),
                    "defaults": dict(item.get("defaults", {})),
                }
            )
        if not known_models:
            known_models = list(manifest.get("models", []))
        if not known_models and manifest.get("default_model"):
            default_model = str(manifest.get("default_model"))
            defaults = {"chat": True}
            for use_case, candidate in (manifest.get("default_model_for", {}) or {}).items():
                if str(candidate) == default_model:
                    defaults[str(use_case)] = True
            known_models = [
                {
                    "id": f"{manifest['id']}/{default_model}",
                    "name": default_model,
                    "provider": manifest["id"],
                    "type": "chat",
                    "defaults": defaults,
                }
            ]
        return cls(
            provider_id=str(manifest["id"]),
            display_name=str(manifest.get("display_name", manifest["id"])),
            api_key_env=str(manifest.get("api_key_env", "")),
            base_url_env=str(manifest.get("base_url_env", "")),
            default_base_url=str(
                manifest.get("default_base_url", "https://api.openai.com/v1")
            ),
            credential_required=bool(manifest.get("credential_required", True)),
            known_models=known_models,
            extra_headers=dict(manifest.get("headers", {})),
        )

    def list_models(self):
        return list(self.KNOWN_MODELS)

    def _headers(self, *, content_type: str = "application/json") -> Dict[str, str]:
        headers: Dict[str, str] = dict(self._extra_headers)
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _ensure_credentials(self) -> None:
        if self._credential_required and not self._api_key:
            raise RuntimeError(
                f"{self.provider_id}: missing API key env ({self._api_key_env})"
            )
        if not self._base_url:
            raise RuntimeError(f"{self.provider_id}: base URL is not configured")

    def _request_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_credentials()
        url = self._base_url + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120) as resp:
                raw_bytes = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{self.provider_id} API error {exc.code}: {err_body}"
            ) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"{self.provider_id} API connection error: {exc.reason}"
            ) from None
        try:
            return json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError(
                f"{self.provider_id} API returned invalid JSON: {raw_bytes[:500]}"
            ) from None

    def _request_stream(self, path: str, body: Dict[str, Any]):
        self._ensure_credentials()
        url = self._base_url + path
        body["stream"] = True
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(),
            method="POST",
        )
        try:
            return urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{self.provider_id} API error {exc.code}: {err_body}"
            ) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"{self.provider_id} API connection error: {exc.reason}"
            ) from None

    @staticmethod
    def _parse_sse_lines(resp):
        buf = b""
        for chunk in iter(lambda: resp.read(4096), b""):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return
                yield payload

    def build_request(self, messages):
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
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
        for key in (
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "response_format",
        ):
            if key in params:
                body[key] = params[key]
        raw = self._request_json("/chat/completions", body)
        return self.parse_response(raw)

    def stream(self, model, messages, tools, params):
        body = {"model": model, "messages": self.build_request(messages)}
        if tools:
            body["tools"] = tools
        for key in (
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "response_format",
        ):
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
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield {
                        "type": "content_delta",
                        "delta": {"type": "text", "text": text},
                    }
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
        if isinstance(input_text, str):
            input_text = [input_text]
        raw = self._request_json("/embeddings", {"model": model, "input": input_text})
        embeddings = [item.get("embedding", []) for item in raw.get("data", [])]
        usage_raw = raw.get("usage", {})
        return {
            "embeddings": embeddings,
            "usage": {
                "input_tokens": usage_raw.get("prompt_tokens", 0),
                "total_tokens": usage_raw.get("total_tokens", 0),
            },
        }

    def image_gen(self, model, prompt, params):
        body = {
            "model": model,
            "prompt": prompt,
            "n": params.get("n", 1),
            "size": params.get("size", "1024x1024"),
            "quality": params.get("quality", "standard"),
            "response_format": params.get("response_format", "b64_json"),
        }
        raw = self._request_json("/images/generations", body)
        images = []
        for item in raw.get("data", []):
            if "b64_json" in item:
                images.append("data:image/png;base64," + item["b64_json"])
            elif "url" in item:
                images.append(item["url"])
        return {"images": images}

    def image_analyze(self, model, image, prompt):
        if image.startswith("data:") or image.startswith("http"):
            image_content = {"type": "image_url", "image_url": {"url": image}}
        else:
            image_content = {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + image},
            }
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content,
                ],
            }
        ]
        raw = self._request_json("/chat/completions", {"model": model, "messages": messages})
        text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"text": text}

    def transcribe(self, model, audio, params):
        if audio.startswith("data:"):
            _, b64data = audio.split(",", 1) if "," in audio else ("", audio)
            audio_bytes = base64.b64decode(b64data)
        else:
            audio_bytes = base64.b64decode(audio)
        ext = params.get("format", "mp3")
        files = {"file": ("audio." + ext, audio_bytes, "audio/" + ext)}
        fields = {"model": model}
        if "language" in params:
            fields["language"] = params["language"]
        resp = self._request_multipart("/audio/transcriptions", fields, files)
        parsed = json.loads(resp.decode("utf-8"))
        return {"text": parsed.get("text", "")}

    def tts(self, model, text, voice):
        voice = voice or "alloy"
        body = {"model": model, "input": text, "voice": voice}
        self._ensure_credentials()
        req = urllib.request.Request(
            self._base_url + "/audio/speech",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120) as resp:
            audio_bytes = resp.read()
        return {"audio": "data:audio/mp3;base64," + base64.b64encode(audio_bytes).decode("ascii")}

    def _request_multipart(self, path: str, fields: Dict[str, Any], files: Dict[str, Any]):
        self._ensure_credentials()
        boundary = "----RumiCompatibleBoundary123"
        parts = []
        for key, value in fields.items():
            parts.append(f"--{boundary}".encode())
            parts.append(f'Content-Disposition: form-data; name="{key}"'.encode())
            parts.append(b"")
            parts.append(str(value).encode("utf-8"))
        for key, (filename, filedata, mime) in files.items():
            parts.append(f"--{boundary}".encode())
            parts.append(
                f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode()
            )
            parts.append(f"Content-Type: {mime}".encode())
            parts.append(b"")
            parts.append(filedata)
        parts.append(f"--{boundary}--".encode())
        body = b"\r\n".join(parts)
        req = urllib.request.Request(
            self._base_url + path,
            data=body,
            method="POST",
        )
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        for key, value in self._headers(content_type="").items():
            req.add_header(key, value)
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120) as resp:
            return resp.read()
