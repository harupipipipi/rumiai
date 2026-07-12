"""Native hosted providers whose task contracts are not OpenAI chat compatible."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

from ..base_provider import BaseProvider


class HostedProviderError(RuntimeError):
    """Stable hosted-provider error with retry metadata."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


class NativeHostedProvider(BaseProvider):
    """Small JSON transport shared by official non-OpenAI hosted APIs."""

    provider_id = ""
    api_key_env = ""
    base_url_env = ""
    default_base_url = ""
    account_env = ""
    KNOWN_MODELS: list[dict[str, Any]] = []
    manifest_factory = True

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "",
        account_id: str = "",
        known_models: list[dict[str, Any]] | None = None,
        opener=urllib.request.urlopen,
    ) -> None:
        self._api_key = str(api_key or os.environ.get(self.api_key_env, "") or "").strip()
        resolved_base = base_url or os.environ.get(self.base_url_env, "") or self.default_base_url
        self._base_url = str(resolved_base or "").strip().rstrip("/")
        self._account_id = str(
            account_id or (os.environ.get(self.account_env, "") if self.account_env else "") or ""
        ).strip()
        self._opener = opener
        self._known_models = [dict(model) for model in (known_models or self.KNOWN_MODELS)]

    @classmethod
    def from_manifest(
        cls,
        manifest: dict[str, Any],
        *,
        model_manifests: list[dict[str, Any]] | None = None,
    ) -> "NativeHostedProvider":
        """Construct from the trusted component manifest and its unified models."""
        return cls(known_models=model_manifests)

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return dated snapshot models unless a provider supports explicit refresh."""
        return [dict(model) for model in self._known_models]

    def _model_id(self, model: str) -> str:
        value = str(model or "").strip()
        prefix = f"{self.provider_id}/"
        return value[len(prefix) :] if value.startswith(prefix) else value

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise HostedProviderError(
                "authentication_required", f"{self.provider_id} API key is not configured"
            )
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "RumiAI/1.0",
        }

    def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        if not self._base_url:
            raise HostedProviderError("configuration_error", "Provider base URL is not configured")
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._base_url + path,
            data=data,
            headers=headers or self._headers(),
            method=method,
        )
        try:
            with self._opener(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HostedProviderError(
                "transport_error", "Hosted provider request failed", retryable=True
            ) from exc
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HostedProviderError("invalid_response", "Provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise HostedProviderError("invalid_response", "Provider JSON must be an object")
        return payload

    def _open_stream(self, path: str, body: dict[str, Any]):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._base_url + path,
            data=data,
            headers=self._headers(),
            method="POST",
        )
        try:
            return self._opener(request, timeout=120.0)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HostedProviderError(
                "transport_error", "Hosted provider stream failed", retryable=True
            ) from exc

    @staticmethod
    def _sse_data(response) -> Iterable[dict[str, Any]]:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                item = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield item

    @staticmethod
    def _http_error(status: int) -> HostedProviderError:
        if status in {401, 403, 498}:
            return HostedProviderError(
                "authentication_failed", "Provider rejected credentials", status=status
            )
        if status == 429:
            return HostedProviderError(
                "rate_limited", "Provider rate limit exceeded", status=status, retryable=True
            )
        if status >= 500:
            return HostedProviderError(
                "provider_unavailable", "Provider is unavailable", status=status, retryable=True
            )
        return HostedProviderError(
            "invalid_request", "Provider rejected the request", status=status
        )


class CohereProvider(NativeHostedProvider):
    """Cohere v2 chat/embed/rerank adapter with paginated native inventory."""

    provider_id = "cohere"
    api_key_env = "COHERE_API_KEY"
    base_url_env = "COHERE_BASE_URL"
    default_base_url = "https://api.cohere.com"
    KNOWN_MODELS = [
        {"id": "cohere/command-a-plus-05-2026", "model_id": "command-a-plus-05-2026", "type": "chat"},
        {"id": "cohere/embed-v4.0", "model_id": "embed-v4.0", "type": "embedding"},
        {"id": "cohere/rerank-v4.0-pro", "model_id": "rerank-v4.0-pro", "type": "rerank"},
    ]

    def complete(self, model, messages, tools, params):
        body = {"model": self._model_id(model), "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        body.update({key: value for key, value in dict(params or {}).items() if key != "stream"})
        raw = self._request_json("POST", "/v2/chat", body)
        message = raw.get("message") if isinstance(raw.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        text = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        billed = usage.get("billed_units") if isinstance(usage.get("billed_units"), dict) else {}
        return {
            "content": [{"type": "text", "text": text}],
            "finish_reason": str(raw.get("finish_reason") or "COMPLETE").lower(),
            "usage": {
                "input_tokens": int(billed.get("input_tokens") or 0),
                "output_tokens": int(billed.get("output_tokens") or 0),
                "total_tokens": int(billed.get("input_tokens") or 0)
                + int(billed.get("output_tokens") or 0),
            },
            "tool_calls": message.get("tool_calls", []),
        }

    def stream(self, model, messages, tools, params):
        body = {"model": self._model_id(model), "messages": messages, "stream": True}
        if tools:
            body["tools"] = tools
        body.update({key: value for key, value in dict(params or {}).items() if key != "stream"})
        response = self._open_stream("/v2/chat", body)
        try:
            for event in self._sse_data(response):
                event_type = str(event.get("type") or "")
                delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
                message = delta.get("message") if isinstance(delta.get("message"), dict) else {}
                content = message.get("content") if isinstance(message.get("content"), dict) else {}
                text = content.get("text")
                if event_type == "content-delta" and text:
                    yield {"type": "content_delta", "delta": {"type": "text", "text": str(text)}}
                if event_type == "message-end":
                    yield {"type": "stream_end", "finish_reason": "stop", "usage": {}}
        finally:
            response.close()

    def embed(self, model, input_text):
        texts = [input_text] if isinstance(input_text, str) else list(input_text)
        raw = self._request_json(
            "POST",
            "/v2/embed",
            {"model": self._model_id(model), "texts": texts, "embedding_types": ["float"]},
        )
        embeddings = raw.get("embeddings") if isinstance(raw.get("embeddings"), dict) else {}
        return {"embeddings": embeddings.get("float", []), "usage": raw.get("meta", {})}

    def rerank(self, model: str, query: str, documents: list[Any], **params: Any):
        body = {"model": self._model_id(model), "query": query, "documents": documents, **params}
        raw = self._request_json("POST", "/v2/rerank", body)
        return {"results": raw.get("results", []), "usage": raw.get("meta", {})}

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh:
            return super().list_models()
        models: list[dict[str, Any]] = []
        token = ""
        while True:
            query = urllib.parse.urlencode({"page_size": 1000, **({"page_token": token} if token else {})})
            raw = self._request_json("GET", f"/v1/models?{query}")
            for item in raw.get("models", []) if isinstance(raw.get("models"), list) else []:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                endpoints = [str(value) for value in item.get("endpoints", [])]
                model_type = "rerank" if "rerank" in endpoints else "embedding" if "embed" in endpoints else "chat"
                model_id = str(item["name"])
                models.append({"id": f"cohere/{model_id}", "model_id": model_id, "type": model_type})
            token = str(raw.get("next_page_token") or "")
            if not token:
                break
        return models or super().list_models()


class CloudflareWorkersAIProvider(NativeHostedProvider):
    """Cloudflare Workers AI account-scoped model execution and inventory."""

    provider_id = "cloudflare-workers-ai"
    api_key_env = "CLOUDFLARE_API_TOKEN"
    base_url_env = "CLOUDFLARE_API_BASE_URL"
    account_env = "CLOUDFLARE_ACCOUNT_ID"
    default_base_url = "https://api.cloudflare.com/client/v4"

    def _account_path(self, suffix: str) -> str:
        if not self._account_id:
            raise HostedProviderError("configuration_error", "Cloudflare account ID is required")
        return f"/accounts/{urllib.parse.quote(self._account_id, safe='')}{suffix}"

    def run(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = urllib.parse.quote(self._model_id(model), safe="@/")
        raw = self._request_json("POST", self._account_path(f"/ai/run/{model_id}"), payload)
        if raw.get("success") is False:
            raise HostedProviderError("provider_error", "Workers AI execution failed")
        return raw.get("result", {}) if isinstance(raw.get("result"), dict) else {"output": raw.get("result")}

    def complete(self, model, messages, tools, params):
        payload = {"messages": messages, **dict(params or {})}
        if tools:
            payload["tools"] = tools
        result = self.run(model, payload)
        return {"content": [{"type": "text", "text": str(result.get("response") or "")}], "finish_reason": "stop", "usage": result.get("usage", {})}

    def embed(self, model, input_text):
        result = self.run(model, {"text": input_text})
        return {"embeddings": result.get("data", result.get("embeddings", []))}

    def rerank(self, model: str, query: str, documents: list[Any], **params: Any):
        return self.run(model, {"query": query, "contexts": documents, **params})

    def image_gen(self, model, prompt, params):
        return self.run(model, {"prompt": prompt, **dict(params or {})})

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh:
            return super().list_models()
        models: list[dict[str, Any]] = []
        page = 1
        while True:
            raw = self._request_json("GET", self._account_path(f"/ai/models/search?page={page}&per_page=100"))
            for item in raw.get("result", []) if isinstance(raw.get("result"), list) else []:
                if not isinstance(item, dict) or not (item.get("name") or item.get("id")):
                    continue
                model_id = str(item.get("name") or item.get("id"))
                task = str(item.get("task", {}).get("name") if isinstance(item.get("task"), dict) else item.get("task") or "unknown")
                models.append({"id": f"{self.provider_id}/{model_id}", "model_id": model_id, "type": task, "metadata": {"capability_provenance": "cloudflare_models_api"}})
            info = raw.get("result_info") if isinstance(raw.get("result_info"), dict) else {}
            total_pages = int(info.get("total_pages") or page)
            if page >= total_pages:
                break
            page += 1
        return models or super().list_models()


class JinaProvider(NativeHostedProvider):
    """Jina embeddings and reranking adapter."""

    provider_id = "jina-ai"
    api_key_env = "JINA_API_KEY"
    base_url_env = "JINA_BASE_URL"
    default_base_url = "https://api.jina.ai/v1"

    def embed(self, model, input_text):
        values = [input_text] if isinstance(input_text, str) else list(input_text)
        raw = self._request_json("POST", "/embeddings", {"model": self._model_id(model), "input": values})
        return {"embeddings": [item.get("embedding", []) for item in raw.get("data", [])], "usage": raw.get("usage", {})}

    def rerank(self, model: str, query: str, documents: list[Any], **params: Any):
        raw = self._request_json("POST", "/rerank", {"model": self._model_id(model), "query": query, "documents": documents, **params})
        return {"results": raw.get("results", []), "usage": raw.get("usage", {})}


class ReplicateProvider(NativeHostedProvider):
    """Replicate official-model prediction adapter."""

    provider_id = "replicate"
    api_key_env = "REPLICATE_API_TOKEN"
    base_url_env = "REPLICATE_BASE_URL"
    default_base_url = "https://api.replicate.com/v1"

    def predict(self, model: str, inputs: dict[str, Any], *, wait_seconds: int = 30):
        model_id = self._model_id(model)
        parts = model_id.split("/")
        if len(parts) != 2 or not all(parts):
            raise HostedProviderError("invalid_request", "Replicate model must be owner/name")
        path = "/models/{}/{}/predictions".format(
            urllib.parse.quote(parts[0], safe=""), urllib.parse.quote(parts[1], safe="")
        )
        headers = self._headers()
        headers["Prefer"] = f"wait={max(1, min(60, int(wait_seconds)))}"
        return self._request_json("POST", path, {"input": inputs}, headers=headers)

    def image_gen(self, model, prompt, params):
        result = self.predict(model, {"prompt": prompt, **dict(params or {})})
        output = result.get("output")
        images = output if isinstance(output, list) else [output] if output else []
        return {"images": images, "prediction": result}


class VoyageProvider(NativeHostedProvider):
    """Voyage embeddings and reranking adapter."""

    provider_id = "voyage-ai"
    api_key_env = "VOYAGE_API_KEY"
    base_url_env = "VOYAGE_BASE_URL"
    default_base_url = "https://api.voyageai.com/v1"

    def embed(self, model, input_text):
        raw = self._request_json("POST", "/embeddings", {"model": self._model_id(model), "input": input_text})
        return {"embeddings": [item.get("embedding", []) for item in raw.get("data", [])], "usage": raw.get("usage", {})}

    def rerank(self, model: str, query: str, documents: list[Any], **params: Any):
        raw = self._request_json("POST", "/rerank", {"model": self._model_id(model), "query": query, "documents": documents, **params})
        return {"results": raw.get("data", raw.get("results", [])), "usage": raw.get("usage", {})}
