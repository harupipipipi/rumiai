from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend_core.ecosystem.registry import Registry
from core_runtime.function_registry import FunctionRegistry


class _FakeContainer:
    def __init__(self, function_registry):
        self._function_registry = function_registry

    def get_or_none(self, name):
        if name == "function_registry":
            return self._function_registry
        return None


class _FakeActiveEcosystem:
    def __init__(self, active_pack_identity=None, overrides=None, disabled=None):
        self.active_pack_identity = active_pack_identity
        self._overrides = overrides or {}
        self._disabled = set(disabled or [])

    def get_override(self, component_type):
        return self._overrides.get(component_type)

    def is_component_disabled(self, component_full_id):
        return component_full_id in self._disabled


class TestDefaultspackRegistryIntegration(unittest.TestCase):
    def test_registry_loads_defaultspack_functions(self):
        function_registry = FunctionRegistry()
        with patch(
            "core_runtime.di_container.get_container",
            return_value=_FakeContainer(function_registry),
        ):
            registry = Registry()
            packs = registry.load_all_packs()

        self.assertIn("defaultspack", packs)
        self.assertIsNotNone(function_registry.get("defaultspack:list_modules"))
        self.assertIsNotNone(function_registry.get("defaultspack:install_setup_pack"))

    def test_active_defaultspack_identity_makes_v2_primary(self):
        function_registry = FunctionRegistry()
        with patch(
            "core_runtime.di_container.get_container",
            return_value=_FakeContainer(function_registry),
        ):
            registry = Registry()
            registry.load_all_packs()

        active = _FakeActiveEcosystem(active_pack_identity="rumi:ecosystem/defaultspack")
        component = registry.resolve_component_for_type("chat", active)

        self.assertIsNotNone(component)
        self.assertEqual(component.pack_id, "defaultspack")
        self.assertEqual(component.id, "chat")

    def test_defaultspack_is_not_forced_without_active_identity(self):
        function_registry = FunctionRegistry()
        with patch(
            "core_runtime.di_container.get_container",
            return_value=_FakeContainer(function_registry),
        ):
            registry = Registry()
            registry.load_all_packs()

        active = _FakeActiveEcosystem(active_pack_identity=None)
        component = registry.resolve_component_for_type("agent", active)

        self.assertIsNotNone(component)
        self.assertEqual(component.pack_id, "defaults")
        self.assertEqual(component.id, "agent")

    def test_full_id_override_can_select_non_preferred_pack(self):
        function_registry = FunctionRegistry()
        with patch(
            "core_runtime.di_container.get_container",
            return_value=_FakeContainer(function_registry),
        ):
            registry = Registry()
            registry.load_all_packs()

        active = _FakeActiveEcosystem(
            active_pack_identity="rumi:ecosystem/defaultspack",
            overrides={"chat": "defaults:chat:chat"},
        )
        component = registry.resolve_component_for_type("chat", active)

        self.assertIsNotNone(component)
        self.assertEqual(component.pack_id, "defaults")
        self.assertEqual(component.full_id, "defaults:chat:chat")

    def test_defaultspack_pack_routes_are_cloned_to_v2_prefix(self):
        function_registry = FunctionRegistry()
        with patch(
            "core_runtime.di_container.get_container",
            return_value=_FakeContainer(function_registry),
        ):
            registry = Registry()
            registry.load_all_packs()

        routes = registry.get_pack_routes("defaultspack")
        self.assertTrue(
            any(route["path"] == "/api/packs/defaultspack/chat/conversations" for route in routes)
        )


if __name__ == "__main__":
    unittest.main()
