"""Tests for ecosystem_loader.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ecosystem.defaultspack.ecosystem_loader import EcosystemLoader, ALL_MODULES
from ecosystem.defaultspack.module_state import ModuleStatus


class TestEcosystemLoader:
    def test_setup_returns_summary(self):
        loader = EcosystemLoader()
        summary = loader.setup()
        assert "pack_id" in summary
        assert summary["pack_id"] == "defaultspack"
        assert "load_order" in summary
        assert "results" in summary

    def test_all_modules_attempted(self):
        loader = EcosystemLoader()
        summary = loader.setup()
        for mod_id in ALL_MODULES:
            assert mod_id in summary["results"]

    def test_independent_modules_enabled(self):
        loader = EcosystemLoader()
        summary = loader.setup()
        # Modules without deps should be enabled
        for mod_id in ["ai_client", "prompt", "tool", "memory", "coding", "media"]:
            assert mod_id in summary["enabled"], f"{mod_id} should be enabled"

    def test_get_module(self):
        loader = EcosystemLoader()
        loader.setup()
        ai = loader.get_module("ai_client")
        assert ai is not None

    def test_reload_module(self):
        loader = EcosystemLoader()
        loader.setup()
        result = loader.reload_module("ai_client")
        assert result["status"] == "enabled"

    def test_rollback_module(self):
        loader = EcosystemLoader()
        loader.setup()
        assert loader.rollback_module("ai_client")
        assert loader.get_module("ai_client") is None

    def test_catalog(self):
        loader = EcosystemLoader()
        loader.setup()
        catalog = loader.get_catalog()
        assert "ai_client" in catalog
        assert "prompt" in catalog
