from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .openai_compatible_provider import OpenAICompatibleProvider


class LMStudioAPIError(RuntimeError):
    """Normalized LM Studio native API failure without credential leakage."""

    def __init__(self, message: str, *, kind: str = "unknown", status_code: int | None = None):
        super().__init__(message)
        self.kind = str(kind or "unknown")
        self.status_code = status_code


class LMStudioProvider(OpenAICompatibleProvider):
    """LM Studio provider with native installed-model discovery.

    Inference remains OpenAI-compatible under ``/v1``. Inventory and explicit
    model management use LM Studio's native ``/api/v1/models`` endpoints so the
    catalog reflects every model installed in the user's LM Studio environment.
    """

    provider_name = "lmstudio"
    display_name = "LM Studio"
    DEFAULT_INFERENCE_BASE_URL = "http://127.0.0.1:1234/v1"
    DEFAULT_MANAGEMENT_BASE_URL = "http://127.0.0.1:1234"
    NATIVE_MODEL_LIST_PATH = "/api/v1/models"
    NATIVE_MODEL_LOAD_PATH = "/api/v1/models/load"
    NATIVE_MODEL_UNLOAD_PATH = "/api/v1/models/unload"
    _LOAD_CONFIG_FIELDS = {
        "context_length",
        "eval_batch_size",
        "flash_attention",
        "num_experts",
        "offload_kv_cache_to_gpu",
        "echo_load_config",
    }

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        *,
        management_base_url: str = "",
        cache_ttl_seconds: int = 60,
    ) -> None:
        explicit_management_base = str(
            management_base_url
            or os.environ.get("LMSTUDIO_SERVER_URL", "")
            or os.environ.get("LMSTUDIO_MANAGEMENT_BASE_URL", "")
            or ""
        ).strip()
        self._management_base_url_override = explicit_management_base.rstrip("/")
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            provider_id=self.provider_name,
            display_name=self.display_name,
            api_key_env=("LMSTUDIO_API_TOKEN", "LM_API_TOKEN"),
            base_url_env="LMSTUDIO_BASE_URL",
            default_base_url=self.DEFAULT_INFERENCE_BASE_URL,
            credential_required=False,
            known_models=[],
            remote_model_discovery=False,
            remote_model_cache_ttl_seconds=cache_ttl_seconds,
        )

    def _management_base_url(self) -> str:
        if self._management_base_url_override:
            return self._management_base_url_override
        inference_base = str(self._base_url or self.DEFAULT_INFERENCE_BASE_URL).strip().rstrip("/")
        if inference_base.endswith("/v1"):
            return inference_base[:-3].rstrip("/")
        return inference_base or self.DEFAULT_MANAGEMENT_BASE_URL

    @staticmethod
    def _raw_model_id(model: str) -> str:
        value = str(model or "").strip()
        prefix = "lmstudio/"
        return value[len(prefix):] if value.startswith(prefix) else value

    def list_models(self) -> List[Dict[str, Any]]:
        return self._models_with_cache(force_refresh=False)

    def refresh_models(self) -> List[Dict[str, Any]]:
        """Explicitly refresh native inventory, retaining stale cache on failure."""
        return self._models_with_cache(force_refresh=True)

    def _models_with_cache(self, *, force_refresh: bool) -> List[Dict[str, Any]]:
        cache = self._load_remote_model_cache()
        now = int(time.time())
        if not force_refresh and cache and int(cache.get("expires_at") or 0) > now:
            cached = self._cached_native_models(cache.get("models"), stale=False)
            if cached or isinstance(cache.get("models"), list):
                return cached

        try:
            models = self._fetch_native_models()
        except LMStudioAPIError:
            models = None

        if models is not None:
            self._save_remote_model_cache(models, now=now)
            return [dict(model) for model in models]

        return self._cached_native_models(cache.get("models"), stale=True) if cache else []

    def _cached_native_models(self, raw_models: Any, *, stale: bool) -> List[Dict[str, Any]]:
        if not isinstance(raw_models, list):
            return []
        output: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_models:
            if not isinstance(raw, dict):
                continue
            provider_id = str(raw.get("provider_id") or raw.get("provider") or "").strip()
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            if provider_id != self.provider_name or metadata.get("source") != "lmstudio_native_api":
                continue
            model_id = str(raw.get("model_id") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            item = dict(raw)
            item_metadata = dict(metadata)
            item_metadata["catalog_cache_state"] = "stale" if stale else "fresh"
            item["metadata"] = item_metadata
            output.append(item)
        return output

    def _fetch_native_models(self) -> List[Dict[str, Any]]:
        payload = self._native_request_json(self.NATIVE_MODEL_LIST_PATH)
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise LMStudioAPIError(
                "LM Studio model-list response does not contain a models array",
                kind="schema_error",
            )
        return self._normalize_native_models(raw_models)

    def _normalize_native_models(self, raw_models: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_models, list):
            return []
        output: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_models:
            model = self._normalize_native_model(raw)
            if model is None:
                continue
            model_id = str(model["model_id"])
            if model_id in seen:
                continue
            seen.add(model_id)
            output.append(model)
        return output

    def _normalize_native_model(self, raw: Any) -> Dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        model_id = str(raw.get("key") or "").strip()
        native_type = str(raw.get("type") or "").strip().lower()
        if not model_id or native_type not in {"llm", "embedding"}:
            return None

        is_llm = native_type == "llm"
        native_capabilities = raw.get("capabilities") if isinstance(raw.get("capabilities"), dict) else {}
        reasoning = (
            native_capabilities.get("reasoning")
            if isinstance(native_capabilities.get("reasoning"), dict)
            else {}
        )
        reasoning_levels = [
            str(item).strip()
            for item in reasoning.get("allowed_options", [])
            if str(item or "").strip()
        ]
        default_reasoning = str(reasoning.get("default") or "").strip() or None
        thinking_supported = bool(reasoning_levels or default_reasoning)
        loaded_instances = raw.get("loaded_instances") if isinstance(raw.get("loaded_instances"), list) else []
        context_window = self._nonnegative_int(raw.get("max_context_length"))

        capability_map: Dict[str, Any] = {
            "text_input": True,
            "text_output": is_llm,
            "streaming": is_llm,
        }
        if is_llm:
            capability_map.update(
                {
                    "image_input": bool(native_capabilities.get("vision")),
                    "tool_calling": bool(native_capabilities.get("trained_for_tool_use")),
                    "thinking": thinking_supported,
                }
            )

        quantization = raw.get("quantization") if isinstance(raw.get("quantization"), dict) else None
        metadata: Dict[str, Any] = {
            "source": "lmstudio_native_api",
            "source_endpoint": self.NATIVE_MODEL_LIST_PATH,
            "capability_source": "lmstudio_native_api",
            "capability_confidence": "verified",
            "native_type": native_type,
            "publisher": raw.get("publisher"),
            "architecture": raw.get("architecture"),
            "quantization": dict(quantization) if quantization else None,
            "size_bytes": self._nonnegative_int(raw.get("size_bytes")),
            "params_string": raw.get("params_string"),
            "format": raw.get("format"),
            "loaded": bool(loaded_instances),
            "load_state": "loaded" if loaded_instances else "unloaded",
            "loaded_instances": [dict(item) for item in loaded_instances if isinstance(item, dict)],
            "description": raw.get("description"),
            "variants": [str(item) for item in raw.get("variants", []) if str(item or "").strip()]
            if isinstance(raw.get("variants"), list)
            else [],
            "selected_variant": raw.get("selected_variant"),
        }

        thinking = {
            "supported": thinking_supported,
            "levels": reasoning_levels,
            "default_level": default_reasoning,
            "provider_mapping": {level: level for level in reasoning_levels},
        }
        display_name = str(raw.get("display_name") or model_id)
        model: Dict[str, Any] = {
            "id": f"{self.provider_name}/{model_id}",
            "qualified_model_id": f"{self.provider_name}/{model_id}",
            "model_id": model_id,
            "provider_id": self.provider_name,
            "provider": self.provider_name,
            "display_name": display_name,
            "name": display_name,
            "type": "chat" if is_llm else "embedding",
            "context_window": context_window,
            "max_context": context_window,
            "max_context_tokens": context_window,
            "capabilities": capability_map,
            "thinking": thinking,
            "supports_thinking": thinking_supported,
            "thinking_levels": reasoning_levels,
            "default_thinking_level": default_reasoning,
            "metadata": metadata,
        }
        if is_llm and capability_map.get("tool_calling"):
            model["request_features"] = {"tool_choice": True}
        return model

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def probe(self) -> Dict[str, Any]:
        try:
            models = self._fetch_native_models()
        except LMStudioAPIError as exc:
            return {
                "connected": False,
                "status": exc.kind,
                "model_count": 0,
                "error": str(exc),
                "status_code": exc.status_code,
            }
        return {
            "connected": True,
            "status": "connected" if models else "connected_empty",
            "model_count": len(models),
            "loaded_model_count": sum(bool(model.get("metadata", {}).get("loaded")) for model in models),
            "error": "",
            "status_code": 200,
        }

    def load_model(self, model: str, **config: Any) -> Dict[str, Any]:
        model_id = self._raw_model_id(model)
        if not model_id:
            raise ValueError("LM Studio model id is required")
        payload: Dict[str, Any] = {"model": model_id}
        for key in self._LOAD_CONFIG_FIELDS:
            if key in config and config[key] is not None:
                payload[key] = config[key]
        return self._native_request_json(self.NATIVE_MODEL_LOAD_PATH, body=payload)

    def unload_model(self, instance_id: str) -> Dict[str, Any]:
        raw_instance_id = self._raw_model_id(instance_id)
        if not raw_instance_id:
            raise ValueError("LM Studio instance id is required")
        return self._native_request_json(
            self.NATIVE_MODEL_UNLOAD_PATH,
            body={"instance_id": raw_instance_id},
        )

    def _native_request_json(
        self,
        path: str,
        *,
        body: Dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Dict[str, Any]:
        base = self._management_base_url()
        if not base:
            raise LMStudioAPIError("LM Studio server URL is not configured", kind="configuration_error")
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
                    min(
                        30,
                        int(os.environ.get("RUMI_DEFAULTSPACK_LMSTUDIO_TIMEOUT", "6") or "6"),
                    ),
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
            raise LMStudioAPIError(
                f"LM Studio native API returned HTTP {exc.code}",
                kind=kind,
                status_code=exc.code,
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise LMStudioAPIError(
                "LM Studio native API is unreachable",
                kind="network_error",
            ) from None
        try:
            payload = json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError):
            raise LMStudioAPIError(
                "LM Studio native API returned invalid JSON",
                kind="schema_error",
            ) from None
        if not isinstance(payload, dict):
            raise LMStudioAPIError(
                "LM Studio native API returned a non-object response",
                kind="schema_error",
            )
        return payload
