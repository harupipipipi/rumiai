import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.ai_client.providers import (
    build_profile_catalog,
    detect_available_providers,
    detect_rumi_provider,
    get_all_known_models,
    get_provider_catalog,
)


class AIClient:
    """AI Client — プロバイダーへの委譲とプロファイル解決"""
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
        """環境変数が設定されているプロバイダーを自動登録する"""
        try:
            available = detect_available_providers()
            for name, instance in available.items():
                self._providers[name] = instance
        except Exception:
            pass

    def _auto_register_rumi(self):
        """rumi プロバイダーを自動登録する（他のプロバイダーが1つ以上ある場合のみ）"""
        try:
            rumi = detect_rumi_provider(self)
            if rumi is not None:
                self._providers["rumi"] = rumi
        except Exception:
            pass

    def register_provider(self, name, provider):
        """プロバイダーを動的に登録する"""
        self._providers[name] = provider

    def register_profile(self, name, profile):
        """プロファイルエイリアスを登録する。"""
        self._profiles[name] = dict(profile or {})

    def _active_provider_ids(self):
        return set(self._providers.keys())

    def resolve_provider(self, model_str):
        """model文字列("provider/model" or "profile_name")からプロバイダーとモデル名を解決"""
        if "/" in model_str:
            provider_name, model_name = model_str.split("/", 1)
        else:
            profile = self._profiles.get(model_str)
            if profile:
                provider_name = profile.get("provider") or profile.get("provider_id") or "stub"
                model_name = profile.get("model") or profile.get("model_id") or model_str
            else:
                matches = [
                    item
                    for item in self.list_models()
                    if item.get("model_id") == model_str or item.get("qualified_model_id") == model_str
                ]
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
        try:
            return provider.complete(model_name, messages, tools or [], params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def stream(self, model, messages, tools=None, params=None):
        provider, model_name = self.resolve_provider(model)
        try:
            return provider.stream(model_name, messages, tools or [], params or {})
        except NotImplementedError as e:
            raise RuntimeError(str(e)) from None

    def list_models(self, provider=None):
        """登録済みプロバイダーの既知モデル一覧を返す"""
        active_provider_ids = self._active_provider_ids()
        if provider is not None and provider not in active_provider_ids:
            return []
        models = get_all_known_models(
            provider_id=provider,
            active_provider_ids=active_provider_ids,
        )
        return [
            model for model in models
            if model.get("provider_id") in active_provider_ids
        ]

    def list_providers(self):
        active_provider_ids = self._active_provider_ids()
        return [
            provider for provider in get_provider_catalog(active_provider_ids=active_provider_ids)
            if provider.get("provider_id") in active_provider_ids
        ]

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
