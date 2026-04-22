import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import urllib.request
import urllib.error
import urllib.parse
import base64
import ssl

from ..base_provider import BaseProvider
from .profile_catalog import merge_curated_and_profiles, profile_dir_for


class GoogleProvider(BaseProvider):
    """Google Generative AI API プロバイダー (Gemini 2.5 Pro, Gemini 2.5 Flash 等)"""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    PROFILE_DIR = profile_dir_for("google", __file__)

    CURATED_MODELS = [
        {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "google", "type": "chat"},
        {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "google", "type": "chat"},
        {"id": "google/gemini-3-pro-preview", "name": "Gemini 3 Pro Preview", "provider": "google", "type": "chat"},
        {"id": "google/gemini-3-flash-preview", "name": "Gemini 3 Flash Preview", "provider": "google", "type": "chat"},
        {"id": "google/gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite", "provider": "google", "type": "chat"},
        {"id": "google/gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash-Lite", "provider": "google", "type": "chat"},
        {"id": "google/gemma-4-31b-it", "name": "Gemma 4 31B IT", "provider": "google", "type": "chat"},
        {"id": "google/gemma-3-27b-it", "name": "Gemma 3 27B IT", "provider": "google", "type": "chat"},
        {"id": "google/gemma-3n-e4b-it", "name": "Gemma 3n E4B IT", "provider": "google", "type": "chat"},
        {"id": "google/gemini-embedding-001", "name": "Gemini Embedding 001", "provider": "google", "type": "embedding"},
        {"id": "google/text-embedding-004", "name": "Text Embedding 004", "provider": "google", "type": "embedding"},
    ]
    KNOWN_MODELS = CURATED_MODELS

    def __init__(self):
        self._api_key = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        self._ssl_ctx = ssl.create_default_context()

    @classmethod
    def _load_profile_models(cls):
        return merge_curated_and_profiles("google", cls.CURATED_MODELS, cls.PROFILE_DIR)

    def list_models(self):
        return self._load_profile_models()

    # ── internal helpers ────────────────────────────────────────────────

    def _url(self, model, method):
        return "{}/models/{}:{}?key={}".format(self.BASE_URL, model, method, self._api_key)

    def _request_json(self, url, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120) as resp:
                raw_bytes = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError("Google API error {}: {}".format(e.code, err_body))
        except urllib.error.URLError as e:
            raise RuntimeError("Google API connection error: {}".format(e.reason))
        try:
            return json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError("Google API returned invalid JSON: {}".format(raw_bytes[:500]))

    def _request_stream(self, url, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=120)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError("Google API error {}: {}".format(e.code, err_body))
        except urllib.error.URLError as e:
            raise RuntimeError("Google API connection error: {}".format(e.reason))
        return resp

    # ── build_request / parse_response ──────────────────────────────────

    def build_request(self, messages):
        """StandardMessage → Gemini contents 形式 + systemInstruction"""
        system_text = ""
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                if isinstance(content, str):
                    system_text += content + "\n"
                elif isinstance(content, list):
                    for c in content:
                        if c.get("type") == "text":
                            system_text += c.get("text", "") + "\n"
                continue
            gemini_role = "model" if role == "assistant" else "user"
            parts = []
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for c in content:
                    if c.get("type") == "text":
                        parts.append({"text": c.get("text", "")})
                    elif c.get("type") == "image" and c.get("source"):
                        src = c["source"]
                        parts.append({
                            "inline_data": {
                                "mime_type": src.get("media_type", "image/png"),
                                "data": src.get("data", ""),
                            }
                        })
                    elif c.get("type") == "image_url":
                        img_url = c.get("image_url", {}).get("url", "")
                        if img_url.startswith("data:"):
                            header, b64 = img_url.split(",", 1) if "," in img_url else ("", img_url)
                            mime = "image/png"
                            if "image/jpeg" in header:
                                mime = "image/jpeg"
                            elif "image/gif" in header:
                                mime = "image/gif"
                            elif "image/webp" in header:
                                mime = "image/webp"
                            parts.append({"inline_data": {"mime_type": mime, "data": b64}})
                        else:
                            parts.append({"file_data": {"file_uri": img_url, "mime_type": "image/png"}})
                    else:
                        text_val = c.get("text", "")
                        if text_val:
                            parts.append({"text": text_val})
            if parts:
                contents.append({"role": gemini_role, "parts": parts})
        system_instruction = None
        if system_text.strip():
            system_instruction = {"parts": [{"text": system_text.strip()}]}
        return system_instruction, contents

    def parse_response(self, raw):
        """Gemini generateContent JSON → StandardResponse"""
        candidates = raw.get("candidates", [])
        content = []
        finish = "stop"
        if candidates:
            cand = candidates[0]
            parts = cand.get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    content.append({"type": "text", "text": part["text"]})
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    content.append({
                        "type": "tool_use",
                        "id": "",
                        "name": fc.get("name", ""),
                        "input": fc.get("args", {}),
                    })
            reason = cand.get("finishReason", "STOP")
            reason_map = {"STOP": "stop", "MAX_TOKENS": "length", "SAFETY": "safety", "RECITATION": "recitation"}
            finish = reason_map.get(reason, reason.lower())
        if not content:
            content = [{"type": "text", "text": ""}]
        usage_raw = raw.get("usageMetadata", {})
        usage = {
            "input_tokens": usage_raw.get("promptTokenCount", 0),
            "output_tokens": usage_raw.get("candidatesTokenCount", 0),
            "total_tokens": usage_raw.get("totalTokenCount", 0),
        }
        return {
            "content": content,
            "finish_reason": finish,
            "usage": usage,
            "raw_extra": {"model_version": raw.get("modelVersion", "")},
        }

    # ── 9 required methods ──────────────────────────────────────────────

    def complete(self, model, messages, tools, params):
        system_instruction, contents = self.build_request(messages)
        body = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = system_instruction
        if tools:
            gemini_tools = self._convert_tools(tools)
            if gemini_tools:
                body["tools"] = gemini_tools
        gen_config = {}
        for k, gk in [("temperature", "temperature"), ("max_tokens", "maxOutputTokens"),
                       ("top_p", "topP"), ("top_k", "topK"), ("stop", "stopSequences")]:
            if k in params:
                gen_config[gk] = params[k]
        if "response_format" in params:
            fmt = params["response_format"]
            if isinstance(fmt, dict) and fmt.get("type") == "json_object":
                gen_config["responseMimeType"] = "application/json"
        if gen_config:
            body["generationConfig"] = gen_config
        url = self._url(model, "generateContent")
        raw = self._request_json(url, body)
        return self.parse_response(raw)

    def stream(self, model, messages, tools, params):
        system_instruction, contents = self.build_request(messages)
        body = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = system_instruction
        if tools:
            gemini_tools = self._convert_tools(tools)
            if gemini_tools:
                body["tools"] = gemini_tools
        gen_config = {}
        for k, gk in [("temperature", "temperature"), ("max_tokens", "maxOutputTokens"),
                       ("top_p", "topP"), ("top_k", "topK"), ("stop", "stopSequences")]:
            if k in params:
                gen_config[gk] = params[k]
        if gen_config:
            body["generationConfig"] = gen_config
        url = self._url(model, "streamGenerateContent") + "&alt=sse"
        resp = self._request_stream(url, body)
        try:
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
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    candidates = obj.get("candidates", [])
                    if candidates:
                        cand = candidates[0]
                        parts = cand.get("content", {}).get("parts", [])
                        for part in parts:
                            if "text" in part:
                                yield {"type": "content_delta", "delta": {"type": "text", "text": part["text"]}}
                        reason = cand.get("finishReason", "")
                        if reason and reason != "FINISH_REASON_UNSPECIFIED":
                            reason_map = {"STOP": "stop", "MAX_TOKENS": "length", "SAFETY": "safety"}
                            finish = reason_map.get(reason, reason.lower())
                            usage_raw = obj.get("usageMetadata", {})
                            yield {
                                "type": "stream_end",
                                "finish_reason": finish,
                                "usage": {
                                    "input_tokens": usage_raw.get("promptTokenCount", 0),
                                    "output_tokens": usage_raw.get("candidatesTokenCount", 0),
                                    "total_tokens": usage_raw.get("totalTokenCount", 0),
                                },
                            }
        finally:
            resp.close()

    def embed(self, model, input_text):
        if isinstance(input_text, str):
            input_text = [input_text]
        url = "{}/models/{}:batchEmbedContents?key={}".format(self.BASE_URL, model, self._api_key)
        requests_list = []
        for text in input_text:
            requests_list.append({
                "model": "models/" + model,
                "content": {"parts": [{"text": text}]},
            })
        body = {"requests": requests_list}
        raw = self._request_json(url, body)
        embeddings = []
        for emb in raw.get("embeddings", []):
            embeddings.append(emb.get("values", []))
        return {
            "embeddings": embeddings,
            "usage": {"input_tokens": 0, "total_tokens": 0},
        }

    def image_gen(self, model, prompt, params):
        raise NotImplementedError("Google Gemini image generation via this provider is not supported. Use openai/dall-e-3 instead.")

    def image_analyze(self, model, image, prompt):
        """Gemini の vision 機能で画像解析"""
        if image.startswith("data:"):
            header, b64 = image.split(",", 1) if "," in image else ("", image)
            mime = "image/png"
            if "image/jpeg" in header:
                mime = "image/jpeg"
            elif "image/gif" in header:
                mime = "image/gif"
            elif "image/webp" in header:
                mime = "image/webp"
            inline = {"mime_type": mime, "data": b64}
        elif image.startswith("http"):
            contents = [{"role": "user", "parts": [
                {"file_data": {"file_uri": image, "mime_type": "image/png"}},
                {"text": prompt},
            ]}]
            url = self._url(model, "generateContent")
            raw = self._request_json(url, {"contents": contents})
            text = ""
            for cand in raw.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if "text" in part:
                        text += part["text"]
            return {"text": text}
        else:
            inline = {"mime_type": "image/png", "data": image}
        contents = [{"role": "user", "parts": [
            {"inline_data": inline},
            {"text": prompt},
        ]}]
        url = self._url(model, "generateContent")
        raw = self._request_json(url, {"contents": contents})
        text = ""
        for cand in raw.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                if "text" in part:
                    text += part["text"]
        return {"text": text}

    def transcribe(self, model, audio, params):
        raise NotImplementedError("Google Gemini does not support dedicated audio transcription via this endpoint. Use openai/whisper-1 instead.")

    def tts(self, model, text, voice):
        raise NotImplementedError("Google Gemini does not support text-to-speech via this endpoint. Use openai/tts-1 instead.")

    # ── tool conversion helper ──────────────────────────────────────────

    @staticmethod
    def _convert_tools(tools):
        """OpenAI 形式の tools → Gemini 形式に変換"""
        functions = []
        for tool in tools:
            if tool.get("type") == "function":
                fn = tool.get("function", {})
                gemini_fn = {"name": fn.get("name", ""), "description": fn.get("description", "")}
                parameters = fn.get("parameters")
                if parameters:
                    gemini_fn["parameters"] = parameters
                functions.append(gemini_fn)
        if functions:
            return [{"functionDeclarations": functions}]
        return []
