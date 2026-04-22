import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


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
            from domain.ai_client.providers import detect_available_providers
            available = detect_available_providers()
            for name, instance in available.items():
                self._providers[name] = instance
        except Exception:
            pass

    def _auto_register_rumi(self):
        """rumi プロバイダーを自動登録する（他のプロバイダーが1つ以上ある場合のみ）"""
        try:
            from domain.ai_client.providers import detect_rumi_provider
            rumi = detect_rumi_provider(self)
            if rumi is not None:
                self._providers["rumi"] = rumi
        except Exception:
            pass

    def register_provider(self, name, provider):
        """プロバイダーを動的に登録する"""
        self._providers[name] = provider

    def resolve_provider(self, model_str):
        """model文字列("provider/model" or "profile_name")からプロバイダーとモデル名を解決"""
        if "/" in model_str:
            provider_name, model_name = model_str.split("/", 1)
        else:
            profile = self._profiles.get(model_str)
            if profile:
                provider_name = profile.get("provider", "stub")
                model_name = profile.get("model", model_str)
            else:
                provider_name = "stub"
                model_name = model_str
                for pid, prov in self._providers.items():
                    if pid == "stub":
                        continue
                    candidates = []
                    if callable(getattr(prov, "list_models", None)):
                        try:
                            candidates = prov.list_models() or []
                        except Exception:
                            candidates = []
                    if not candidates and hasattr(prov, "KNOWN_MODELS"):
                        candidates = getattr(prov, "KNOWN_MODELS", []) or []
                    for candidate in candidates:
                        if isinstance(candidate, dict):
                            cid = str(candidate.get("id", ""))
                            if cid == model_str:
                                provider_name = pid
                                model_name = model_str
                                break
                            if "/" in cid and cid.split("/", 1)[1] == model_str:
                                provider_name = pid
                                model_name = cid.split("/", 1)[1]
                                break
                            if str(candidate.get("name", "")) == model_str:
                                provider_name = pid
                                model_name = cid.split("/", 1)[1] if "/" in cid else model_str
                                break
                    if provider_name != "stub":
                        break
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
        models = [
            {"id": "stub/default", "name": "Stub Default Model", "provider": "stub"},
            {"id": "stub/fast", "name": "Stub Fast Model", "provider": "stub"},
            {"id": "stub/large", "name": "Stub Large Model", "provider": "stub"},
        ]
        seen = {m["id"] for m in models}
        for pid, prov in self._providers.items():
            if pid == "stub":
                continue
            listed = []
            if callable(getattr(prov, "list_models", None)):
                try:
                    listed = prov.list_models() or []
                except Exception:
                    listed = []
            if not listed and hasattr(prov, "KNOWN_MODELS"):
                listed = getattr(prov, "KNOWN_MODELS", []) or []
            for item in listed:
                if isinstance(item, dict):
                    model_id = str(item.get("id", "")).strip()
                    if not model_id or model_id in seen:
                        continue
                    seen.add(model_id)
                    models.append(item)
                elif isinstance(item, str):
                    model_id = item if "/" in item else f"{pid}/{item}"
                    if model_id in seen:
                        continue
                    seen.add(model_id)
                    models.append({"id": model_id, "name": item, "provider": pid, "type": "chat"})
        if provider is not None:
            models = [m for m in models if m["provider"] == provider]
        return models

    def list_providers(self):
        providers = []
        for pid in self._providers:
            providers.append({"id": pid, "name": pid.capitalize(), "status": "available"})
        return providers

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
