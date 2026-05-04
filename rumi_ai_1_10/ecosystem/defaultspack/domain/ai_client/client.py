import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.ai_client.providers import (
    build_profile_catalog,
    detect_available_providers,
    detect_rumi_provider,
    get_all_known_models,
    get_provider_catalog,
    get_provider_catalog_map,
)


class AIClient:
    """AI Client - provider routing with profile and catalog compatibility."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._providers = {}
        self._profiles = {}
        self._register_default_provider()
        self._auto_register_providers()
        self._auto_register_rumi()

    def _register_default_provider(self):
        from domain.ai_client.providers.stub_provider import StubProvider

        self._providers["stub"] = StubProvider()

    def _auto_register_providers(self):
        """環境変数が設定されているプロバイダーを自動登録する。"""
        try:
            available = detect_available_providers()
            for name, instance in available.items():
                self._providers[name] = instance
        except Exception:
            pass

    def _auto_register_rumi(self):
        """rumi プロバイダーを自動登録する（他のプロバイダーが1つ以上ある場合のみ）。"""
        try:
            rumi = detect_rumi_provider(self)
            if rumi is not None:
                self._providers["rumi"] = rumi
        except Exception:
            pass

    def register_provider(self, name, provider):
        """プロバイダーを動的に登録する。"""
        self._providers[name] = provider

    def register_profile(self, name, profile=None, provider="", model="", **kwargs):
        """互換的にプロファイルを登録する。"""
        if isinstance(profile, dict):
            payload = dict(profile)
        else:
            payload = dict(kwargs)
            if profile is not None and not provider:
                provider = str(profile)
            if provider:
                payload["provider"] = provider
            if model:
                payload["model"] = model
        self._profiles[name] = payload

    def _active_provider_ids(self):
        return set(self._providers.keys())

    def _provider_model_candidates(self, provider_name):
        provider = self._providers.get(provider_name)
        if provider is None:
            return []
        listed = []
        if callable(getattr(provider, "list_models", None)):
            try:
                listed = provider.list_models() or []
            except Exception:
                listed = []
        if not listed and hasattr(provider, "KNOWN_MODELS"):
            listed = getattr(provider, "KNOWN_MODELS", []) or []
        return listed

    @staticmethod
    def _normalize_runtime_model(provider_id, provider_entry, raw):
        if isinstance(raw, str):
            model_id = raw.split("/", 1)[1] if "/" in raw else raw
            qualified_model_id = raw if "/" in raw else f"{provider_id}/{model_id}"
            display_name = model_id
            model_type = "chat"
            defaults = {}
            metadata = {}
            capabilities = []
            context_window = 0
            max_context = 0
            supports_thinking = False
            thinking_levels = []
        elif isinstance(raw, dict):
            qualified_model_id = str(raw.get("id", "")).strip()
            model_id = str(raw.get("model_id", "")).strip()
            if qualified_model_id and "/" in qualified_model_id and not model_id:
                _, model_id = qualified_model_id.split("/", 1)
            if not model_id:
                model_id = str(raw.get("model_name") or raw.get("name") or "").strip()
            if not model_id:
                return None
            if not qualified_model_id:
                qualified_model_id = f"{provider_id}/{model_id}"
            display_name = str(raw.get("display_name") or raw.get("name") or model_id)
            model_type = str(raw.get("type", "chat"))
            defaults = dict(raw.get("defaults", {}))
            metadata = dict(raw.get("metadata", {}))
            raw_capabilities = raw.get("capabilities", [])
            if isinstance(raw_capabilities, dict):
                capabilities = [key for key, value in raw_capabilities.items() if value]
                capability_map = dict(raw_capabilities)
            else:
                capabilities = list(raw_capabilities or [])
                capability_map = {str(key): True for key in capabilities}
            context_window = int(raw.get("context_window", raw.get("max_context", raw.get("max_context_tokens", 0))) or 0)
            max_context = int(raw.get("max_context", raw.get("max_context_tokens", context_window)) or 0)
            supports_thinking = bool(
                raw.get("supports_thinking")
                or capability_map.get("thinking")
                or capability_map.get("reasoning")
                or metadata.get("supports_thinking")
                or model_type == "reasoning"
            )
            thinking_levels = list(raw.get("thinking_levels") or metadata.get("thinking_levels") or [])
            if supports_thinking and not thinking_levels:
                thinking_levels = ["low", "medium", "high", "xhigh"]
        else:
            return None

        normalized = {
            "id": qualified_model_id,
            "qualified_model_id": qualified_model_id,
            "provider": provider_id,
            "provider_id": provider_id,
            "provider_display_name": provider_entry.get("display_name", provider_id),
            "model_id": model_id,
            "model_name": model_id,
            "name": display_name,
            "display_name": display_name,
            "type": model_type,
            "context_window": context_window,
            "max_context": max_context,
            "max_context_tokens": max_context,
            "supports_thinking": supports_thinking,
            "thinking_levels": thinking_levels,
            "default_thinking_level": raw.get("default_thinking_level", metadata.get("default_thinking_level", "medium" if supports_thinking else None)) if isinstance(raw, dict) else None,
            "capabilities": capabilities,
            "availability": dict(provider_entry.get("availability", {})),
            "supports_invoke": bool(
                provider_entry.get("availability", {}).get("supports_invoke", False)
            ),
            "defaults": defaults,
            "metadata": metadata,
        }
        normalized["metadata"].update(
            {
                "provider_model_key": qualified_model_id,
                "provider_display_name": provider_entry.get("display_name", provider_id),
                "provider_kind": provider_entry.get("kind", ""),
                "availability_status": provider_entry.get("availability", {}).get("status"),
                "max_context": max_context,
                "supports_thinking": supports_thinking,
                "thinking_levels": thinking_levels,
            }
        )
        return normalized

    def _runtime_model_matches(self, model_ref):
        active_provider_ids = self._active_provider_ids()
        catalog_map = get_provider_catalog_map(active_provider_ids=active_provider_ids)
        matches = []
        seen = set()
        for provider_id in active_provider_ids:
            provider_entry = catalog_map.get(provider_id, {})
            provider_entry.setdefault("display_name", provider_id)
            provider_entry.setdefault("availability", {"active": True, "supports_invoke": True})
            for raw in self._provider_model_candidates(provider_id):
                candidate = self._normalize_runtime_model(provider_id, provider_entry, raw)
                if candidate is None:
                    continue
                candidate_key = (candidate["provider_id"], candidate["model_id"])
                if candidate_key in seen:
                    continue
                seen.add(candidate_key)
                if model_ref in {
                    candidate["qualified_model_id"],
                    candidate["id"],
                    candidate["model_id"],
                    candidate["name"],
                    candidate["display_name"],
                }:
                    matches.append(candidate)
        return matches

    def resolve_provider(self, model_str):
        """model文字列("provider/model" or "profile_name")から解決する。"""
        if "/" in model_str:
            provider_name, model_name = model_str.split("/", 1)
        else:
            profile = self._profiles.get(model_str)
            if profile:
                provider_name = profile.get("provider") or profile.get("provider_id") or "stub"
                model_name = (
                    profile.get("model")
                    or profile.get("model_id")
                    or profile.get("qualified_model_id")
                    or model_str
                )
                if isinstance(model_name, str) and "/" in model_name:
                    resolved_provider, resolved_model = model_name.split("/", 1)
                    provider_name = provider_name or resolved_provider
                    model_name = resolved_model
            else:
                matches = []
                seen = set()
                for item in self.list_models():
                    item_key = (item.get("provider_id"), item.get("model_id"))
                    if item_key in seen:
                        continue
                    if model_str in {
                        item.get("model_id"),
                        item.get("qualified_model_id"),
                        item.get("id"),
                        item.get("name"),
                        item.get("display_name"),
                        item.get("disambiguated_name"),
                    }:
                        seen.add(item_key)
                        matches.append(item)
                for item in self._runtime_model_matches(model_str):
                    item_key = (item.get("provider_id"), item.get("model_id"))
                    if item_key not in seen:
                        seen.add(item_key)
                        matches.append(item)
                if len(matches) == 1:
                    provider_name = matches[0].get("provider_id", "stub")
                    model_name = matches[0].get("model_id", model_str)
                else:
                    provider_name = "stub"
                    model_name = model_str
        provider = self._providers.get(provider_name, self._providers["stub"])
        return provider, model_name

    def complete(self, model, messages, tools=None, params=None):
        provider, model_name = self.resolve_provider(model)
        if (
            provider.__class__.__name__ == "StubProvider"
            and isinstance(model, str)
            and "/" in model
            and not model.startswith("stub/")
        ):
            provider_name = model.split("/", 1)[0]
            raise RuntimeError(
                f"{provider_name}: provider is not configured. "
                "Set the provider API key before sending a message."
            )
        try:
            return provider.complete(model_name, messages, tools or [], params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def stream(self, model, messages, tools=None, params=None):
        provider, model_name = self.resolve_provider(model)
        if (
            provider.__class__.__name__ == "StubProvider"
            and isinstance(model, str)
            and "/" in model
            and not model.startswith("stub/")
        ):
            provider_name = model.split("/", 1)[0]
            raise RuntimeError(
                f"{provider_name}: provider is not configured. "
                "Set the provider API key before sending a message."
            )
        try:
            return provider.stream(model_name, messages, tools or [], params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def list_models(self, provider=None):
        """登録済みプロバイダーの既知モデル一覧を返す。"""
        active_provider_ids = self._active_provider_ids()
        if provider is not None and provider not in active_provider_ids:
            return []

        models = get_all_known_models(
            provider_id=provider,
            active_provider_ids=active_provider_ids,
        )
        models = [
            model
            for model in models
            if model.get("provider_id") in active_provider_ids
        ]

        catalog_map = get_provider_catalog_map(active_provider_ids=active_provider_ids)
        seen = {model.get("qualified_model_id") for model in models}
        provider_ids = [provider] if provider else sorted(active_provider_ids)
        for provider_id in provider_ids:
            provider_entry = catalog_map.get(provider_id)
            if provider_entry is None:
                continue
            for raw in self._provider_model_candidates(provider_id):
                candidate = self._normalize_runtime_model(provider_id, provider_entry, raw)
                if candidate is None:
                    continue
                qualified_model_id = candidate.get("qualified_model_id")
                if qualified_model_id in seen:
                    continue
                seen.add(qualified_model_id)
                models.append(candidate)
        return models

    def list_providers(self):
        active_provider_ids = self._active_provider_ids()
        catalog = get_provider_catalog(active_provider_ids=active_provider_ids)
        active = [
            provider
            for provider in catalog
            if provider.get("provider_id") in active_provider_ids
        ]
        known_ids = {provider.get("provider_id") for provider in active}
        for provider_id in sorted(active_provider_ids - known_ids):
            provider = self._providers.get(provider_id)
            active.append(
                {
                    "id": provider_id,
                    "provider_id": provider_id,
                    "name": getattr(provider, "display_name", provider_id.capitalize()),
                    "display_name": getattr(provider, "display_name", provider_id.capitalize()),
                    "kind": "custom",
                    "description": "",
                    "env_vars": [],
                    "base_url_envs": [],
                    "default_model": "",
                    "capabilities": [],
                    "availability": {
                        "active": True,
                        "available": True,
                        "configured": True,
                        "catalog_only": False,
                        "supports_invoke": callable(getattr(provider, "complete", None)),
                        "status": "active",
                    },
                    "metadata": {
                        "catalog_only": False,
                        "supports_invoke": callable(getattr(provider, "complete", None)),
                        "default_base_url": "",
                    },
                }
            )
        return active

    def list_profiles(self, provider=None):
        active_provider_ids = self._active_provider_ids()
        profiles = build_profile_catalog(
            active_provider_ids=active_provider_ids,
            custom_profiles=self._profiles,
        )
        profiles = [
            profile
            for profile in profiles
            if not profile.get("provider_id") or profile.get("provider_id") in active_provider_ids
        ]
        if provider is not None:
            profiles = [profile for profile in profiles if profile.get("provider_id") == provider]
        return profiles

    def embed(self, model, input_text):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.embed(model_name, input_text)
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def image_gen(self, model, prompt, params=None):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.image_gen(model_name, prompt, params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def image_analyze(self, model, image, prompt):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.image_analyze(model_name, image, prompt)
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def transcribe(self, model, audio, params=None):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.transcribe(model_name, audio, params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def tts(self, model, text, voice=None):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.tts(model_name, text, voice)
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None
