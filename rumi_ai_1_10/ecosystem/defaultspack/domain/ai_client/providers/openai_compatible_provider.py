from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .openai_provider import OpenAIProvider


class OpenAICompatibleProvider(OpenAIProvider):
    """OpenAI-compatible provider with both legacy and manifest constructors."""

    KNOWN_MODELS: List[Dict[str, Any]] = []
    DISPLAY_NAME = "OpenAI Compatible"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        known_models=None,
        *,
        provider_id: str = "",
        display_name: str = "",
        api_key_env: str = "",
        base_url_env: str = "",
        default_base_url: str = "",
        credential_required: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__()
        self.provider_id = str(provider_id or "openai_compatible")
        self.display_name = str(display_name or self.provider_id)
        self.DISPLAY_NAME = self.display_name
        self._api_key_env = str(api_key_env or "")
        self._base_url_env = str(base_url_env or "")
        self._default_base_url = str(default_base_url or self.BASE_URL).strip().rstrip("/")
        self._credential_required = bool(credential_required)
        self._extra_headers = dict(extra_headers or {})

        env_api_key = os.environ.get(self._api_key_env, "") if self._api_key_env else ""
        env_base_url = os.environ.get(self._base_url_env, "") if self._base_url_env else ""

        self._api_key = str(api_key or env_api_key or "").strip()
        resolved_base_url = str(base_url or env_base_url or self._default_base_url or "").strip()
        self._base_url = resolved_base_url.rstrip("/") if resolved_base_url else ""
        self.BASE_URL = self._base_url
        self.KNOWN_MODELS = self._normalize_known_models(known_models or [])

    @classmethod
    def from_manifest(
        cls,
        manifest: Dict[str, Any],
        *,
        model_manifests: Optional[List[Dict[str, Any]]] = None,
    ) -> "OpenAICompatibleProvider":
        provider_id = str(manifest.get("id", "")).strip() or "openai_compatible"
        known_models: List[Dict[str, Any]] = []
        for item in model_manifests or []:
            model_id = str(item.get("model_id", "")).strip()
            if not model_id:
                continue
            known_models.append(
                {
                    "id": f"{provider_id}/{model_id}",
                    "model_id": model_id,
                    "name": item.get("display_name", model_id),
                    "display_name": item.get("display_name", model_id),
                    "provider": provider_id,
                    "provider_id": provider_id,
                    "type": item.get("type", "chat"),
                    "defaults": dict(item.get("defaults", {})),
                    "metadata": dict(item.get("metadata", {})),
                }
            )
        if not known_models:
            known_models = list(manifest.get("models", []))
        if not known_models and manifest.get("default_model"):
            default_model = str(manifest.get("default_model")).strip()
            defaults = {"chat": True}
            for use_case, candidate in (manifest.get("default_model_for", {}) or {}).items():
                if str(candidate).strip() == default_model:
                    defaults[str(use_case)] = True
            known_models = [
                {
                    "id": f"{provider_id}/{default_model}",
                    "model_id": default_model,
                    "name": default_model,
                    "display_name": default_model,
                    "provider": provider_id,
                    "provider_id": provider_id,
                    "type": "chat",
                    "defaults": defaults,
                }
            ]
        return cls(
            provider_id=provider_id,
            display_name=str(manifest.get("display_name", provider_id)),
            api_key_env=str(manifest.get("api_key_env", "")),
            base_url_env=str(manifest.get("base_url_env", "")),
            default_base_url=str(
                manifest.get("default_base_url", "https://api.openai.com/v1")
            ),
            credential_required=bool(manifest.get("credential_required", True)),
            known_models=known_models,
            extra_headers=dict(manifest.get("headers", {})),
        )

    def _normalize_known_models(self, raw_models) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in list(raw_models or []):
            model = self._normalize_known_model(raw)
            if model is None:
                continue
            if model["id"] in seen:
                continue
            seen.add(model["id"])
            normalized.append(model)
        return normalized

    def _normalize_known_model(self, raw) -> Optional[Dict[str, Any]]:
        if isinstance(raw, str):
            model_id = raw.split("/", 1)[1] if "/" in raw else raw
            if not model_id:
                return None
            qualified_model_id = raw if "/" in raw else f"{self.provider_id}/{model_id}"
            return {
                "id": qualified_model_id,
                "provider": self.provider_id,
                "name": model_id,
                "type": "chat",
            }
        if not isinstance(raw, dict):
            return None
        qualified_model_id = str(raw.get("id", "")).strip()
        model_id = str(raw.get("model_id", "")).strip()
        if qualified_model_id and "/" in qualified_model_id and not model_id:
            _, model_id = qualified_model_id.split("/", 1)
        if not model_id:
            model_id = str(raw.get("model_name") or raw.get("name") or "").strip()
        if not model_id:
            return None
        if not qualified_model_id:
            qualified_model_id = f"{self.provider_id}/{model_id}"
        display_name = str(raw.get("display_name") or raw.get("name") or model_id)
        normalized = {
            "id": qualified_model_id,
            "provider": self.provider_id,
            "name": display_name,
            "type": str(raw.get("type", "chat")),
        }
        defaults = dict(raw.get("defaults", {}))
        metadata = dict(raw.get("metadata", {}))
        capabilities = list(raw.get("capabilities", []))
        if defaults:
            normalized["defaults"] = defaults
        if metadata:
            normalized["metadata"] = metadata
        if capabilities:
            normalized["capabilities"] = capabilities
        return normalized

    def list_models(self):
        return [dict(model) for model in self.KNOWN_MODELS]

    def _headers(self, content_type="application/json"):
        headers = dict(self._extra_headers)
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _ensure_runtime_config(self) -> None:
        if self._credential_required and not self._api_key:
            missing = self._api_key_env or "api_key"
            raise RuntimeError(
                f"{self.provider_id}: missing API key env ({missing})"
            )
        if not self._base_url:
            raise RuntimeError(f"{self.provider_id}: base URL is not configured")
        self.BASE_URL = self._base_url

    def _request_json(self, path, body):
        self._ensure_runtime_config()
        return super()._request_json(path, body)

    def _request_stream(self, path, body):
        self._ensure_runtime_config()
        return super()._request_stream(path, body)

    def _request_multipart(self, path, fields, files):
        self._ensure_runtime_config()
        return super()._request_multipart(path, fields, files)
