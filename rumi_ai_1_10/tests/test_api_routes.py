"""tests/test_api_routes.py — 施策3: api_routes テーブル構築・ディスパッチのテスト"""
from __future__ import annotations

import re
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# テスト対象のモジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestCompileTemplatePath(unittest.TestCase):
    """route_handlers._compile_template_path のテスト"""

    def setUp(self):
        from core_runtime.api.route_handlers import _compile_template_path
        self._compile = _compile_template_path

    def test_no_placeholder_returns_none(self):
        """プレースホルダなしのパスは None を返す"""
        result = self._compile("/api/panel/dashboard")
        self.assertIsNone(result)

    def test_single_placeholder(self):
        """単一プレースホルダのコンパイル"""
        result = self._compile("/api/panel/flows/{id}")
        self.assertIsNotNone(result)
        pattern, param_names = result
        self.assertEqual(param_names, ["id"])
        self.assertIsNotNone(pattern.match("/api/panel/flows/my-flow-1"))
        self.assertIsNone(pattern.match("/api/panel/flows/"))
        self.assertIsNone(pattern.match("/api/panel/flows/a/b"))

    def test_suffix_after_placeholder(self):
        """プレースホルダの後にサフィックスがあるパターン"""
        result = self._compile("/api/panel/packs/{id}/enable")
        self.assertIsNotNone(result)
        pattern, param_names = result
        self.assertEqual(param_names, ["id"])
        m = pattern.match("/api/panel/packs/my-pack/enable")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("id"), "my-pack")

    def test_no_match_wrong_suffix(self):
        """異なるサフィックスはマッチしない"""
        result = self._compile("/api/panel/packs/{id}/enable")
        pattern, _ = result
        self.assertIsNone(pattern.match("/api/panel/packs/my-pack/disable"))


