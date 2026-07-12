from .providers import (
    detect_available_providers,
    get_best_model_for_provider,
)
from ..extensions.runtime import get_extension_registry


class ProfileLoader:
    """プロファイル管理。extension manifest を優先して組み込みプロファイルを生成する。"""

    def __init__(self):
        self._profiles = {}
        self._load_builtin_defaults()

    @staticmethod
    def _registry_provider_order():
        try:
            registry = get_extension_registry(force_reload=True)
            return [item["id"] for item in registry.llm().providers(enabled_only=True)]
        except Exception:
            return []

    @staticmethod
    def _best_model_from_registry(provider_id, use_case):
        try:
            registry = get_extension_registry(force_reload=True)
            model = registry.llm().best_model(provider_id, use_case=use_case)
            if model is not None:
                return str(model.get("model_id", ""))
        except Exception:
            pass
        return ""

    @staticmethod
    def _embedding_model_from_registry(provider_id):
        try:
            registry = get_extension_registry(force_reload=True)
            for model in registry.llm().models(provider_id=provider_id, enabled_only=True):
                if str(model.get("type", "")).strip() == "embedding":
                    return str(model.get("model_id", ""))
        except Exception:
            pass
        return ""

    def _load_builtin_defaults(self):
        """利用可能 provider と extension metadata から builtin profile を組み立てる。"""
        available = detect_available_providers()
        provider_order = [pid for pid in self._registry_provider_order() if pid in available]
        if not provider_order:
            provider_order = [pid for pid in sorted(available.keys()) if pid != "stub"]

        # "default"
        for provider in provider_order:
            model = (
                self._best_model_from_registry(provider, "chat")
                or get_best_model_for_provider(provider, use_case="chat")
            )
            if model:
                self._profiles["default"] = {"provider": provider, "model": model}
                break
        if "default" not in self._profiles:
            self._profiles["default"] = {"provider": "stub", "model": "default"}

        # "fast"
        for provider in provider_order:
            model = self._best_model_from_registry(provider, "fast")
            if model:
                self._profiles["fast"] = {"provider": provider, "model": model}
                break
        if "fast" not in self._profiles:
            self._profiles["fast"] = dict(self._profiles["default"])

        # "large"
        for provider in provider_order:
            model = (
                self._best_model_from_registry(provider, "large")
                or self._best_model_from_registry(provider, "chat")
                or get_best_model_for_provider(provider, use_case="chat")
            )
            if model:
                self._profiles["large"] = {"provider": provider, "model": model}
                break
        if "large" not in self._profiles:
            self._profiles["large"] = dict(self._profiles["default"])

        # "embedding"
        for provider in provider_order:
            model = self._embedding_model_from_registry(provider)
            if model:
                self._profiles["embedding"] = {"provider": provider, "model": model}
                break
        if "embedding" not in self._profiles:
            self._profiles["embedding"] = dict(self._profiles["default"])

    def load(self, profile_id, profile_dict):
        """プロファイルを登録する"""
        self._profiles[profile_id] = profile_dict

    def load_from_dict(self, profiles_dict):
        """辞書から複数プロファイルを一括登録する。
        profiles_dict: {"profile_name": {"provider": "...", "model": "..."}, ...}
        """
        for pid, pdict in profiles_dict.items():
            self._profiles[pid] = pdict

    def get(self, profile_id):
        """プロファイルを取得する。存在しなければNone"""
        return self._profiles.get(profile_id)

    def list_profiles(self):
        """登録済みプロファイル一覧を返す"""
        return list(self._profiles.keys())

    def remove(self, profile_id):
        """プロファイルを削除する"""
        return self._profiles.pop(profile_id, None)

    def apply_to_client(self, client):
        """全プロファイルをAIClientに反映する"""
        for pid, pdict in self._profiles.items():
            client._profiles[pid] = pdict
