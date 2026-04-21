from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSetupHandlers(unittest.TestCase):
    class _FakeFunctionRegistry:
        def __init__(self, registered=None):
            self._registered = set(registered or [])

        def get(self, qualified_name):
            return object() if qualified_name in self._registered else None

    class _FakeContainer:
        def __init__(self, function_registry=None):
            self._function_registry = function_registry

        def get_or_none(self, name):
            if name == "function_registry":
                return self._function_registry
            return None

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

    def test_setup_handler_accepts_multiple_setup_pack_ids(self):
        from core_runtime.api.setup_handlers import SetupHandlersMixin

        class _Handler(SetupHandlersMixin):
            pass

        handler = _Handler()
        install_result = {
            "success": True,
            "active_target_pack_id": "otherpack",
            "installed_setup_pack_ids": ["alpha", "beta"],
            "installed_target_pack_ids": ["alpha", "beta"],
        }
        with patch(
            "core_runtime.api.setup_handlers.get_setup_pack_manager"
        ) as mocked, patch(
            "core_runtime.api.setup_handlers.invoke_pack_function"
        ) as invoke, patch(
            "core_runtime.api.setup_handlers.get_container",
            return_value=self._FakeContainer(),
        ):
            mocked.return_value.install.return_value = install_result
            result = handler._setup_install_pack({"setup_pack_ids": ["alpha", "beta"]})

        mocked.return_value.install.assert_called_once_with(["alpha", "beta"])
        invoke.assert_not_called()
        self.assertEqual(
            result["migration_statuses"],
            {
                "alpha": {
                    "pack_id": "alpha",
                    "available": False,
                    "needs_user_migration": False,
                    "registry_available": False,
                    "reason": "function_registry_unavailable",
                },
                "beta": {
                    "pack_id": "beta",
                    "available": False,
                    "needs_user_migration": False,
                    "registry_available": False,
                    "reason": "function_registry_unavailable",
                },
            },
        )

    def test_setup_handler_runs_migration_for_active_setup_target_when_supported(self):
        from core_runtime.api.setup_handlers import SetupHandlersMixin

        class _Handler(SetupHandlersMixin):
            pass

        handler = _Handler()
        install_result = {
            "success": True,
            "active_target_pack_id": "alpha",
            "installed_setup_pack_ids": ["alpha"],
            "installed_target_pack_ids": ["alpha"],
        }
        registry = self._FakeFunctionRegistry(
            {"alpha:get_migration_status", "alpha:run_migration"}
        )
        with patch(
            "core_runtime.api.setup_handlers.get_setup_pack_manager"
        ) as mocked, patch(
            "core_runtime.api.setup_handlers.invoke_pack_function",
            side_effect=[
                {"needs_user_migration": True},
                {"migrated": True},
                {"needs_user_migration": False},
            ],
        ) as invoke:
            mocked.return_value.install.return_value = install_result
            with patch(
                "core_runtime.api.setup_handlers.get_container",
                return_value=self._FakeContainer(registry),
            ):
                result = handler._setup_install_pack({"setup_pack_id": "alpha"})

        mocked.return_value.install.assert_called_once_with("alpha")
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual(result["migrations"], {"alpha": {"migrated": True}})
        self.assertEqual(
            result["migration_statuses"]["alpha"],
            {
                "pack_id": "alpha",
                "available": True,
                "needs_user_migration": False,
                "registry_available": True,
                "reason": None,
            },
        )

    def test_setup_handler_multi_pack_migration_handles_mixed_capabilities(self):
        from core_runtime.api.setup_handlers import SetupHandlersMixin

        class _Handler(SetupHandlersMixin):
            pass

        handler = _Handler()
        install_result = {
            "success": True,
            "active_target_pack_id": "beta",
            "installed_setup_pack_ids": ["beta", "gamma"],
            "installed_target_pack_ids": ["beta", "gamma"],
        }
        registry = self._FakeFunctionRegistry(
            {"beta:get_migration_status", "beta:run_migration"}
        )

        def _invoke(pack_id, function_id):
            if (pack_id, function_id) == ("beta", "get_migration_status"):
                if not hasattr(_invoke, "seen"):
                    _invoke.seen = True
                    return {"needs_user_migration": True}
                return {"needs_user_migration": False}
            if (pack_id, function_id) == ("beta", "run_migration"):
                return {"migrated": True}
            raise AssertionError(f"unexpected invoke: {(pack_id, function_id)}")

        with patch(
            "core_runtime.api.setup_handlers.get_setup_pack_manager"
        ) as mocked, patch(
            "core_runtime.api.setup_handlers.invoke_pack_function",
            side_effect=_invoke,
        ) as invoke:
            mocked.return_value.install.return_value = install_result
            with patch(
                "core_runtime.api.setup_handlers.get_container",
                return_value=self._FakeContainer(registry),
            ):
                result = handler._setup_install_pack({"setup_pack_ids": ["beta", "gamma"]})

        mocked.return_value.install.assert_called_once_with(["beta", "gamma"])
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual(result["migrations"], {"beta": {"migrated": True}})
        self.assertEqual(result["migration_statuses"]["beta"]["available"], True)
        self.assertEqual(result["migration_statuses"]["beta"]["needs_user_migration"], False)
        self.assertEqual(
            result["migration_statuses"]["gamma"],
            {
                "pack_id": "gamma",
                "available": False,
                "needs_user_migration": False,
                "registry_available": True,
                "reason": "function_not_registered",
            },
        )

    def test_setup_get_migration_status_uses_active_setup_target(self):
        from core_runtime.api.setup_handlers import SetupHandlersMixin

        class _Handler(SetupHandlersMixin):
            pass

        handler = _Handler()
        registry = self._FakeFunctionRegistry({"alpha:get_migration_status"})
        with patch(
            "core_runtime.api.setup_handlers.get_setup_pack_manager"
        ) as mocked, patch(
            "core_runtime.api.setup_handlers.get_container",
            return_value=self._FakeContainer(registry),
        ), patch(
            "core_runtime.api.setup_handlers.invoke_pack_function",
            return_value={"needs_user_migration": False},
        ) as invoke:
            mocked.return_value.get_selection.return_value = {"active_target_pack_id": "alpha"}
            result = handler._setup_get_migration_status()

        invoke.assert_called_once_with("alpha", "get_migration_status")
        self.assertEqual(
            result,
            {
                "pack_id": "alpha",
                "available": True,
                "needs_user_migration": False,
                "registry_available": True,
                "reason": None,
            },
        )

    def test_setup_get_migration_status_returns_unavailable_without_active_target(self):
        from core_runtime.api.setup_handlers import SetupHandlersMixin

        class _Handler(SetupHandlersMixin):
            pass

        handler = _Handler()
        with patch(
            "core_runtime.api.setup_handlers.get_setup_pack_manager"
        ) as mocked:
            mocked.return_value.get_selection.return_value = {}
            result = handler._setup_get_migration_status()

        self.assertEqual(
            result,
            {
                "pack_id": None,
                "available": False,
                "needs_user_migration": False,
                "registry_available": False,
                "reason": "active_target_not_selected",
            },
        )

    def test_setup_get_migration_status_distinguishes_registry_unavailable(self):
        from core_runtime.api.setup_handlers import SetupHandlersMixin

        class _Handler(SetupHandlersMixin):
            pass

        handler = _Handler()
        with patch(
            "core_runtime.api.setup_handlers.get_setup_pack_manager"
        ) as mocked, patch(
            "core_runtime.api.setup_handlers.get_container",
            return_value=self._FakeContainer(None),
        ):
            mocked.return_value.get_selection.return_value = {"active_target_pack_id": "alpha"}
            result = handler._setup_get_migration_status()

        self.assertEqual(
            result,
            {
                "pack_id": "alpha",
                "available": False,
                "needs_user_migration": False,
                "registry_available": False,
                "reason": "function_registry_unavailable",
            },
        )

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

    def test_control_panel_requires_session_except_bootstrap_exchange(self):
        import json
        from core_runtime.pack_api_server import PackAPIHandler

        control_panel_ecosystem_path = (
            Path(__file__).resolve().parent.parent
            / "core_runtime"
            / "core_pack"
            / "core_control_panel"
            / "ecosystem.json"
        )
        control_panel_data = json.loads(control_panel_ecosystem_path.read_text(encoding="utf-8"))

        self.assertTrue(control_panel_data["web_mount"]["auth_required"])
        self.assertEqual(
            control_panel_data["pre_auth_routes"],
            [
                {"method": "POST", "path": "/api/panel/auth/bootstrap"},
                {"method": "POST", "path": "/api/panel/auth/exchange"},
            ],
        )

        class _PackInfo:
            def __init__(self, ecosystem):
                self.ecosystem = ecosystem

        class _Registry:
            packs = {
                "core_control_panel": _PackInfo(control_panel_data),
            }

        PackAPIHandler.load_pre_auth_routes(_Registry())
        handler = PackAPIHandler.__new__(PackAPIHandler)
        self.assertTrue(handler._is_pre_auth_route("POST", "/api/panel/auth/bootstrap"))
        self.assertTrue(handler._is_pre_auth_route("POST", "/api/panel/auth/exchange"))
        self.assertFalse(handler._is_pre_auth_route("GET", "/api/panel/dashboard"))
        self.assertFalse(handler._is_pre_auth_route("POST", "/api/panel/flows"))

    def test_core_setup_web_uses_moved_setup_routes_only(self):
        web_path = (
            Path(__file__).resolve().parent.parent
            / "core_runtime"
            / "core_pack"
            / "core_setup"
            / "web"
            / "index.html"
        )
        source = web_path.read_text(encoding="utf-8")
        self.assertIn("/api/setup/packs/install", source)
        self.assertIn("/api/setup/migration/status", source)
        self.assertNotIn("/api/defaultspack/setup", source)
        self.assertNotIn(
            "Checked setup packs are installed together and receive all OK permissions.",
            source,
        )
        self.assertIn(
            "all OK permissions are granted only to setup packs that explicitly support all OK",
            source,
        )
        self.assertIn("Installs without all OK grants", source)


if __name__ == "__main__":
    unittest.main()
