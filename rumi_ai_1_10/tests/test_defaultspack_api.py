from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestDefaultspackApiRoutes(unittest.TestCase):
    def test_defaultspack_ecosystem_routes_are_loaded(self):
        from core_runtime.pack_api_server import PackAPIHandler

        ecosystem_path = (
            Path(__file__).resolve().parent.parent
            / "ecosystem"
            / "defaultspack"
            / "ecosystem.json"
        )
        data = json.loads(ecosystem_path.read_text(encoding="utf-8"))

        class _PackInfo:
            ecosystem = data

        class _Registry:
            packs = {"defaultspack": _PackInfo()}

        count = PackAPIHandler.load_api_routes(_Registry())
        self.assertEqual(count, 18)
        self.assertIn(("GET", "/api/defaultspack/modules"), PackAPIHandler._api_route_exact)
        self.assertIn(("GET", "/api/defaultspack/setup/packs"), PackAPIHandler._api_route_exact)
        self.assertIn(("GET", "/api/defaultspack/pack-requests"), PackAPIHandler._api_route_exact)
        self.assertEqual(len(PackAPIHandler._api_route_patterns), 11)


class TestDefaultspackHandlers(unittest.TestCase):
    def test_handler_delegates_to_function_runtime(self):
        from core_runtime.api.defaultspack_handlers import DefaultspackHandlersMixin

        class _Handler(DefaultspackHandlersMixin):
            pass

        handler = _Handler()
        with patch(
            "core_runtime.api.defaultspack_handlers.invoke_defaultspack_function",
            return_value={"modules": []},
        ) as mocked:
            result = handler._defaultspack_list_modules()

        self.assertEqual(result, {"modules": []})
        mocked.assert_called_once_with("defaultspack:list_modules")


if __name__ == "__main__":
    unittest.main()
