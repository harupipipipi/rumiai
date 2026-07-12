from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List
from urllib.parse import urlsplit

from .openai_compatible_provider import OpenAICompatibleProvider


class OllamaAPIError(RuntimeError):
    """Normalized Ollama API failure without exposing credentials or proxy headers."""

    def __init__(self, message: str, *, kind: str = "unknown", status_code: int | None = None):
        super().__init__(message)
        self.kind = str(kind or "unknown")
        self.status_code = status_code


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama provider with native installed/running model discovery.

    Inference remains OpenAI-compatible under ``/v1``. Inventory is sourced from
    ``/api/tags``, model capabilities/details from ``/api/show``, and running
    state from ``/api/ps``. Discovery never pulls, creates, deletes, loads, or
    unloads a model.
    """

    provider_name = "ollama"
    display_name = "Ollama"
    DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:11434"
    DEFAULT_INFERENCE_BASE_URL = "http://127.0.0.1:11434/v1"
    TAGS_PATH = "/api/tags"
    SHOW_PATH = "/api/show"
    PS_PATH = "/api/ps"
    GENERATE_PATH = "/api/generate"
    _CONTEXT_KEY = re.compile(r"(?:^|\.)context_length$")
    _NUM_CTX_LINE = re.compile(r"^\s*num_ctx\s+([0-9]+)\s*$", re.MULTILINE)

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        *,
        server_base_url: str = "",
        cache_ttl_seconds: int = 60,
        detail_workers: int = 4,
    ) -> None:
        env_endpoint = str(
            os.environ.get("OLLAMA_BASE_URL", "")
            or os.environ.get("OLLAMA_HOST", "")
            or ""
        ).strip()
        explicit_inference = self._normalize_inference_url(base_url or env_endpoint)
        explicit_server = self._normalize_server_url(server_base_url or env_endpoint)
        self._server_base_url_override = explicit_server.rstrip("/")
        try:
            self._detail_workers = max(1, min(8, int(detail_workers)))
        except (TypeError, ValueError):
            self._detail_workers = 4
        super().__init__(
            api_key=api_key,
            base_url=explicit_inference,
            provider_id=self.provider_name,
            display_name=self.display_name,
            api_key_env="OLLAMA_API_KEY",
            base_url_env="",
            default_base_url=self.DEFAULT_INFERENCE_BASE_URL,
            credential_required=False,
            known_models=[],
            remote_model_discovery=False,
            remote_model_cache_ttl_seconds=cache_ttl_seconds,
        )

    @classmethod
    def _with_scheme(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "://" not in text:
            text = "http://" + text
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return text.rstrip("/")

    @classmethod
    def _normalize_server_url(cls, value: str) -> str:
        text = cls._with_scheme(value)
        if not text:
            return ""
        return text[:-3].rstrip("/") if text.endswith("/v1") else text

    @classmethod
    def _normalize_inference_url(cls, value: str) -> str:
        server = cls._normalize_server_url(value)
        return server + "/v1" if server else ""

    def _server_base_url(self) -> str:
        if self._server_base_url_override:
            return self._server_base_url_override
        inference = str(self._base_url or self.DEFAULT_INFERENCE_BASE_URL).strip().rstrip("/")
        if inference.endswith("/v1"):
            return inference[:-3].rstrip("/")
        return inference or self.DEFAULT_SERVER_BASE_URL

    @staticmethod
    def _raw_model_id(model: str) -> str:
        value = str(model or "").strip()
        prefix = "ollama/"
        return value[len(prefix):] if value.startswith(prefix) else value

    def list_models(self) -> List[Dict[str, Any]]:
        return self._models_with_cache(force_refresh=False)

    def refresh_models(self) -> List[Dict[str, Any]]:
        return self._models_with_cache(force_refresh=True)

    def _models_with_cache(self, *, force_refresh: bool) -> List[Dict[str, Any]]:
        cache = self._load_remote_model_cache()
        now = int(time.time())
        if not force_refresh and cache and int(cache.get("expires_at") or 0) > now:
            cached = self._cached_models(cache.get("models"), stale=False)
            if cached or isinstance(cache.get("models"), list):
                return cached

        previous = self._cached_models(cache.get("models"), stale=True) if cache else []
        try:
            models = self._fetch_native_inventory(previous)
        except OllamaAPIError:
            models = None

        if models is not None:
            self._save_remote_model_cache(models, now=now)
            return [deepcopy(model) for model in models]
        return previous

    def _cached_models(self, raw_models: Any, *, stale: bool) -> List[Dict[str, Any]]:
        if not isinstance(raw_models, list):
            return []
        output: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_models:
            if not isinstance(raw, dict):
                continue
            provider_id = str(raw.get("provider_id") or raw.get("provider") or "").strip()
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            if provider_id != self.provider_name or metadata.get("source") != "ollama_native_api":
                continue
            model_id = str(raw.get("model_id") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            item = deepcopy(raw)
            item_metadata = dict(metadata)
            item_metadata["catalog_cache_state"] = "stale" if stale else "fresh"
            item["metadata"] = item_metadata
            output.append(item)
        return output

    def _fetch_native_inventory(self, previous: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tags_payload = self._native_request_json(self.TAGS_PATH)
        raw_tags = tags_payload.get("models")
        if not isinstance(raw_tags, list):
            raise OllamaAPIError("Ollama /api/tags response has no models array", kind="schema_error")

        try:
            ps_payload = self._native_request_json(self.PS_PATH)
            raw_running = ps_payload.get("models") if isinstance(ps_payload, dict) else []
        except OllamaAPIError:
            raw_running = []
        running_map = self._running_model_map(raw_running)

        previous_map = {
            str(model.get("model_id") or ""): model
            for model in previous
            if isinstance(model, dict) and str(model.get("model_id") or "")
        }
        show_results = self._fetch_changed_model_details(raw_tags, previous_map)

        output: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw_tag in raw_tags:
            if not isinstance(raw_tag, dict):
                continue
            model_id = str(raw_tag.get("model") or raw_tag.get("name") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            digest = str(raw_tag.get("digest") or "").strip()
            previous_model = previous_map.get(model_id)
            previous_digest = str(
                ((previous_model or {}).get("metadata") or {}).get("detail_digest") or ""
            )
            if previous_model and digest and digest == previous_digest and model_id not in show_results:
                model = self._refresh_cached_model(previous_model, raw_tag, running_map.get(model_id))
            else:
                model = self._normalize_model(
                    raw_tag,
                    show_results.get(model_id),
                    running_map.get(model_id),
                )
            if model is not None:
                output.append(model)
        return output

    def _fetch_changed_model_details(
        self,
        raw_tags: List[Any],
        previous_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any] | None]:
        pending: List[str] = []
        for raw in raw_tags:
            if not isinstance(raw, dict):
                continue
            model_id = str(raw.get("model") or raw.get("name") or "").strip()
            if not model_id:
                continue
            digest = str(raw.get("digest") or "").strip()
            previous = previous_map.get(model_id) or {}
            previous_digest = str((previous.get("metadata") or {}).get("detail_digest") or "")
            if not previous or not digest or digest != previous_digest:
                pending.append(model_id)

        if not pending:
            return {}
        results: Dict[str, Dict[str, Any] | None] = {}
        with ThreadPoolExecutor(max_workers=min(self._detail_workers, len(pending))) as pool:
            futures = {pool.submit(self._show_model, model_id): model_id for model_id in pending}
            for future in as_completed(futures):
                model_id = futures[future]
                try:
                    results[model_id] = future.result()
                except Exception:
                    results[model_id] = None
        return results

    def _show_model(self, model_id: str) -> Dict[str, Any]:
        return self._native_request_json(self.SHOW_PATH, body={"model": model_id})

    @staticmethod
    def _running_model_map(raw_running: Any) -> Dict[str, Dict[str, Any]]:
        output: Dict[str, Dict[str, Any]] = {}
        if not isinstance(raw_running, list):
            return output
        for raw in raw_running:
            if not isinstance(raw, dict):
                continue
            model_id = str(raw.get("model") or raw.get("name") or "").strip()
            if model_id:
                output[model_id] = dict(raw)
        return output

    def _refresh_cached_model(
        self,
        previous: Dict[str, Any],
        raw_tag: Dict[str, Any],
        running: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        item = deepcopy(previous)
        metadata = dict(item.get("metadata") or {})
        self._overlay_tag_metadata(metadata, raw_tag)
        self._overlay_running_metadata(metadata, running)
        metadata["catalog_cache_state"] = "fresh"
        item["metadata"] = metadata
        return item

    def _normalize_model(
        self,
        raw_tag: Dict[str, Any],
        show: Dict[str, Any] | None,
        running: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        model_id = str(raw_tag.get("model") or raw_tag.get("name") or "").strip()
        if not model_id:
            return None
        show = show if isinstance(show, dict) else {}
        native_capabilities = {
            str(item).strip().lower()
            for item in show.get("capabilities", [])
            if str(item or "").strip()
        } if isinstance(show.get("capabilities"), list) else set()
        type_source = "ollama_show_capabilities"
        if "embedding" in native_capabilities and "completion" not in native_capabilities:
            model_type = "embedding"
        elif native_capabilities:
            model_type = "chat"
        elif "embed" in model_id.casefold():
            model_type = "embedding"
            type_source = "name_heuristic"
        else:
            model_type = "chat"
            type_source = "unknown_default"

        is_chat = model_type == "chat"
        capabilities: Dict[str, Any] = {
            "text_input": True,
            "text_output": is_chat,
            "streaming": is_chat,
        }
        if native_capabilities:
            capabilities.update(
                {
                    "image_input": "vision" in native_capabilities,
                    "tool_calling": "tools" in native_capabilities,
                    "thinking": "thinking" in native_capabilities,
                    "json_schema": is_chat,
                    "structured_output": is_chat,
                }
            )

        context_window = self._context_window(show)
        thinking_supported = bool(capabilities.get("thinking"))
        thinking_levels = ["low", "medium", "high", "max"] if thinking_supported else []
        details = self._merged_details(raw_tag, show)
        metadata: Dict[str, Any] = {
            "source": "ollama_native_api",
            "inventory_endpoint": self.TAGS_PATH,
            "detail_endpoint": self.SHOW_PATH,
            "running_endpoint": self.PS_PATH,
            "capability_source": type_source if not native_capabilities else "ollama_show_capabilities",
            "capability_confidence": "verified" if native_capabilities else "low",
            "type_source": type_source,
            "native_capabilities": sorted(native_capabilities),
            "detail_digest": str(raw_tag.get("digest") or ""),
            "template": show.get("template"),
            "parameters": show.get("parameters"),
            "license": show.get("license"),
            "model_info": dict(show.get("model_info")) if isinstance(show.get("model_info"), dict) else {},
            "default_context_length": self._parameter_num_ctx(show.get("parameters")),
        }
        metadata.update(details)
        self._overlay_tag_metadata(metadata, raw_tag)
        self._overlay_running_metadata(metadata, running)
        metadata["catalog_cache_state"] = "fresh"

        display_name = str(raw_tag.get("name") or raw_tag.get("model") or model_id)
        result: Dict[str, Any] = {
            "id": f"{self.provider_name}/{model_id}",
            "qualified_model_id": f"{self.provider_name}/{model_id}",
            "provider_id": self.provider_name,
            "provider": self.provider_name,
            "model_id": model_id,
            "display_name": display_name,
            "name": display_name,
            "type": model_type,
            "context_window": context_window,
            "max_context": context_window,
            "max_context_tokens": context_window,
            "capabilities": capabilities,
            "thinking": {
                "supported": thinking_supported,
                "levels": thinking_levels,
                "default_level": "medium" if thinking_supported else None,
                "provider_mapping": {level: level for level in thinking_levels},
            },
            "supports_thinking": thinking_supported,
            "thinking_levels": thinking_levels,
            "default_thinking_level": "medium" if thinking_supported else None,
            "metadata": metadata,
        }
        if is_chat:
            result["request_features"] = {
                "json_mode": True,
                "response_format": True,
                "tool_choice": bool(capabilities.get("tool_calling")),
            }
        return result

    @staticmethod
    def _merged_details(raw_tag: Dict[str, Any], show: Dict[str, Any]) -> Dict[str, Any]:
        tag_details = raw_tag.get("details") if isinstance(raw_tag.get("details"), dict) else {}
        show_details = show.get("details") if isinstance(show.get("details"), dict) else {}
        details = {**tag_details, **show_details}
        return {
            "format": details.get("format"),
            "family": details.get("family"),
            "families": list(details.get("families") or []) if isinstance(details.get("families"), list) else [],
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
            "parent_model": details.get("parent_model"),
        }

    @staticmethod
    def _overlay_tag_metadata(metadata: Dict[str, Any], raw_tag: Dict[str, Any]) -> None:
        metadata.update(
            {
                "digest": raw_tag.get("digest"),
                "modified_at": raw_tag.get("modified_at"),
                "size_bytes": OllamaProvider._nonnegative_int(raw_tag.get("size")),
            }
        )
        details = raw_tag.get("details") if isinstance(raw_tag.get("details"), dict) else {}
        for source, target in (
            ("format", "format"),
            ("family", "family"),
            ("parameter_size", "parameter_size"),
            ("quantization_level", "quantization_level"),
        ):
            if details.get(source) not in (None, ""):
                metadata[target] = details.get(source)
        if isinstance(details.get("families"), list):
            metadata["families"] = list(details["families"])

    @staticmethod
    def _overlay_running_metadata(metadata: Dict[str, Any], running: Dict[str, Any] | None) -> None:
        running = running if isinstance(running, dict) else {}
        metadata.update(
            {
                "running": bool(running),
                "load_state": "running" if running else "installed",
                "expires_at": running.get("expires_at"),
                "size_vram": OllamaProvider._nonnegative_int(running.get("size_vram")),
                "active_context_length": OllamaProvider._nonnegative_int(running.get("context_length")),
            }
        )

    @classmethod
    def _context_window(cls, show: Dict[str, Any]) -> int:
        model_info = show.get("model_info") if isinstance(show.get("model_info"), dict) else {}
        candidates: List[int] = []
        for key, value in model_info.items():
            if cls._CONTEXT_KEY.search(str(key)):
                parsed = cls._nonnegative_int(value)
                if parsed:
                    candidates.append(parsed)
        return max(candidates, default=0)

    @classmethod
    def _parameter_num_ctx(cls, parameters: Any) -> int:
        match = cls._NUM_CTX_LINE.search(str(parameters or ""))
        return cls._nonnegative_int(match.group(1)) if match else 0

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def probe(self) -> Dict[str, Any]:
        try:
            payload = self._native_request_json(self.TAGS_PATH)
        except OllamaAPIError as exc:
            return {
                "connected": False,
                "status": exc.kind,
                "model_count": 0,
                "error": str(exc),
                "status_code": exc.status_code,
            }
        models = payload.get("models") if isinstance(payload.get("models"), list) else []
        return {
            "connected": True,
            "status": "connected" if models else "connected_empty",
            "model_count": len(models),
            "error": "",
            "status_code": 200,
        }

    def unload_model(self, model: str) -> Dict[str, Any]:
        model_id = self._raw_model_id(model)
        if not model_id:
            raise ValueError("Ollama model id is required")
        return self._native_request_json(
            self.GENERATE_PATH,
            body={"model": model_id, "keep_alive": 0, "stream": False},
        )

    def _native_request_json(
        self,
        path: str,
        *,
        body: Dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Dict[str, Any]:
        base = self._server_base_url()
        if not base:
            raise OllamaAPIError("Ollama server URL is not configured", kind="configuration_error")
        url = base.rstrip("/") + "/" + str(path or "").lstrip("/")
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = self._headers(content_type="application/json" if data is not None else "")
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST" if data is not None else "GET",
        )
        timeout_seconds = timeout
        if timeout_seconds is None:
            try:
                timeout_seconds = max(
                    2,
                    min(30, int(os.environ.get("RUMI_DEFAULTSPACK_OLLAMA_TIMEOUT", "6") or "6")),
                )
            except (TypeError, ValueError):
                timeout_seconds = 6
        try:
            with urllib.request.urlopen(
                request,
                context=self._ssl_ctx,
                timeout=timeout_seconds,
            ) as response:
                raw_bytes = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            kind = "authentication_error" if exc.code in {401, 403} else "http_error"
            raise OllamaAPIError(
                f"Ollama native API returned HTTP {exc.code}",
                kind=kind,
                status_code=exc.code,
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise OllamaAPIError("Ollama native API is unreachable", kind="network_error") from None
        try:
            payload = json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise OllamaAPIError("Ollama native API returned invalid JSON", kind="schema_error") from None
        if not isinstance(payload, dict):
            raise OllamaAPIError("Ollama native API returned a non-object response", kind="schema_error")
        return payload
