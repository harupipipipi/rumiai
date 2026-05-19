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


class TestDefaultspackProviderExpansion(unittest.TestCase):
    def test_detect_available_providers_accepts_new_openai_compatible_provider_keys(self):
        from domain.ai_client.providers import detect_available_providers

        with patch.dict(
            os.environ,
            {"XAI_API_KEY": "x-key", "GROQ_API_KEY": "g-key", "DEEPSEEK_API_KEY": "d-key"},
            clear=True,
        ):
            providers = detect_available_providers()

        self.assertIn("xai", providers)
        self.assertIn("groq", providers)
        self.assertIn("deepseek", providers)

    def test_generic_provider_loads_profile_models_from_user_data(self):
        from domain.ai_client.providers.provider_catalog import XaiProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "profiles"
            target_dir = profile_dir / "grok-code-fast-1"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "profile.json").write_text(
                json.dumps(
                    {
                        "provider_id": "xai",
                        "model_id": "grok-code-fast-1",
                        "display_name": "Grok Code Fast 1",
                        "metadata": {"type": "chat"},
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(XaiProvider, "profile_dir", return_value=profile_dir):
                provider = XaiProvider()
                model_ids = {item["id"] for item in provider.list_models()}

        self.assertIn("xai/grok-code-fast-1", model_ids)
        self.assertIn("xai/grok-4", model_ids)

    def test_get_all_known_models_includes_generic_provider_catalog(self):
        from domain.ai_client.providers import get_all_known_models

        model_ids = {item["id"] for item in get_all_known_models()}

        self.assertIn("groq/llama-3.3-70b-versatile", model_ids)
        self.assertIn("together/meta-llama/Llama-3.3-70B-Instruct-Turbo", model_ids)
        self.assertIn("mistral/mistral-large-latest", model_ids)

    def test_ai_client_lists_auto_registered_generic_provider_models(self):
        from domain.ai_client.client import AIClient

        AIClient._instance = None
        with patch.dict(
            os.environ,
            {"MISTRAL_API_KEY": "m-key", "RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS": "1"},
            clear=True,
        ):
            client = AIClient()

        try:
            models = client.list_models(provider="mistral")
        finally:
            AIClient._instance = None

        model_ids = {item["id"] for item in models}
        self.assertIn("mistral/mistral-large-latest", model_ids)
        self.assertIn("mistral/mistral-embed", model_ids)

    def test_ai_client_lists_only_supported_openrouter_model(self):
        from domain.ai_client.client import AIClient

        AIClient._instance = None
        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "or-key", "RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS": "1"},
            clear=True,
        ):
            client = AIClient()

        try:
            models = client.list_models(provider="openrouter")
            provider, model_name = client.resolve_provider("openrouter/tencent/hy3-preview:free")
        finally:
            AIClient._instance = None

        self.assertEqual({item["id"] for item in models}, {"openrouter/tencent/hy3-preview:free"})
        self.assertEqual(model_name, "tencent/hy3-preview:free")
        self.assertEqual(getattr(provider, "provider_id", ""), "openrouter")

    def test_gitlawb_opengateway_includes_mimo_v2_omni(self):
        from domain.ai_client.client import AIClient
        from domain.ai_client.providers.gitlawb_opengateway_provider import GitlawbOpengatewayProvider

        AIClient._instance = None
        with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS": "1"}, clear=True):
            client = AIClient()

        try:
            models = client.list_models(provider="gitlawb-opengateway")
            provider, model_name = client.resolve_provider("gitlawb-opengateway/mimo-v2-omni")
        finally:
            AIClient._instance = None

        model = next(item for item in models if item["id"] == "gitlawb-opengateway/mimo-v2-omni")
        self.assertEqual(model_name, "mimo-v2-omni")
        self.assertEqual(getattr(provider, "provider_id", ""), "gitlawb-opengateway")
        self.assertIn("vision", model.get("capabilities", []))
        self.assertEqual(GitlawbOpengatewayProvider()._headers()["Authorization"], "Bearer anything")

    def test_ai_client_does_not_stub_unconfigured_openrouter_completion(self):
        from domain.ai_client.client import AIClient

        AIClient._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": tmpdir}, clear=True):
                client = AIClient()

            try:
                with self.assertRaisesRegex(RuntimeError, "openrouter: provider is not configured"):
                    client.complete(
                        "openrouter/tencent/hy3-preview:free",
                        [{"role": "user", "content": "hello"}],
                        [],
                        {},
                    )
            finally:
                AIClient._instance = None

    def test_api_routes_read_models_before_legacy_apis(self):
        from domain.ai_client.client import AIClient

        AIClient._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "frontend_settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "models": {"model_api_routes": "google/gemini-test: google/models-main"},
                        "apis": {"model_api_routes": "google/gemini-test: google/apis-legacy"},
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                client = AIClient()

            try:
                with patch.object(client, "_settings_path", return_value=settings_path):
                    routes = client._api_routes()
            finally:
                AIClient._instance = None

        self.assertEqual(routes["google/gemini-test"], ["google/models-main"])

    def test_structured_api_routes_take_priority_over_text_routes(self):
        from domain.ai_client.client import AIClient

        AIClient._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "frontend_settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "models": {
                            "api_routes": [
                                {"model": "google/gemini-test", "apis": ["google/main", "google/backup"]}
                            ],
                            "model_api_routes": "google/gemini-test: google/legacy",
                        }
                    }
                ),
                encoding="utf-8",
            )
            client = AIClient()

            try:
                with patch.object(client, "_settings_path", return_value=settings_path):
                    routes = client._api_routes()
            finally:
                AIClient._instance = None

        self.assertEqual(routes["google/gemini-test"], ["google/main", "google/backup"])

    def test_named_api_metadata_persists_api_bound_model_data(self):
        from domain.ai_client.api_key_store import provider_api_metadata, provider_named_api_keys, set_provider_api_key

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": tmpdir}, clear=True):
                set_provider_api_key(
                    "longcat",
                    "secret",
                    api_id="work",
                    name="work",
                    base_url="https://api.longcat.chat/openai/v1",
                    allowed_models=["LongCat-Flash-Chat"],
                    default_model="LongCat-Flash-Chat",
                    notes="fast longcat route",
                    quota_label="paid",
                )

                metadata = provider_api_metadata("longcat", "work")
                keys = provider_named_api_keys("longcat")

        self.assertEqual(metadata["base_url"], "https://api.longcat.chat/openai/v1")
        self.assertEqual(metadata["allowed_models"], ["LongCat-Flash-Chat"])
        self.assertEqual(metadata["default_model"], "LongCat-Flash-Chat")
        self.assertEqual(keys[0]["quota_label"], "paid")

    def test_composite_fallback_chain_uses_next_model_on_quota_error(self):
        from domain.ai_client.client import AIClient

        class FailingProvider:
            def complete(self, model, messages, tools, params):
                raise RuntimeError("429 rate limit")

        class SuccessProvider:
            def complete(self, model, messages, tools, params):
                return {"content": [{"type": "text", "text": f"ok:{model}"}], "finish_reason": "stop"}

        AIClient._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "frontend_settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "models": {
                            "composite_models": [
                                {
                                    "id": "combo/default",
                                    "mode": "fallback_chain",
                                    "members": ["fail/model-a", "win/model-b"],
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            client = AIClient()
            client.register_provider("fail", FailingProvider())
            client.register_provider("win", SuccessProvider())

            try:
                with patch.object(client, "_settings_path", return_value=settings_path):
                    response = client.complete("combo/default", [{"role": "user", "content": "hello"}])
            finally:
                AIClient._instance = None

        self.assertEqual(response["content"][0]["text"], "ok:model-b")

    def test_composite_fallback_chain_honors_member_conditions(self):
        from domain.ai_client.client import AIClient

        class EchoProvider:
            def complete(self, model, messages, tools, params):
                return {"content": [{"type": "text", "text": f"ok:{model}"}], "finish_reason": "stop"}

        AIClient._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "frontend_settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "models": {
                            "composite_models": [
                                {
                                    "id": "combo/conditional",
                                    "mode": "fallback_chain",
                                    "members": [
                                        {"model": "plain/text", "conditions": {"has_images": False}},
                                        {"model": "vision/omni", "conditions": {"has_images": True}},
                                    ],
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            client = AIClient()
            client.register_provider("plain", EchoProvider())
            client.register_provider("vision", EchoProvider())

            try:
                with patch.object(client, "_settings_path", return_value=settings_path):
                    response = client.complete(
                        "combo/conditional",
                        [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "describe this"},
                                    {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                                ],
                            }
                        ],
                    )
            finally:
                AIClient._instance = None

        self.assertEqual(response["content"][0]["text"], "ok:omni")

    def test_composite_fallback_chain_uses_fallback_on_error_kind(self):
        from domain.ai_client.client import AIClient

        class TimeoutProvider:
            def complete(self, model, messages, tools, params):
                raise RuntimeError("request timed out")

        class SuccessProvider:
            def complete(self, model, messages, tools, params):
                return {"content": [{"type": "text", "text": f"ok:{model}"}], "finish_reason": "stop"}

        AIClient._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "frontend_settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "models": {
                            "composite_models": [
                                {
                                    "id": "combo/error-routing",
                                    "mode": "fallback_chain",
                                    "members": [
                                        {"model": "slow/model-a", "fallback_on": ["timeout"]},
                                        "win/model-b",
                                    ],
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            client = AIClient()
            client.register_provider("slow", TimeoutProvider())
            client.register_provider("win", SuccessProvider())

            try:
                with patch.object(client, "_settings_path", return_value=settings_path):
                    response = client.complete("combo/error-routing", [{"role": "user", "content": "hello"}])
            finally:
                AIClient._instance = None

        self.assertEqual(response["content"][0]["text"], "ok:model-b")

    def test_composite_ensemble_merges_member_answers_without_synthesizer(self):
        from domain.ai_client.client import AIClient

        class EchoProvider:
            def __init__(self, prefix):
                self.prefix = prefix

            def complete(self, model, messages, tools, params):
                return {"content": [{"type": "text", "text": f"{self.prefix}:{model}"}], "finish_reason": "stop"}

        AIClient._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "frontend_settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "models": {
                            "composite_models": [
                                {
                                    "id": "combo/ensemble",
                                    "mode": "ensemble",
                                    "members": ["a/one", "b/two"],
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            client = AIClient()
            client.register_provider("a", EchoProvider("a"))
            client.register_provider("b", EchoProvider("b"))

            try:
                with patch.object(client, "_settings_path", return_value=settings_path):
                    response = client.complete("combo/ensemble", [{"role": "user", "content": "hello"}])
            finally:
                AIClient._instance = None

        text = response["content"][0]["text"]
        self.assertIn("[a/one]", text)
        self.assertIn("[b/two]", text)
        self.assertEqual(set(response["metadata"]["ensemble"]["members"]), {"a/one", "b/two"})

    def test_api_route_stream_keeps_named_key_until_generator_is_consumed(self):
        from domain.ai_client import client as client_module
        from domain.ai_client.client import AIClient

        class StreamingProvider:
            def __init__(self):
                self._api_key = "original-secret"
                self.keys_seen = []

            def stream(self, model, messages, tools, params):
                def chunks():
                    self.keys_seen.append(self._api_key)
                    yield {"type": "delta", "model": model, "api_key": self._api_key}

                return chunks()

        provider = StreamingProvider()
        AIClient._instance = None
        with patch.dict(os.environ, {}, clear=True):
            client = AIClient()
        client.register_provider("google", provider)

        try:
            with (
                patch.object(client, "_api_routes", return_value={"google/gemini-test": ["google/backup"]}),
                patch.object(client_module, "read_provider_api_key", return_value="named-route-secret"),
            ):
                stream = client.stream("google/gemini-test", [{"role": "user", "content": "hello"}])

                self.assertEqual(provider._api_key, "original-secret")
                chunks = list(stream)

            self.assertEqual(provider.keys_seen, ["named-route-secret"])
            self.assertEqual(chunks[0]["api_key"], "named-route-secret")
            self.assertEqual(provider._api_key, "original-secret")
        finally:
            AIClient._instance = None


if __name__ == "__main__":
    unittest.main()
