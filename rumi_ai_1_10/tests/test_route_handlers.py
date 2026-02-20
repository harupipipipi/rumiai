"""
RouteHandlersMixin のユニットテスト (Wave4-B 改善推奨3)

テスト対象:
  - _is_safe_path_param (モジュールレベル関数)
  - _compile_template_path (モジュールレベル関数)
  - RouteHandlersMixin.load_pack_routes
  - RouteHandlersMixin._match_pack_route
  - RouteHandlersMixin._handle_pack_route_request
  - RouteHandlersMixin._get_registered_routes
  - RouteHandlersMixin._reload_pack_routes
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# ダミーモジュール — route_handlers.py 内の動的インポート回避用
# ---------------------------------------------------------------------------
_PKG = "rumi_ai_1_10.core_runtime"

# pack_api_server ダミー
_dummy_pack_api = types.ModuleType(f"{_PKG}.pack_api_server")


class _APIResponse:
    """テスト用 APIResponse スタブ"""

    def __init__(self, success, data=None, error=None):
        self.success = success
        self.data = data
        self.error = error

    def __repr__(self):
        return f"APIResponse(success={self.success!r}, error={self.error!r})"


_dummy_pack_api.APIResponse = _APIResponse
sys.modules.setdefault(f"{_PKG}.pack_api_server", _dummy_pack_api)

# audit_logger ダミー
_dummy_audit = types.ModuleType(f"{_PKG}.audit_logger")
_dummy_audit_instance = MagicMock()
_dummy_audit.get_audit_logger = MagicMock(return_value=_dummy_audit_instance)
sys.modules.setdefault(f"{_PKG}.audit_logger", _dummy_audit)

# ---------------------------------------------------------------------------
# テスト対象のインポート
# ---------------------------------------------------------------------------
from rumi_ai_1_10.core_runtime.api.route_handlers import (  # noqa: E402
    RouteHandlersMixin,
    _compile_template_path,
    _is_safe_path_param,
)
from rumi_ai_1_10.core_runtime.api._helpers import _SAFE_ERROR_MSG  # noqa: E402


# ======================================================================
# テスト用スタブ
# ======================================================================

class StubRouteHandler(RouteHandlersMixin):
    """RouteHandlersMixin を利用可能にするための最小スタブ"""

    def __init__(self):
        self.responses: list[tuple] = []
        self._flow_results: dict = {}

    def _send_response(self, response, status_code=200):
        self.responses.append((response, status_code))

    def _run_flow(self, flow_id, inputs, timeout=300):
        if flow_id in self._flow_results:
            return self._flow_results[flow_id]
        return {"success": True, "result": {"flow_id": flow_id, "inputs": inputs}}


def _make_registry(routes_by_pack: dict) -> MagicMock:
    """テスト用の mock registry を生成

    Args:
        routes_by_pack: {pack_id: [route_dict, ...]}
    """
    reg = MagicMock()
    reg.get_all_routes.return_value = routes_by_pack
    return reg


# ======================================================================
# Fixture: ルーティングテーブルリセット
# ======================================================================

@pytest.fixture(autouse=True)
def _reset_routes():
    """各テスト後に classvar ルーティングテーブルをリセット"""
    yield
    RouteHandlersMixin._pack_routes = {}
    RouteHandlersMixin._exact_routes = {}
    RouteHandlersMixin._template_routes = []


# ======================================================================
# TestIsSafePathParam
# ======================================================================

class TestIsSafePathParam:
    """_is_safe_path_param のテスト"""

    def test_normal_string(self):
        assert _is_safe_path_param("hello") is True
        assert _is_safe_path_param("pack-123") is True
        assert _is_safe_path_param("my_flow.v2") is True

    def test_null_byte_rejected(self):
        assert _is_safe_path_param("hello\x00world") is False
        assert _is_safe_path_param("\x00") is False

    def test_path_traversal_rejected(self):
        assert _is_safe_path_param("..") is False
        assert _is_safe_path_param("../etc/passwd") is False
        assert _is_safe_path_param("foo/../bar") is False

    def test_single_dot_allowed(self):
        assert _is_safe_path_param(".") is True
        assert _is_safe_path_param("file.txt") is True

    def test_empty_string_allowed(self):
        """空文字列は構文的には安全（ルーティングでは別途弾かれる）"""
        assert _is_safe_path_param("") is True


# ======================================================================
# TestCompileTemplatePath
# ======================================================================

class TestCompileTemplatePath:
    """_compile_template_path のテスト"""

    def test_no_placeholder_returns_none(self):
        assert _compile_template_path("/api/health") is None
        assert _compile_template_path("/api/routes") is None

    def test_single_placeholder(self):
        result = _compile_template_path("/api/packs/{pack_id}")
        assert result is not None
        pattern, params = result
        assert params == ["pack_id"]
        m = pattern.match("/api/packs/my-pack")
        assert m is not None
        assert m.group("pack_id") == "my-pack"

    def test_multiple_placeholders(self):
        result = _compile_template_path("/api/packs/{pack_id}/items/{item_id}")
        assert result is not None
        pattern, params = result
        assert params == ["pack_id", "item_id"]
        m = pattern.match("/api/packs/p1/items/i2")
        assert m is not None
        assert m.group("pack_id") == "p1"
        assert m.group("item_id") == "i2"

    def test_consecutive_placeholders(self):
        """連続プレースホルダのコンパイル"""
        result = _compile_template_path("/{a}/{b}")
        assert result is not None
        pattern, params = result
        assert params == ["a", "b"]
        m = pattern.match("/foo/bar")
        assert m is not None
        assert m.group("a") == "foo"
        assert m.group("b") == "bar"

    def test_placeholder_only_path(self):
        """プレースホルダのみのパス"""
        result = _compile_template_path("/{id}")
        assert result is not None
        pattern, params = result
        assert params == ["id"]
        m = pattern.match("/12345")
        assert m is not None
        assert m.group("id") == "12345"

    def test_no_match_wrong_path(self):
        result = _compile_template_path("/api/packs/{pack_id}")
        pattern, _ = result
        assert pattern.match("/api/other/my-pack") is None

    def test_no_match_extra_segments(self):
        result = _compile_template_path("/api/packs/{pack_id}")
        pattern, _ = result
        assert pattern.match("/api/packs/p1/extra") is None


# ======================================================================
# TestLoadPackRoutes
# ======================================================================

class TestLoadPackRoutes:
    """load_pack_routes のテスト"""

    def test_empty_registry(self):
        reg = _make_registry({})
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 0

    def test_none_registry(self):
        count = RouteHandlersMixin.load_pack_routes(None)
        assert count == 0

    def test_registry_without_get_all_routes(self):
        """get_all_routes 属性がない registry"""
        reg = MagicMock(spec=[])  # 属性なし
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 0

    def test_exact_route_registered(self):
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/pack1/status", "flow_id": "pack1.status"},
            ]
        })
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 1
        assert ("GET", "/api/pack1/status") in RouteHandlersMixin._exact_routes

    def test_template_route_registered(self):
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/pack1/{item_id}", "flow_id": "pack1.get_item"},
            ]
        })
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 1
        assert len(RouteHandlersMixin._template_routes) == 1

    def test_mixed_routes(self):
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/pack1/list", "flow_id": "pack1.list"},
                {"method": "GET", "path": "/api/pack1/{id}", "flow_id": "pack1.get"},
                {"method": "POST", "path": "/api/pack1/create", "flow_id": "pack1.create"},
            ]
        })
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 3
        assert len(RouteHandlersMixin._exact_routes) == 2
        assert len(RouteHandlersMixin._template_routes) == 1

    def test_missing_flow_id_skipped(self):
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/test", "flow_id": ""},
            ]
        })
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 0

    def test_missing_path_skipped(self):
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "", "flow_id": "pack1.flow"},
            ]
        })
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 0

    def test_reload_clears_previous(self):
        """再ロードで前のルートがクリアされること"""
        reg1 = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/old", "flow_id": "pack1.old"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg1)
        assert ("GET", "/api/old") in RouteHandlersMixin._exact_routes

        reg2 = _make_registry({
            "pack2": [
                {"method": "POST", "path": "/api/new", "flow_id": "pack2.new"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg2)
        assert ("GET", "/api/old") not in RouteHandlersMixin._exact_routes
        assert ("POST", "/api/new") in RouteHandlersMixin._exact_routes


# ======================================================================
# TestMatchPackRoute
# ======================================================================

class TestMatchPackRoute:
    """_match_pack_route のテスト"""

    def setup_method(self):
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/pack1/status", "flow_id": "pack1.status"},
                {"method": "GET", "path": "/api/pack1/{item_id}", "flow_id": "pack1.get_item"},
                {"method": "POST", "path": "/api/pack1/create", "flow_id": "pack1.create"},
                {"method": "GET", "path": "/{a}/{b}", "flow_id": "pack1.ab"},
                {"method": "GET", "path": "/{id}", "flow_id": "pack1.single"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        self.handler = StubRouteHandler()

    def test_exact_match(self):
        result = self.handler._match_pack_route("/api/pack1/status", "GET")
        assert result is not None
        route_info, path_params = result
        assert route_info["flow_id"] == "pack1.status"
        assert path_params == {}

    def test_exact_match_case_insensitive_method(self):
        result = self.handler._match_pack_route("/api/pack1/status", "get")
        assert result is not None

    def test_template_match(self):
        result = self.handler._match_pack_route("/api/pack1/my-item-123", "GET")
        assert result is not None
        route_info, path_params = result
        assert route_info["flow_id"] == "pack1.get_item"
        assert path_params["item_id"] == "my-item-123"

    def test_no_match_wrong_method(self):
        """GET ルートに POST でアクセスすると不一致"""
        result = self.handler._match_pack_route("/api/pack1/status", "DELETE")
        assert result is None

    def test_no_match_deep_path(self):
        """セグメント数が合わないパスは不一致"""
        result = self.handler._match_pack_route("/api/x/y/z/w", "GET")
        assert result is None

    def test_path_traversal_in_param_rejected(self):
        """パストラバーサルを含むパラメータが拒否されること"""
        # /{a}/{b} にマッチするが a=".." は拒否される
        result = self.handler._match_pack_route("/../foo", "GET")
        assert result is None

    def test_null_byte_in_param_rejected(self):
        """null バイト (URL encoded) を含むパラメータが拒否されること"""
        result = self.handler._match_pack_route("/api/pack1/item%00evil", "GET")
        assert result is None

    def test_url_decoded_traversal_rejected(self):
        """URL デコード後の .. (%2e%2e) が拒否されること"""
        result = self.handler._match_pack_route("/api/pack1/%2e%2e", "GET")
        assert result is None

    def test_consecutive_placeholders_match(self):
        """連続プレースホルダのマッチとパラメータ抽出"""
        result = self.handler._match_pack_route("/foo/bar", "GET")
        assert result is not None
        route_info, path_params = result
        assert route_info["flow_id"] == "pack1.ab"
        assert path_params["a"] == "foo"
        assert path_params["b"] == "bar"

    def test_single_placeholder_match(self):
        """プレースホルダのみのパス /{id} のマッチ"""
        result = self.handler._match_pack_route("/some-id", "GET")
        assert result is not None
        route_info, path_params = result
        assert route_info["flow_id"] == "pack1.single"
        assert path_params["id"] == "some-id"

    def test_trailing_slash_normalized(self):
        """末尾スラッシュが正規化されてテンプレートにマッチすること"""
        result = self.handler._match_pack_route("/api/pack1/my-item/", "GET")
        assert result is not None
        route_info, path_params = result
        assert path_params["item_id"] == "my-item"

    def test_exact_match_priority_over_template(self):
        """完全一致がテンプレートより優先されること"""
        result = self.handler._match_pack_route("/api/pack1/status", "GET")
        assert result is not None
        route_info, path_params = result
        assert route_info["flow_id"] == "pack1.status"
        assert path_params == {}


# ======================================================================
# TestHandlePackRouteRequest
# ======================================================================

class TestHandlePackRouteRequest:
    """_handle_pack_route_request のテスト"""

    def test_successful_flow_execution(self):
        handler = StubRouteHandler()
        match = (
            {"pack_id": "pack1", "flow_id": "pack1.action", "input_mapping": {}},
            {},
        )
        handler._handle_pack_route_request(
            "/api/pack1/action", {"data": "test"}, "POST", match,
        )
        assert len(handler.responses) == 1
        resp, code = handler.responses[0]
        assert resp.success is True

    def test_flow_scope_violation(self):
        """flow_id が pack_id のスコープ外の場合に 403 になること"""
        handler = StubRouteHandler()
        match = (
            {"pack_id": "pack1", "flow_id": "pack2.evil_flow", "input_mapping": {}},
            {},
        )
        handler._handle_pack_route_request("/api/test", {}, "POST", match)
        assert len(handler.responses) == 1
        resp, code = handler.responses[0]
        assert code == 403
        assert "scope" in (resp.error or "").lower()

    def test_path_params_in_inputs(self):
        """パスパラメータが inputs に含まれること"""
        handler = StubRouteHandler()
        captured_inputs = {}

        def mock_run_flow(flow_id, inputs, timeout=300):
            captured_inputs.update(inputs)
            return {"success": True, "result": {}}

        handler._run_flow = mock_run_flow

        match = (
            {"pack_id": "pack1", "flow_id": "pack1.get", "input_mapping": {}},
            {"item_id": "123"},
        )
        handler._handle_pack_route_request("/api/pack1/123", {}, "GET", match)
        assert captured_inputs["_path_params"]["item_id"] == "123"
        assert captured_inputs["_method"] == "GET"
        assert captured_inputs["_path"] == "/api/pack1/123"

    def test_input_mapping_applied(self):
        """input_mapping が適用されること"""
        handler = StubRouteHandler()
        captured_inputs = {}

        def mock_run_flow(flow_id, inputs, timeout=300):
            captured_inputs.update(inputs)
            return {"success": True, "result": {}}

        handler._run_flow = mock_run_flow

        match = (
            {
                "pack_id": "pack1",
                "flow_id": "pack1.get",
                "input_mapping": {"target_id": "path.item_id"},
            },
            {"item_id": "456"},
        )
        handler._handle_pack_route_request("/api/pack1/456", {}, "GET", match)
        assert captured_inputs["target_id"] == "456"

    def test_flow_failure_returns_error(self):
        """Flow 実行失敗時にエラーが返されること"""
        handler = StubRouteHandler()
        handler._flow_results["pack1.fail"] = {
            "success": False,
            "error": "Flow failed",
            "status_code": 422,
        }

        match = (
            {"pack_id": "pack1", "flow_id": "pack1.fail", "input_mapping": {}},
            {},
        )
        handler._handle_pack_route_request("/api/pack1/fail", {}, "POST", match)
        assert len(handler.responses) == 1
        resp, code = handler.responses[0]
        assert resp.success is False
        assert code == 422

    def test_flow_id_equals_pack_id_allowed(self):
        """flow_id == pack_id の場合もスコープチェックを通過すること"""
        handler = StubRouteHandler()
        match = (
            {"pack_id": "mypack", "flow_id": "mypack", "input_mapping": {}},
            {},
        )
        handler._handle_pack_route_request("/api/test", {}, "POST", match)
        assert len(handler.responses) == 1
        resp, code = handler.responses[0]
        assert resp.success is True

    def test_body_merged_into_inputs(self):
        """リクエストボディが inputs にマージされること"""
        handler = StubRouteHandler()
        captured_inputs = {}

        def mock_run_flow(flow_id, inputs, timeout=300):
            captured_inputs.update(inputs)
            return {"success": True, "result": {}}

        handler._run_flow = mock_run_flow

        match = (
            {"pack_id": "pack1", "flow_id": "pack1.do", "input_mapping": {}},
            {},
        )
        handler._handle_pack_route_request(
            "/api/pack1/do", {"key1": "val1", "key2": 42}, "POST", match,
        )
        assert captured_inputs["key1"] == "val1"
        assert captured_inputs["key2"] == 42


# ======================================================================
# TestGetRegisteredRoutes
# ======================================================================

class TestGetRegisteredRoutes:
    """_get_registered_routes のテスト"""

    def test_empty(self):
        handler = StubRouteHandler()
        result = handler._get_registered_routes()
        assert result["count"] == 0
        assert result["routes"] == []

    def test_with_routes(self):
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/p1/list", "flow_id": "pack1.list",
                 "description": "List items"},
                {"method": "POST", "path": "/api/p1/create", "flow_id": "pack1.create"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        handler = StubRouteHandler()
        result = handler._get_registered_routes()
        assert result["count"] == 2
        assert len(result["routes"]) == 2
        paths = {r["path"] for r in result["routes"]}
        assert "/api/p1/list" in paths
        assert "/api/p1/create" in paths

    def test_route_info_fields(self):
        """各ルート情報に必要なフィールドが含まれること"""
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/api/test", "flow_id": "pack1.test",
                 "description": "A test route"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        handler = StubRouteHandler()
        result = handler._get_registered_routes()
        route = result["routes"][0]
        assert "method" in route
        assert "path" in route
        assert "pack_id" in route
        assert "flow_id" in route
        assert "description" in route


# ======================================================================
# TestReloadPackRoutes
# ======================================================================

class TestReloadPackRoutes:
    """_reload_pack_routes のテスト"""

    def test_reload_success(self):
        handler = StubRouteHandler()
        mock_registry = MagicMock()

        dummy_be = types.ModuleType("backend_core")
        dummy_eco = types.ModuleType("backend_core.ecosystem")
        dummy_reg_mod = types.ModuleType("backend_core.ecosystem.registry")
        dummy_reg_mod.get_registry = MagicMock(return_value=mock_registry)

        with patch.dict(sys.modules, {
            "backend_core": dummy_be,
            "backend_core.ecosystem": dummy_eco,
            "backend_core.ecosystem.registry": dummy_reg_mod,
        }), patch.object(
            RouteHandlersMixin, "load_pack_routes", return_value=5,
        ):
            result = handler._reload_pack_routes()

        assert result["reloaded"] is True
        assert result["route_count"] == 5

    def test_reload_failure(self):
        handler = StubRouteHandler()
        # backend_core が import できない場合
        with patch.dict(sys.modules, {
            "backend_core": None,
        }):
            result = handler._reload_pack_routes()
        assert result["reloaded"] is False
        assert result["error"] == _SAFE_ERROR_MSG


# ======================================================================
# TestEdgeCases (改善推奨3: エッジケース)
# ======================================================================

class TestEdgeCases:
    """エッジケーステスト"""

    def test_double_dot_in_url_encoded_param(self):
        """URL エンコードされた %2e%2e (..) が拒否されること"""
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/items/{name}", "flow_id": "pack1.get"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        handler = StubRouteHandler()
        result = handler._match_pack_route("/items/%2e%2e", "GET")
        assert result is None

    def test_null_byte_url_encoded(self):
        """URL エンコードされた %00 が拒否されること"""
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/items/{name}", "flow_id": "pack1.get"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        handler = StubRouteHandler()
        result = handler._match_pack_route("/items/test%00evil", "GET")
        assert result is None

    def test_deeply_nested_template(self):
        """深くネストされたテンプレートパス"""
        reg = _make_registry({
            "pack1": [
                {
                    "method": "GET",
                    "path": "/api/{org}/{project}/{resource}/{id}",
                    "flow_id": "pack1.deep",
                },
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        handler = StubRouteHandler()
        result = handler._match_pack_route("/api/acme/proj1/items/42", "GET")
        assert result is not None
        route_info, params = result
        assert params["org"] == "acme"
        assert params["project"] == "proj1"
        assert params["resource"] == "items"
        assert params["id"] == "42"

    def test_special_chars_in_param_value(self):
        """特殊文字を含むパラメータ値（.. と \\x00 以外は許可）"""
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/items/{name}", "flow_id": "pack1.get"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        handler = StubRouteHandler()
        # ハイフン、アンダースコア、ドット、チルダなどは許可される
        result = handler._match_pack_route("/items/my-item_v2.0~draft", "GET")
        assert result is not None
        _, params = result
        assert params["name"] == "my-item_v2.0~draft"

    def test_method_default_uppercase(self):
        """route 登録時にメソッドが大文字化されること"""
        reg = _make_registry({
            "pack1": [
                {"method": "post", "path": "/api/test", "flow_id": "pack1.test"},
            ]
        })
        count = RouteHandlersMixin.load_pack_routes(reg)
        assert count == 1
        handler = StubRouteHandler()
        result = handler._match_pack_route("/api/test", "POST")
        assert result is not None

    def test_mixed_traversal_in_middle(self):
        """パス途中の .. を含むパラメータが拒否されること"""
        reg = _make_registry({
            "pack1": [
                {"method": "GET", "path": "/a/{x}/b", "flow_id": "pack1.mid"},
            ]
        })
        RouteHandlersMixin.load_pack_routes(reg)
        handler = StubRouteHandler()
        result = handler._match_pack_route("/a/../b", "GET")
        assert result is None
