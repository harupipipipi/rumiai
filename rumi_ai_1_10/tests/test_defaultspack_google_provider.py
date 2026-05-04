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
        self.assertEqual(
            provider.BASE_URL,
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )

    def test_google_provider_uses_openai_compatible_chat_endpoint(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        captured = {}

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key"}, clear=True):
            provider = GoogleProvider()

        def fake_request_json(path, body):
            captured["path"] = path
            captured["body"] = body
            return {
                "choices": [
                    {
                        "message": {"content": "hello from gemini"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 4,
                    "total_tokens": 7,
                },
                "model": "gemini-2.5-flash",
            }

        provider._request_json = fake_request_json
        response = provider.complete(
            "gemini-2.5-flash",
            [{"role": "user", "content": "hello"}],
            [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            {"temperature": 0.2, "thinking_level": "low"},
        )

        self.assertEqual(captured["path"], "/chat/completions")
        self.assertEqual(captured["body"]["model"], "gemini-2.5-flash")
        self.assertEqual(captured["body"]["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(captured["body"]["tools"][0]["function"]["name"], "lookup")
        self.assertEqual(captured["body"]["reasoning_effort"], "low")
        self.assertEqual(response["content"][0]["text"], "hello from gemini")

    def test_openai_provider_translates_generic_thinking_level(self):
        from domain.ai_client.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        captured = {}

        def fake_request_json(path, body):
            captured["path"] = path
            captured["body"] = body
            return {
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            }

        provider._request_json = fake_request_json
        provider.complete(
            "gpt-5.4",
            [{"role": "user", "content": "think"}],
            [],
            {"thinking_level": "xhigh"},
        )

        self.assertEqual(captured["path"], "/chat/completions")
        self.assertEqual(captured["body"]["reasoning_effort"], "high")
        self.assertNotIn("thinking_level", captured["body"])

    def test_anthropic_provider_translates_generic_thinking_level(self):
        from domain.ai_client.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
        captured = {}

        def fake_request_json(path, body):
            captured["path"] = path
            captured["body"] = body
            return {
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {},
            }

        provider._request_json = fake_request_json
        provider.complete(
            "claude-sonnet-4-6",
            [{"role": "user", "content": "think"}],
            [],
            {"thinking_level": "xhigh", "max_tokens": 4096},
        )

        self.assertEqual(captured["path"], "/v1/messages")
        self.assertEqual(captured["body"]["thinking"]["budget_tokens"], 16384)
        self.assertGreaterEqual(captured["body"]["max_tokens"], 17408)
        self.assertNotIn("thinking_level", captured["body"])

    def test_google_provider_key_can_be_saved_as_defaultspack_secret(self):
        from core_runtime.secrets_store import SecretsStore
        from domain.ai_client.api_key_store import (
            load_provider_api_keys_into_env,
            provider_has_api_key,
            set_provider_api_key,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets"
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}, clear=True):
                result = set_provider_api_key("google", "google-secret")
                store = SecretsStore(str(secrets_dir))

                self.assertTrue(result["success"])
                self.assertEqual(result["key"], "GOOGLE_API_KEY")
                self.assertTrue(provider_has_api_key("google"))
                self.assertTrue(store.has_secret("GOOGLE_API_KEY"))

                os.environ.pop("GOOGLE_API_KEY", None)
                loaded = load_provider_api_keys_into_env()

        self.assertTrue(loaded["google"])

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

    def test_google_catalog_includes_gemini_and_gemma_models(self):
        from domain.ai_client.providers import get_all_known_models

        model_ids = {item["id"] for item in get_all_known_models(provider_id="google")}

        self.assertIn("google/gemini-3-pro-preview", model_ids)
        self.assertIn("google/gemini-3-flash-preview", model_ids)
        self.assertIn("google/gemma-4-31b-it", model_ids)
        self.assertIn("google/gemma-3-27b-it", model_ids)
        self.assertIn("google/gemma-3n-e4b-it", model_ids)


if __name__ == "__main__":
    unittest.main()
