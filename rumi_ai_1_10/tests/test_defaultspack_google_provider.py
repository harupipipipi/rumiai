from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _DynamicProvider:
    KNOWN_MODELS = [
        {"id": "dynamic/stale", "name": "Stale", "provider": "dynamic", "type": "chat"},
    ]

    def list_models(self):
        return [
            {"id": "dynamic/fresh", "name": "Fresh", "provider": "dynamic", "type": "chat"},
        ]


class TestDefaultspackGoogleProvider(unittest.TestCase):
    def test_detect_available_providers_accepts_gemini_api_key(self):
        from domain.ai_client.providers import detect_available_providers

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
            providers = detect_available_providers()

        self.assertIn("google", providers)

    def test_google_provider_prefers_google_api_key_when_both_are_set(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        with patch.dict(
            os.environ,
            {"GOOGLE_API_KEY": "google-key", "GEMINI_API_KEY": "gemini-key"},
            clear=True,
        ):
            provider = GoogleProvider()

        self.assertEqual(provider._api_key, "google-key")

    def test_google_provider_loads_profile_models_from_user_data(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "profiles"
            target_dir = profile_dir / "gemma-3-12b-it"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "profile.json").write_text(
                json.dumps(
                    {
                        "provider_id": "google",
                        "model_id": "gemma-3-12b-it",
                        "display_name": "Gemma 3 12B IT",
                        "metadata": {"type": "chat"},
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(GoogleProvider, "PROFILE_DIR", profile_dir):
                provider = GoogleProvider()
                model_ids = {item["id"] for item in provider.list_models()}

        self.assertIn("google/gemma-3-12b-it", model_ids)
        self.assertIn("google/gemini-2.5-pro", model_ids)

    def test_ai_client_prefers_provider_list_models(self):
        from domain.ai_client.client import AIClient

        AIClient._instance = None
        with patch.object(AIClient, "_auto_register_providers", lambda self: None), patch.object(
            AIClient, "_auto_register_rumi", lambda self: None
        ):
            client = AIClient()

        try:
            client.register_provider("dynamic", _DynamicProvider())
            models = client.list_models(provider="dynamic")
        finally:
            AIClient._instance = None

        self.assertEqual(
            models,
            [{"id": "dynamic/fresh", "name": "Fresh", "provider": "dynamic", "type": "chat"}],
        )

    def test_ai_client_loads_default_profile_from_environment(self):
        from domain.ai_client.client import AIClient

        AIClient._instance = None
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            client = AIClient()
            profile = client._profiles.get("default")
            provider, model = client.resolve_provider("default")

        try:
            self.assertEqual(profile, {"provider": "openai", "model": "gpt-4o"})
            self.assertEqual(provider.__class__.__name__, "OpenAIProvider")
            self.assertEqual(model, "gpt-4o")
        finally:
            AIClient._instance = None

    def test_chat_store_uses_real_default_model_when_provider_is_available(self):
        from domain.chat.store import ChatStore

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            store = ChatStore()
            conv = store.create_conversation()

        self.assertEqual(conv["model"], "openai/gpt-4o")


if __name__ == "__main__":
    unittest.main()
