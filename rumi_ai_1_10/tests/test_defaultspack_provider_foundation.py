from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestDefaultspackProviderCatalog(unittest.TestCase):
    def test_provider_catalog_contains_major_and_local_entries(self):
        from ecosystem.defaultspack.backend.ai_client.provider_catalog import (
            list_provider_catalog,
        )

        providers = {item["provider_id"]: item for item in list_provider_catalog()}
        self.assertIn("openai", providers)
        self.assertIn("anthropic", providers)
        self.assertIn("ollama", providers)
        self.assertTrue(providers["ollama"]["local"])

    def test_model_catalog_exposes_cross_provider_identity_metadata(self):
        from ecosystem.defaultspack.backend.ai_client.provider_catalog import (
            list_model_catalog,
        )

        models = list_model_catalog(provider="openai")
        self.assertTrue(models)
        sample = next(model for model in models if model["model_id"] == "gpt-4o")
        self.assertEqual(sample["canonical_model_id"], "gpt-4o")
        self.assertEqual(sample["same_model_across_providers_key"], "gpt-4o")
        self.assertEqual(sample["qualified_model_id"], "openai/gpt-4o")

    def test_detect_available_providers_registers_openai_compatible_gateways(self):
        from ecosystem.defaultspack.domain.ai_client.providers import (
            detect_available_providers,
        )

        env = {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_BASE_URL": "https://openrouter.example/v1",
        }
        with patch.dict(os.environ, env, clear=False):
            providers = detect_available_providers()
        self.assertIn("openrouter", providers)

    def test_provider_catalog_marks_google_configured_when_only_gemini_key_is_set(self):
        from ecosystem.defaultspack.backend.ai_client.provider_catalog import (
            list_provider_catalog,
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            providers = {item["provider_id"]: item for item in list_provider_catalog()}

        google = providers["google"]
        self.assertIn("GEMINI_API_KEY", google["env_vars"])
        self.assertEqual(google["configured_envs"], ["GEMINI_API_KEY"])
        self.assertTrue(google["configured"])
        self.assertTrue(google["availability"]["configured"])


class TestDefaultspackToolPermissionPolicy(unittest.TestCase):
    def test_permission_policy_round_trip_and_checker_behavior(self):
        from ecosystem.defaultspack.backend.tool.permission_policy import (
            ToolPermissionPolicyStore,
        )
        from ecosystem.defaultspack.domain.tool.permission_checker import (
            PermissionChecker,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tool_permission_policy.json"
            manager = ToolPermissionPolicyStore(path=path)
            stored = manager.update({"tools": {"dangerous_tool": "deny"}})
            self.assertEqual(stored["tools"]["dangerous_tool"], "deny")

            with patch(
                "ecosystem.defaultspack.domain.tool.permission_checker.get_tool_permission_policy_manager",
                return_value=manager,
            ):
                checker = PermissionChecker()
                self.assertFalse(checker.check("dangerous_tool", {}))

            manager.update({"tools": {"ask_tool": "ask"}})
            with patch(
                "ecosystem.defaultspack.domain.tool.permission_checker.get_tool_permission_policy_manager",
                return_value=manager,
            ):
                checker = PermissionChecker()
                self.assertFalse(checker.check("ask_tool", {}))
                decision = checker.decide("ask_tool", {})
                self.assertTrue(decision["requires_approval"])


class TestDefaultspackHttpRegistryContract(unittest.TestCase):
    def test_registry_requests_include_method_marker(self):
        transport_path = (
            Path(__file__).resolve().parent.parent
            / "ecosystem"
            / "defaultspack"
            / "transport"
            / "http.py"
        )
        source = transport_path.read_text(encoding="utf-8")
        self.assertIn('request_data.setdefault("_method", method)', source)


if __name__ == "__main__":
    unittest.main()
