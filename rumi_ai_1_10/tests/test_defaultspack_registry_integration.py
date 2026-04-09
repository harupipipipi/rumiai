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


if __name__ == "__main__":
    unittest.main()