class TestApiRouteTableBuild(unittest.TestCase):
    """load_api_routes のテスト（モック registry 使用）"""

    def setUp(self):
        from core_runtime.pack_api_server import PackAPIHandler

        self._approval_patcher = patch.object(
            PackAPIHandler,
            "_is_pack_approved_for_runtime_routes",
            return_value=True,
        )
        self._approval_patcher.start()

    def tearDown(self):
        self._approval_patcher.stop()

    def _make_mock_registry(
        self,
        api_routes,
        *,
        pack_id="test_pack",
        pack_path=None,
        pre_auth_routes=None,
        web_mount=None,
    ):
        pack_info = MagicMock()
        pack_info.ecosystem = {"api_routes": api_routes}
        if pre_auth_routes is not None:
            pack_info.ecosystem["pre_auth_routes"] = pre_auth_routes
        if web_mount is not None:
            pack_info.ecosystem["web_mount"] = web_mount
        if pack_path is not None:
            pack_info.path = pack_path
            pack_info.subdir = pack_path
        registry = MagicMock()
        registry.packs = {pack_id: pack_info}
        return registry

    def test_exact_route_match(self):
        """完全一致ルートが正しくマッチする"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "GET", "path": "/api/panel/dashboard", "handler": "_panel_get_dashboard"},
        ])
        count = PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})
        self.assertEqual(count, 1)
        self.assertIn(("GET", "/api/panel/dashboard"), PackAPIHandler._api_route_exact)
        entry = PackAPIHandler._api_route_exact[("GET", "/api/panel/dashboard")]
        self.assertEqual(entry["handler"], "_panel_get_dashboard")

    def test_pattern_route_match(self):
        """パターンルート（/api/panel/flows/{id}）が正しくマッチする"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "GET", "path_pattern": "/api/panel/flows/{id}", "handler": "_panel_get_flow_detail"},
        ])
        count = PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})
        self.assertEqual(count, 1)
        self.assertEqual(len(PackAPIHandler._api_route_patterns), 1)
        method, pattern, param_names, entry = PackAPIHandler._api_route_patterns[0]
        self.assertEqual(method, "GET")
        self.assertEqual(param_names, ["id"])
        self.assertEqual(entry["handler"], "_panel_get_flow_detail")

    def test_path_param_extraction(self):
        """パスパラメータが正しく抽出される"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "GET", "path_pattern": "/api/panel/flows/{id}", "handler": "_panel_get_flow_detail"},
            {"method": "POST", "path_pattern": "/api/panel/packs/{id}/enable", "handler": "_panel_enable_pack"},
        ])
        PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})

        # flows/{id}
        _, pattern1, _, _ = PackAPIHandler._api_route_patterns[0]
        m1 = pattern1.match("/api/panel/flows/test-flow-123")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.group("id"), "test-flow-123")

        # packs/{id}/enable
        _, pattern2, _, _ = PackAPIHandler._api_route_patterns[1]
        m2 = pattern2.match("/api/panel/packs/my_pack/enable")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.group("id"), "my_pack")

    def test_method_mismatch(self):
        """HTTP メソッドが異なる場合マッチしない"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "POST", "path": "/api/panel/flows", "handler": "_panel_create_flow", "pass_body": True},
        ])
        PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})
        self.assertNotIn(("GET", "/api/panel/flows"), PackAPIHandler._api_route_exact)
        self.assertIn(("POST", "/api/panel/flows"), PackAPIHandler._api_route_exact)

    def test_unknown_path(self):
        """テーブルにないパスがマッチしない"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "GET", "path": "/api/panel/dashboard", "handler": "_panel_get_dashboard"},
        ])
        PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})
        self.assertNotIn(("GET", "/api/unknown"), PackAPIHandler._api_route_exact)

    def test_invalid_handler_name_rejected(self):
        """不正なハンドラ名は拒否される"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "GET", "path": "/api/bad", "handler": "os.system('rm -rf /')"},
        ])
        count = PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})
        self.assertEqual(count, 0)

    def test_function_route_from_untrusted_pack_rejected(self):
        """第三者 pack の function_id api_route は登録されない"""
        from core_runtime.pack_api_server import PackAPIHandler

        registry = self._make_mock_registry([
            {"method": "POST", "path": "/api/pwn", "function_id": "pwn"},
        ])

        count = PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})

        self.assertEqual(count, 0)
        self.assertNotIn(("POST", "/api/pwn"), PackAPIHandler._api_route_exact)

    def test_pre_auth_routes_from_untrusted_pack_rejected(self):
        """第三者 pack の pre_auth_routes は認証バイパステーブルに載せない"""
        from core_runtime.pack_api_server import PackAPIHandler

        registry = self._make_mock_registry(
            [],
            pre_auth_routes=[{"method": "POST", "path": "/api/pwn"}],
            web_mount={"path_prefix": "/public-pack", "static_root": "web", "auth_required": False},
        )

        count = PackAPIHandler.load_pre_auth_routes(registry, pack_ids={"test_pack"})

        self.assertEqual(count, 0)
        self.assertEqual(PackAPIHandler._pre_auth_table, [])

    def test_pass_body_flag(self):
        """pass_body フラグがエントリに保存される"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "POST", "path": "/api/panel/flows", "handler": "_panel_create_flow", "pass_body": True},
        ])
        PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})
        entry = PackAPIHandler._api_route_exact[("POST", "/api/panel/flows")]
        self.assertTrue(entry["pass_body"])

    def test_response_mode_raw(self):
        """response_mode が raw のエントリ"""
        from core_runtime.pack_api_server import PackAPIHandler
        registry = self._make_mock_registry([
            {"method": "POST", "path": "/api/panel/kernel/restart", "handler": "_panel_restart_kernel", "response_mode": "raw"},
        ])
        PackAPIHandler.load_api_routes(registry, pack_ids={"test_pack"})
        entry = PackAPIHandler._api_route_exact[("POST", "/api/panel/kernel/restart")]
        self.assertEqual(entry["response_mode"], "raw")

    def test_dispatch_response_mode_raw_uses_raw_json_payload(self):
        from core_runtime.pack_api_server import PackAPIHandler

        PackAPIHandler._api_route_exact = {
            ("POST", "/api/panel/kernel/restart"): {
                "pack_id": "test_pack",
                "handler": "_panel_restart_kernel",
                "function_id": "",
                "pass_body": False,
                "response_mode": "raw",
                "args": {},
                "path_param_map": {},
            }
        }
        PackAPIHandler._api_route_patterns = []
        handler = PackAPIHandler.__new__(PackAPIHandler)
        handler._panel_restart_kernel = lambda: {
            "restarting": True,
            "message": "Kernel restart requested",
        }
        handler._send_raw_json = MagicMock()
        handler._send_result = MagicMock()
        handler._send_response = MagicMock()
        handler._send_sse = MagicMock()

        dispatched = handler._dispatch_api_route(
            "POST",
            "/api/panel/kernel/restart",
        )

        self.assertTrue(dispatched)
        handler._send_raw_json.assert_called_once_with(
            {
                "restarting": True,
                "message": "Kernel restart requested",
            },
            status=200,
        )
        handler._send_result.assert_not_called()
        handler._send_response.assert_not_called()

    def test_dispatch_response_mode_raw_preserves_explicit_status_code(self):
        from core_runtime.pack_api_server import PackAPIHandler

        PackAPIHandler._api_route_exact = {
            ("POST", "/api/panel/kernel/restart"): {
                "pack_id": "test_pack",
                "handler": "_panel_restart_kernel",
                "function_id": "",
                "pass_body": False,
                "response_mode": "raw",
                "args": {},
                "path_param_map": {},
            }
        }
        PackAPIHandler._api_route_patterns = []
        handler = PackAPIHandler.__new__(PackAPIHandler)
        handler._panel_restart_kernel = lambda: {
            "error": "Restart rate limited",
            "status_code": 429,
        }
        handler._send_raw_json = MagicMock()
        handler._send_result = MagicMock()
        handler._send_response = MagicMock()
        handler._send_sse = MagicMock()

        dispatched = handler._dispatch_api_route(
            "POST",
            "/api/panel/kernel/restart",
        )

        self.assertTrue(dispatched)
        handler._send_raw_json.assert_called_once_with(
            {
                "error": "Restart rate limited",
                "status_code": 429,
            },
            status=429,
        )
        handler._send_result.assert_not_called()
        handler._send_response.assert_not_called()

    def test_api_route_strips_reserved_body_and_query_keys(self):
        from core_runtime.access_tokens import AuthenticatedPrincipal
        from core_runtime.api.request_authorizer import RouteAuthorization
        from core_runtime.api.route_handlers import _compile_template_path
        from core_runtime.pack_api_server import PackAPIHandler

        captured = {}

        class FakeExecutor:
            def execute(self, principal_id, request):
                captured["principal_id"] = principal_id
                captured["request"] = request
                return MagicMock(success=True, output={"ok": True})

        entry = {
            "pack_id": "defaultspack",
            "owner_pack_id": "defaultspack",
            "handler": "",
            "function_id": "echo",
            "pass_body": True,
            "pass_query": True,
            "response_mode": "result",
            "args": {"static": "kept", "_authority_subject": {"profile_id": "evil"}},
            "path_param_map": {
                "safe_id": "id",
                "_authenticated_principal": "id",
            },
            "resource_template": {},
            "core_only": False,
        }
        pattern, param_names = _compile_template_path("/api/test/{id}")
        PackAPIHandler._api_route_exact = {}
        PackAPIHandler._api_route_patterns = [("POST", pattern, param_names, entry)]
        handler = PackAPIHandler.__new__(PackAPIHandler)
        handler._authenticated_principal = AuthenticatedPrincipal(
            token_id="tok",
            profile_id="work",
            surface_id="mobile",
            device_id="phone-1",
            role="mobile_client",
            audiences=("kernel_api",),
            issued_at="",
            expires_at=None,
        )
        handler._send_result = MagicMock()
        handler._send_response = MagicMock()
        handler._send_sse = MagicMock()

        with patch.object(PackAPIHandler, "_is_pack_approved_for_runtime_routes", return_value=True):
            with patch.object(PackAPIHandler, "_pack_allows_in_process_api_metadata", return_value=True):
                with patch("core_runtime.api.router_table.authorize_route", return_value=RouteAuthorization(True)):
                    with patch("core_runtime.capability_executor.get_capability_executor", return_value=FakeExecutor()):
                        dispatched = handler._dispatch_api_route(
                            "POST",
                            "/api/test/abc",
                            body={
                                "visible": "body",
                                "_authenticated_principal": {"profile_id": "evil"},
                            },
                            query={
                                "q": "query",
                                "_authority_subject": {"profile_id": "evil"},
                            },
                        )

        self.assertTrue(dispatched)
        args = captured["request"]["args"]
        self.assertEqual(args["visible"], "body")
        self.assertEqual(args["q"], "query")
        self.assertEqual(args["static"], "kept")
        self.assertEqual(args["safe_id"], "abc")
        self.assertNotIn("_authenticated_principal", args)
        self.assertNotIn("_authority_subject", args)
        context = captured["request"]["context"]
        self.assertEqual(context["_authenticated_principal"]["profile_id"], "work")
        self.assertEqual(context["_authority_subject"]["profile_id"], "work")

    def test_none_registry(self):
        """registry が None の場合は 0 を返す"""
        from core_runtime.pack_api_server import PackAPIHandler
        count = PackAPIHandler.load_api_routes(None)
        self.assertEqual(count, 0)

    def test_core_control_panel_declares_node_manager_routes(self):
        routes_path = (
            Path(__file__).resolve().parent.parent
            / "core_runtime"
            / "core_pack"
            / "core_control_panel"
            / "ecosystem.json"
        )
        routes = json.loads(routes_path.read_text(encoding="utf-8"))["api_routes"]
        node_routes = [
            route
            for route in routes
            if route.get("method") == "GET"
            and (route.get("path") == "/api/panel/nodes" or route.get("path_pattern") == "/api/panel/profiles/{profile_id}/nodes")
        ]

        handlers = {route["handler"] for route in node_routes}
        self.assertIn("_panel_get_nodes", handlers)
        self.assertIn("_panel_get_profile_nodes", handlers)


class TestPathParamSafety(unittest.TestCase):
    """_is_safe_path_param のテスト"""

    def setUp(self):
        from core_runtime.api.route_handlers import _is_safe_path_param
        self._is_safe = _is_safe_path_param

    def test_normal_value(self):
        self.assertTrue(self._is_safe("my-flow-id"))

    def test_null_byte_rejected(self):
        self.assertFalse(self._is_safe("evil\x00payload"))

    def test_path_traversal_rejected(self):
        self.assertFalse(self._is_safe("../../../etc/passwd"))

    def test_empty_string(self):
        self.assertTrue(self._is_safe(""))


if __name__ == "__main__":
    unittest.main()
