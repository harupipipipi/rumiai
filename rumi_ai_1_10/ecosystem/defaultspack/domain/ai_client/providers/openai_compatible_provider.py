from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .openai_provider import OpenAIProvider
from .profile_catalog import merge_curated_and_profiles, profile_dir_for


class OpenAICompatibleProvider(OpenAIProvider):
    """OpenAI-compatible provider with both legacy and manifest constructors."""

    provider_name = ""
    KNOWN_MODELS: List[Dict[str, Any]] = []
    curated_models: List[Dict[str, Any]] = []
    DISPLAY_NAME = "OpenAI Compatible"
    _SUPPRESS_DEFAULT_REASONING_PARAM = "_suppress_default_reasoning_effort"
    _CEREBRAS_REQUEST_DEFAULTS: Dict[str, Dict[str, Any]] = {
        "gpt-oss-120b": {
            "temperature": 1,
            "top_p": 1,
            "reasoning_effort": "high",
        },
        "llama3.1-8b": {
            "max_completion_tokens": 2048,
            "temperature": 0.2,
            "top_p": 1,
        },
    }
    _CEREBRAS_REASONING_MODELS = {"gpt-oss-120b", "zai-glm-4.7"}

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
        default_provider_id = str(provider_id or getattr(self.__class__, "provider_name", "") or "openai_compatible")
        self.provider_id = default_provider_id
        self.display_name = str(display_name or getattr(self.__class__, "display_name", "") or self.provider_id)
        self.DISPLAY_NAME = self.display_name
        self._api_key_envs = self._normalize_env_names(api_key_env)
        self._api_key_env = self._api_key_envs[0] if self._api_key_envs else ""
        self._base_url_env = str(base_url_env or "")
        self._default_base_url = str(default_base_url or self.BASE_URL).strip().rstrip("/")
        self._credential_required = bool(credential_required)
        self._extra_headers = dict(extra_headers or {})

        env_api_key = ""
        for env_name in self._api_key_envs:
            env_api_key = str(os.environ.get(env_name, "") or "").strip()
            if env_api_key:
                break
        env_base_url = os.environ.get(self._base_url_env, "") if self._base_url_env else ""

        self._api_key = str(api_key or env_api_key or "").strip()
        resolved_base_url = str(base_url or env_base_url or self._default_base_url or "").strip()
        self._base_url = resolved_base_url.rstrip("/") if resolved_base_url else ""
        self.BASE_URL = self._base_url
        seed_models = known_models
        if seed_models is None:
            seed_models = self.list_curated_models()
        self.KNOWN_MODELS = self._normalize_known_models(seed_models or [])

    @classmethod
    def profile_dir(cls):
        provider_name = str(getattr(cls, "provider_name", "") or "").strip()
        if not provider_name:
            return None
        return profile_dir_for(provider_name, __file__)

    @classmethod
    def list_curated_models(cls) -> List[Dict[str, Any]]:
        source = getattr(cls, "curated_models", None) or getattr(cls, "KNOWN_MODELS", [])
        return [dict(item) for item in source]

    @classmethod
    def from_manifest(
        cls,
        manifest: Dict[str, Any],
        *,
        model_manifests: Optional[List[Dict[str, Any]]] = None,
    ) -> "OpenAICompatibleProvider":
        provider_id = str(manifest.get("id", "")).strip() or "openai_compatible"
        known_models: List[Dict[str, Any]] = cls.list_curated_models()
        known_model_map = {
            str(item.get("id", "")).strip(): dict(item)
            for item in known_models
            if str(item.get("id", "")).strip()
        }
        for item in model_manifests or []:
            model_id = str(item.get("model_id", "")).strip()
            if not model_id:
                continue
            qualified_model_id = f"{provider_id}/{model_id}"
            known_model_map[qualified_model_id] = {
                "id": qualified_model_id,
                "model_id": model_id,
                "name": item.get("display_name", model_id),
                "display_name": item.get("display_name", model_id),
                "provider": provider_id,
                "provider_id": provider_id,
                "type": item.get("type", "chat"),
                "defaults": dict(item.get("defaults", {})),
                "metadata": dict(item.get("metadata", {})),
                "capabilities": dict(item.get("capabilities", {})),
                "context_window": item.get("context_window", item.get("max_context", item.get("max_context_tokens", 0))),
                "max_context": item.get("max_context", item.get("max_context_tokens", item.get("context_window", 0))),
                "max_context_tokens": item.get("max_context_tokens", item.get("max_context", item.get("context_window", 0))),
                "supports_thinking": bool(item.get("supports_thinking", False)),
                "thinking_levels": list(item.get("thinking_levels", [])),
                "default_thinking_level": item.get("default_thinking_level"),
            }
        known_models = list(known_model_map.values())
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
            api_key_env=manifest.get("api_key_env", ""),
            base_url_env=str(manifest.get("base_url_env", "")),
            default_base_url=str(
                manifest.get("default_base_url", "https://api.openai.com/v1")
            ),
            credential_required=bool(manifest.get("credential_required", True)),
            known_models=known_models,
            extra_headers=dict(manifest.get("headers", {})),
        )

    @staticmethod
    def _normalize_env_names(value: Any) -> List[str]:
        if isinstance(value, str):
            env_name = value.strip()
            return [env_name] if env_name else []
        if isinstance(value, (list, tuple, set)):
            normalized: List[str] = []
            for item in value:
                env_name = str(item or "").strip()
                if env_name and env_name not in normalized:
                    normalized.append(env_name)
            return normalized
        return []

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
            "model_id": model_id,
            "provider_id": self.provider_id,
            "provider": self.provider_id,
            "name": display_name,
            "display_name": display_name,
            "type": str(raw.get("type", "chat")),
        }
        defaults = dict(raw.get("defaults", {}))
        metadata = dict(raw.get("metadata", {}))
        capabilities = raw.get("capabilities", [])
        if defaults:
            normalized["defaults"] = defaults
        if metadata:
            normalized["metadata"] = metadata
        if capabilities:
            normalized["capabilities"] = capabilities
        for key in ("context_window", "max_context", "max_context_tokens", "supports_thinking", "thinking_levels", "default_thinking_level"):
            if key in raw:
                normalized[key] = raw[key]
        return normalized

    def _known_model_entry(self, model: str) -> Dict[str, Any]:
        model_ref = str(model or "").strip()
        model_id = model_ref.split("/", 1)[1] if "/" in model_ref and model_ref.startswith(f"{self.provider_id}/") else model_ref
        qualified = f"{self.provider_id}/{model_id}" if model_id else model_ref
        for item in self.KNOWN_MODELS:
            if not isinstance(item, dict):
                continue
            if model_ref in {
                str(item.get("id") or "").strip(),
                str(item.get("model_id") or "").strip(),
            }:
                return item
            if qualified and qualified == str(item.get("id") or "").strip():
                return item
        return {}

    @staticmethod
    def _capability_map(model_entry: Dict[str, Any]) -> Dict[str, Any]:
        raw = model_entry.get("capabilities") if isinstance(model_entry, dict) else {}
        if isinstance(raw, dict):
            capability_map = dict(raw)
        elif isinstance(raw, list):
            capability_map = {str(item): True for item in raw if str(item or "").strip()}
        else:
            capability_map = {}
        metadata = model_entry.get("metadata") if isinstance(model_entry, dict) else {}
        if isinstance(metadata, dict) and isinstance(metadata.get("capabilities"), dict):
            capability_map.update(metadata["capabilities"])
        return capability_map

    def _model_request_defaults(self, model: str, model_entry: Dict[str, Any]) -> Dict[str, Any]:
        metadata = model_entry.get("metadata") if isinstance(model_entry, dict) else {}
        for key in ("request_defaults", "default_request_params"):
            defaults = metadata.get(key) if isinstance(metadata, dict) else None
            if isinstance(defaults, dict):
                return dict(defaults)
        model_id = str(model or "").strip()
        if "/" in model_id and model_id.startswith(f"{self.provider_id}/"):
            model_id = model_id.split("/", 1)[1]
        if self.provider_id == "cerebras":
            return dict(self._CEREBRAS_REQUEST_DEFAULTS.get(model_id, {}))
        return {}

    def _model_supports_reasoning(self, model: str, model_entry: Dict[str, Any]) -> bool:
        capability_map = self._capability_map(model_entry)
        if "reasoning" in capability_map:
            return bool(capability_map.get("reasoning"))
        if "thinking" in capability_map:
            return bool(capability_map.get("thinking"))
        if isinstance(model_entry, dict) and "supports_thinking" in model_entry:
            return bool(model_entry.get("supports_thinking"))
        model_id = str(model or "").strip()
        if "/" in model_id and model_id.startswith(f"{self.provider_id}/"):
            model_id = model_id.split("/", 1)[1]
        return self.provider_id == "cerebras" and model_id in self._CEREBRAS_REASONING_MODELS

    @staticmethod
    def _translate_params(params):
        raw = dict(params or {})
        translated = OpenAIProvider._translate_params(raw)
        thinking_level = str(raw.get("thinking_level") or "").strip().lower()
        reasoning_effort = str(raw.get("reasoning_effort") or "").strip().lower()
        if thinking_level == "none" or reasoning_effort == "none":
            translated.pop("reasoning_effort", None)
            translated[OpenAICompatibleProvider._SUPPRESS_DEFAULT_REASONING_PARAM] = True
        return translated

    def _translate_cerebras_model_params(self, model: str, params: Dict[str, Any]) -> Dict[str, Any]:
        translated = dict(params or {})
        suppress_default_reasoning = bool(translated.pop(self._SUPPRESS_DEFAULT_REASONING_PARAM, False))
        if str(translated.get("reasoning_effort") or "").strip().lower() == "none":
            suppress_default_reasoning = True
            translated.pop("reasoning_effort", None)
        if "max_tokens" in translated:
            if "max_completion_tokens" not in translated:
                translated["max_completion_tokens"] = translated["max_tokens"]
            translated.pop("max_tokens", None)

        model_entry = self._known_model_entry(model)
        for key, value in self._model_request_defaults(model, model_entry).items():
            if key == "reasoning_effort" and suppress_default_reasoning:
                continue
            translated.setdefault(key, value)

        if not self._model_supports_reasoning(model, model_entry):
            translated.pop("reasoning_effort", None)
        return translated

    def _translate_model_params(self, model, params):
        if self.provider_id == "cerebras":
            return self._translate_cerebras_model_params(model, params)
        return super()._translate_model_params(model, params)

    def list_models(self):
        provider_name = str(self.provider_id or getattr(self, "provider_name", "") or "").strip()
        profile_dir = self.profile_dir()
        if provider_name and profile_dir is not None:
            return merge_curated_and_profiles(provider_name, self.KNOWN_MODELS, profile_dir)
        return [dict(model) for model in self.KNOWN_MODELS]

    def _headers(self, content_type="application/json"):
        headers = dict(self._extra_headers)
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        headers.setdefault("User-Agent", "RumiAI/1.0")
        headers.setdefault("Accept", "application/json")
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _ensure_runtime_config(self) -> None:
        if self._credential_required and not self._api_key:
            missing = ", ".join(self._api_key_envs) or "api_key"
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
