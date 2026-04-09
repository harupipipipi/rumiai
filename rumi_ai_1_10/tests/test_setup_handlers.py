from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSetupHandlers(unittest.TestCase):
    def test_setup_handler_lists_packs(self):
        from core_runtime.api.setup_handlers import SetupHandlersMixin

        class _Handler(SetupHandlersMixin):
            pass

        handler = _Handler()
        with patch(
            "core_runtime.api.setup_handlers.get_setup_pack_manager"
        ) as mocked:
            mocked.return_value.list_packs.return_value = {"packs": []}
            result = handler._setup_list_packs()
        self.assertEqual(result, {"packs": []})

    def test_core_setup_routes_are_declared(self):
        ecosystem_path = (
            Path(__file__).resolve().parent.parent
            / "core_runtime"
            / "core_pack"
            / "core_setup"
            / "ecosystem.json"
        )
        import json

        data = json.loads(ecosystem_path.read_text(encoding="utf-8"))
        routes = data.get("api_routes", [])
        self.assertEqual(len(routes), 5)
        self.assertTrue(any(route.get("path") == "/api/setup/packs" for route in routes))
        self.assertTrue(
            any(route.get("path_pattern") == "/api/setup/packs/{id}/grant-all-ok" for route in routes)
        )

    def test_mutation_routes_are_not_pre_auth(self):
        import json
        from core_runtime.pack_api_server import PackAPIHandler

        setup_ecosystem_path = (
            Path(__file__).resolve().parent.parent
            / "core_runtime"
            / "core_pack"
            / "core_setup"
            / "ecosystem.json"
        )
        defaultspack_ecosystem_path = (
            Path(__file__).resolve().parent.parent
            / "ecosystem"
            / "defaultspack"
            / "ecosystem.json"
        )
        setup_data = json.loads(setup_ecosystem_path.read_text(encoding="utf-8"))
        defaultspack_data = json.loads(defaultspack_ecosystem_path.read_text(encoding="utf-8"))

        class _PackInfo:
            def __init__(self, ecosystem):
                self.ecosystem = ecosystem

        class _Registry:
            packs = {
                "core_setup": _PackInfo(setup_data),
                "defaultspack": _PackInfo(defaultspack_data),
            }

        PackAPIHandler.load_pre_auth_routes(_Registry())
        handler = PackAPIHandler.__new__(PackAPIHandler)
        self.assertFalse(handler._is_pre_auth_route("POST", "/api/setup/packs/install"))
        self.assertFalse(handler._is_pre_auth_route("POST", "/api/defaultspack/pack-requests/request-extension"))
        self.assertTrue(handler._is_pre_auth_route("GET", "/api/setup/status"))


if __name__ == "__main__":
    unittest.main()
