import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class ProfileLoader:
    """プロファイル管理。デフォルトプロファイル組み込み + インメモリdict管理。"""

    # 環境変数で最初に見つかったプロバイダーの最高性能モデルを default に割り当てる
    _PROVIDER_PRIORITY = [
        (("OPENAI_API_KEY",), "openai", "gpt-4o"),
        (("ANTHROPIC_API_KEY",), "anthropic", "claude-sonnet-4-0"),
        (("GOOGLE_API_KEY", "GEMINI_API_KEY"), "google", "gemini-2.5-pro"),
    ]

    _BUILTIN_PROFILES = {
        "fast": [
            (("OPENAI_API_KEY",), "openai", "gpt-4o-mini"),
            (("GOOGLE_API_KEY", "GEMINI_API_KEY"), "google", "gemini-2.5-flash"),
            (("ANTHROPIC_API_KEY",), "anthropic", "claude-3-5-haiku-20241022"),
        ],
        "large": [
            (("OPENAI_API_KEY",), "openai", "gpt-4o"),
            (("ANTHROPIC_API_KEY",), "anthropic", "claude-sonnet-4-0"),
            (("GOOGLE_API_KEY", "GEMINI_API_KEY"), "google", "gemini-2.5-pro"),
        ],
        "embedding": [
            (("OPENAI_API_KEY",), "openai", "text-embedding-3-small"),
            (("GOOGLE_API_KEY", "GEMINI_API_KEY"), "google", "text-embedding-004"),
        ],
    }

    def __init__(self):
        self._profiles = {}
        self._load_builtin_defaults()

    def _load_builtin_defaults(self):
        """環境変数に基づいてデフォルトプロファイルを組み込み定義する"""
        from domain.ai_client.providers import ensure_provider_env_loaded, env_group_configured

        ensure_provider_env_loaded()

        # "default" プロファイル
        for env_vars, provider, model in self._PROVIDER_PRIORITY:
            if env_group_configured(env_vars):
                self._profiles["default"] = {"provider": provider, "model": model}
                break
        if "default" not in self._profiles:
            self._profiles["default"] = {"provider": "stub", "model": "default"}

        # "fast", "large", "embedding" プロファイル
        for profile_name, candidates in self._BUILTIN_PROFILES.items():
            for env_vars, provider, model in candidates:
                if env_group_configured(env_vars):
                    self._profiles[profile_name] = {"provider": provider, "model": model}
                    break
            if profile_name not in self._profiles:
                self._profiles[profile_name] = {"provider": "stub", "model": "default"}

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
