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


class TestDefaultspackCustomProviderRegistry(unittest.TestCase):
    def test_named_key_for_unknown_provider_auto_registers_custom_provider(self):
        from domain.ai_client.api_key_store import (
            list_custom_providers,
            provider_key_status,
            set_provider_api_key,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": tmpdir}, clear=True):
                result = set_provider_api_key(
                    "tavily",
                    "test-secret",
                    api_id="main",
                    name="main",
                    kind="custom",
                )
                self.assertTrue(result["success"], result)
                self.assertEqual(result["kind"], "custom")

                providers = list_custom_providers()
                provider_ids = [item["provider_id"] for item in providers]
                self.assertIn("tavily", provider_ids)
                tavily = next(item for item in providers if item["provider_id"] == "tavily")
                self.assertEqual(tavily["kind"], "custom")

                status = provider_key_status()
                tavily_status = next(row for row in status if row["provider_id"] == "tavily")
                self.assertFalse(tavily_status["builtin"])
                self.assertEqual(tavily_status["kind"], "custom")
                self.assertTrue(tavily_status["configured"])
                self.assertEqual(len(tavily_status["apis"]), 1)
                self.assertEqual(tavily_status["apis"][0]["kind"], "custom")

    def test_register_custom_provider_creates_entry_without_keys(self):
        from domain.ai_client.api_key_store import (
            delete_custom_provider,
            list_custom_providers,
            provider_key_status,
            register_custom_provider,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": tmpdir}, clear=True):
                result = register_custom_provider("searchapi", label="SearchAPI", kind="custom")
                self.assertTrue(result["success"])
                self.assertEqual(result["kind"], "custom")
                self.assertEqual(
                    [item["provider_id"] for item in list_custom_providers()],
                    ["searchapi"],
                )

                status = provider_key_status()
                row = next(row for row in status if row["provider_id"] == "searchapi")
                self.assertFalse(row["configured"])
                self.assertEqual(row["kind"], "custom")
                self.assertEqual(row["apis"], [])

                deleted = delete_custom_provider("searchapi")
                self.assertTrue(deleted["success"])
                self.assertEqual(list_custom_providers(), [])

    def test_register_custom_provider_rejects_blank_id(self):
        from domain.ai_client.api_key_store import register_custom_provider

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": tmpdir}, clear=True):
                result = register_custom_provider("   ")
                self.assertFalse(result["success"])

    def test_provider_key_status_includes_kind_and_builtin_for_known_providers(self):
        from domain.ai_client.api_key_store import provider_key_status

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"RUMI_DEFAULTSPACK_SECRETS_DIR": tmpdir}, clear=True):
                rows = provider_key_status()
        google = next(row for row in rows if row["provider_id"] == "google")
        self.assertTrue(google["builtin"])
        self.assertEqual(google["kind"], "llm")

    def test_provider_key_status_surfaces_env_backed_opencode_zen_key(self):
        from domain.ai_client.api_key_store import provider_key_status

        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "RUMI_DEFAULTSPACK_SECRETS_DIR": tmpdir,
                "OPENCODE_ZEN_API_KEY": "zen-secret",
            }
            with patch.dict(os.environ, env, clear=True):
                rows = provider_key_status()

        opencode = next(row for row in rows if row["provider_id"] == "opencode-zen")
        self.assertTrue(opencode["configured"])
        self.assertEqual(len(opencode["apis"]), 1)
        api = opencode["apis"][0]
        self.assertTrue(api["readonly"])
        self.assertEqual(api["source"], "env")
        self.assertEqual(api["api_id"], "environment")
        self.assertEqual(api["provider_id"], "opencode-zen")


if __name__ == "__main__":
    unittest.main()
