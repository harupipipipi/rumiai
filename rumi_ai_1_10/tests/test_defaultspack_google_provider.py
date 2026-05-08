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
            {
                "temperature": 0.2,
                "thinking_level": "low",
                "tool_choice": "auto",
                "stream_options": {"include_usage": False},
                "extra_body": {"google": {"thinking_config": {"include_thoughts": True}}},
            },
        )

        self.assertEqual(captured["path"], "/chat/completions")
        self.assertEqual(captured["body"]["model"], "gemini-2.5-flash")
        self.assertEqual(captured["body"]["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(captured["body"]["tools"][0]["function"]["name"], "lookup")
        self.assertEqual(captured["body"]["reasoning_effort"], "low")
        self.assertEqual(captured["body"]["tool_choice"], "auto")
        self.assertEqual(captured["body"]["stream_options"], {"include_usage": False})
        self.assertEqual(captured["body"]["google"]["thinking_config"]["include_thoughts"], True)
        self.assertEqual(response["content"][0]["text"], "hello from gemini")

    def test_google_provider_autofixes_native_base_url_to_openai_compatible_path(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "gemini-key",
                "GOOGLE_BASE_URL": "https://generativelanguage.googleapis.com/v1beta",
            },
            clear=True,
        ):
            provider = GoogleProvider()

        self.assertEqual(
            provider.BASE_URL,
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )

    def test_google_provider_streams_openai_compatible_tool_call_deltas(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        captured = {}

        class FakeStream:
            def __init__(self):
                self._chunks = [
                    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"lookup","arguments":"{\\"q\\""}}]},"finish_reason":null}]}\n\n',
                    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":\\"rumi\\"}"}}]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}\n\n',
                    b"data: [DONE]\n\n",
                ]

            def read(self, _size=4096):
                return self._chunks.pop(0) if self._chunks else b""

            def close(self):
                captured["closed"] = True

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key"}, clear=True):
            provider = GoogleProvider()

        def fake_request_stream(path, body):
            captured["path"] = path
            captured["body"] = body
            return FakeStream()

        provider._request_stream = fake_request_stream
        chunks = list(provider.stream("gemini-2.5-flash", [{"role": "user", "content": "search"}], [], {}))

        self.assertEqual(captured["path"], "/chat/completions")
        self.assertEqual(captured["body"]["stream_options"], {"include_usage": True})
        self.assertEqual(chunks[0], {"type": "tool_call_start", "id": "call_1", "name": "lookup"})
        self.assertEqual(chunks[1]["type"], "tool_call_delta")
        self.assertEqual(chunks[1]["arguments_chunk"], '{"q"')
        self.assertEqual(chunks[2]["arguments_chunk"], ':"rumi"}')
        self.assertEqual(chunks[3], {"type": "tool_call_end", "id": "call_1", "name": "lookup"})
        self.assertEqual(chunks[-1]["type"], "stream_end")

    def test_google_provider_strips_rumi_tool_metadata_before_request(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        captured = {}

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key"}, clear=True):
            provider = GoogleProvider()

        def fake_request_json(path, body):
            captured["body"] = body
            return {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {},
            }

        provider._request_json = fake_request_json
        provider.complete(
            "gemini-2.5-flash",
            [{"role": "user", "content": "calculate"}],
            [
                {
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "description": "Calculate an expression",
                        "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}},
                    },
                    "metadata": {"source": "extension"},
                    "category": "math",
                    "action_type": "read",
                    "write_action": False,
                }
            ],
            {},
        )

        tool = captured["body"]["tools"][0]
        self.assertEqual(set(tool.keys()), {"type", "function"})
        self.assertEqual(tool["function"]["name"], "calculator")
        self.assertNotIn("metadata", tool)
        self.assertNotIn("category", tool)
        self.assertNotIn("action_type", tool)
        self.assertNotIn("write_action", tool)

    def test_google_provider_moves_inline_thoughts_to_metadata(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        provider = GoogleProvider()
        response = provider.parse_response(
            {
                "choices": [
                    {
                        "message": {"content": "<thought>private plan</thought> visible answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            }
        )

        self.assertEqual(response["content"][0]["text"], "visible answer")
        self.assertEqual(response["metadata"]["thinking"]["transcript"], "private plan")
        self.assertNotIn("<thought>", response["content"][0]["text"])

    def test_google_provider_preserves_multimodal_content_blocks(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        provider = GoogleProvider()
        messages = provider.build_request(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what is in this image?"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
                        },
                    ],
                }
            ]
        )

        self.assertEqual(messages[0]["content"][0]["text"], "what is in this image?")
        self.assertEqual(
            messages[0]["content"][1]["image_url"]["url"],
            "data:image/png;base64,iVBORw0KGgo=",
        )

    def test_google_provider_hides_inline_thought_tags(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        response = GoogleProvider().parse_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": "<thought>private reasoning</thought>赤",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            }
        )

        self.assertEqual(response["content"][0]["text"], "赤")

    def test_google_provider_caps_gemini_thinking_levels(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        self.assertEqual(
            GoogleProvider._translate_params({"thinking_level": "xhigh"}, "gemini-3-pro-preview"),
            {"reasoning_effort": "high"},
        )
        self.assertEqual(
            GoogleProvider._translate_params({"thinking_level": "medium"}, "gemini-3-pro-preview"),
            {"reasoning_effort": "high"},
        )
        self.assertEqual(
            GoogleProvider._translate_params({"thinking_level": "none"}, "gemini-3-flash-preview"),
            {"reasoning_effort": "minimal"},
        )
        self.assertEqual(
            GoogleProvider._translate_params({"thinking_level": "none"}, "gemini-2.5-pro"),
            {},
        )
        self.assertEqual(
            GoogleProvider._translate_params({"thinking_level": "xhigh"}, "gemma-4-31b-it"),
            {"reasoning_effort": "high"},
        )

    def test_google_provider_uses_native_generative_api_for_gemma_4(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        captured = {}

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key"}, clear=True):
            provider = GoogleProvider()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "candidates": [
                            {
                                "content": {"parts": [{"text": "gemma answer"}]},
                                "finishReason": "STOP",
                            }
                        ],
                        "usageMetadata": {
                            "promptTokenCount": 2,
                            "candidatesTokenCount": 3,
                            "totalTokenCount": 5,
                        },
                    }
                ).encode("utf-8")

        def fake_native_request_json(model, body, stream=False):
            captured["model"] = model
            captured["body"] = body
            captured["stream"] = stream
            return FakeResponse()

        provider._native_request_json = fake_native_request_json
        response = provider.complete(
            "gemma-4-31b-it",
            [{"role": "user", "content": "hello"}],
            [{"function": {"name": "google_search"}}],
            {"thinking_level": "high"},
        )

        self.assertEqual(captured["model"], "gemma-4-31b-it")
        self.assertFalse(captured["stream"])
        self.assertEqual(captured["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"], "HIGH")
        self.assertEqual(captured["body"]["tools"], [{"googleSearch": {}}])
        self.assertEqual(response["content"][0]["text"], "gemma answer")
        self.assertEqual(response["usage"]["total_tokens"], 5)

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

    def test_named_provider_api_key_can_be_saved_and_listed(self):
        from core_runtime.secrets_store import SecretsStore
        from domain.ai_client.api_key_store import (
            delete_provider_api_key,
            named_provider_secret_key,
            provider_has_api_key,
            provider_named_api_keys,
            rename_provider_api_key,
            read_provider_api_key,
            set_provider_api_key,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets"
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir)}, clear=True):
                result = set_provider_api_key(
                    "google",
                    "google-main-secret",
                    api_id="main",
                    name="Main",
                )
                key = named_provider_secret_key("google", api_id="main")
                store = SecretsStore(str(secrets_dir))

                self.assertTrue(result["success"])
                self.assertEqual(result["key"], key)
                self.assertTrue(store.has_secret(key))
                self.assertTrue(provider_has_api_key("google"))
                self.assertEqual(read_provider_api_key("google", "main"), "google-main-secret")
                listed = provider_named_api_keys("google")
                self.assertEqual(listed[0]["api_id"], "main")
                self.assertEqual(listed[0]["name"], "Main")
                self.assertEqual(listed[0]["label"], "google:main:***")

                renamed = rename_provider_api_key("google", "main", "work")
                self.assertTrue(renamed["success"])
                self.assertEqual(provider_named_api_keys("google")[0]["api_id"], "work")
                self.assertEqual(read_provider_api_key("google", "work"), "google-main-secret")

                deleted = delete_provider_api_key("google", "work")
                self.assertTrue(deleted["success"])
                self.assertFalse(provider_has_api_key("google"))

    def test_named_google_key_registers_runtime_without_cloud_flag(self):
        from domain.ai_client.api_key_store import set_provider_api_key
        from domain.ai_client.client import AIClient

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets"
            env = {
                "RUMI_DEFAULTSPACK_SECRETS_DIR": str(secrets_dir),
                "RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS": "",
            }
            with patch.dict(os.environ, env, clear=True):
                set_provider_api_key("google", "google-main-secret", api_id="main", name="Main")
                AIClient._instance = None
                client = AIClient()

                self.assertIn("google", client._active_provider_ids())

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
        self.assertIn("google/gemini-2.5-flash-lite", model_ids)
        self.assertNotIn("google/gemini-2.0-flash-lite", model_ids)
        self.assertIn("google/gemma-4-31b-it", model_ids)
        self.assertIn("google/gemma-4-26b-a4b-it", model_ids)
        self.assertIn("google/gemma-3-27b-it", model_ids)
        self.assertIn("google/gemma-3n-e4b-it", model_ids)

    def test_google_catalog_does_not_expose_xhigh_for_gemini(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        profiles = {item["id"]: item for item in GoogleProvider().list_models()}

        self.assertNotIn("xhigh", profiles["google/gemini-2.5-pro"]["thinking_levels"])
        self.assertEqual(profiles["google/gemini-3-pro-preview"]["thinking_levels"], ["low", "high"])
        self.assertEqual(profiles["google/gemma-4-26b-a4b-it"]["thinking_levels"], ["none", "high"])

    def test_google_catalog_marks_gemma_4_as_tool_and_vision_capable(self):
        from domain.ai_client.providers.google_provider import GoogleProvider

        profiles = {item["id"]: item for item in GoogleProvider().list_models()}

        self.assertIn("tool_calls", profiles["google/gemma-4-31b-it"]["capabilities"])
        self.assertIn("vision", profiles["google/gemma-4-31b-it"]["capabilities"])
        self.assertIn("tool_calls", profiles["google/gemma-4-26b-a4b-it"]["capabilities"])
        self.assertIn("vision", profiles["google/gemma-4-26b-a4b-it"]["capabilities"])


if __name__ == "__main__":
    unittest.main()
