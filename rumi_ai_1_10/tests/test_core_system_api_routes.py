from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_core_system_api_manifest_is_loaded_into_builtin_routes():
    from core_runtime.pack_api_server import PackAPIHandler

    count = PackAPIHandler.load_api_routes(
        SimpleNamespace(packs={}),
        include_builtin_core_control_panel=True,
    )

    assert count > 0
    assert ("GET", "/api/packs") in PackAPIHandler._api_route_exact
    assert any(
        method == "GET"
        and entry["handler"] == "_get_pack_status"
        for method, _pattern, _params, entry in PackAPIHandler._api_route_patterns
    )


def test_core_system_api_manifest_file_declares_expected_routes():
    manifest_path = (
        Path(__file__).resolve().parent.parent
        / "core_runtime"
        / "core_pack"
        / "core_system_api"
        / "ecosystem.json"
    )

    assert manifest_path.is_file()
    text = manifest_path.read_text(encoding="utf-8")
    assert '"path": "/api/packs"' in text
    assert '"path_pattern": "/api/packs/{pack_id}/status"' in text


def test_do_get_prefers_api_route_dispatch_for_core_system_routes():
    from core_runtime.pack_api_server import PackAPIHandler

    handler = object.__new__(PackAPIHandler)
    handler.path = "/api/packs"
    handler.client_address = ("198.51.100.7", 12345)
    handler._check_rate_limit = MagicMock(return_value=True)
    handler._match_web_mount = MagicMock(return_value=None)
    handler._is_pre_auth_route = MagicMock(return_value=False)
    handler._check_auth = MagicMock(return_value=True)
    handler._parse_query = MagicMock(return_value={})
    handler._dispatch_api_route = MagicMock(return_value=True)
    handler._dispatch_defaultspack_http_route = MagicMock(return_value=False)
    handler._get_all_packs = MagicMock(side_effect=AssertionError("legacy branch should not run"))

    PackAPIHandler.do_GET(handler)

    handler._dispatch_api_route.assert_called_once_with("GET", "/api/packs", query={})
    handler._get_all_packs.assert_not_called()
