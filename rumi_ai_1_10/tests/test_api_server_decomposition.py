from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch


def test_pack_api_handler_uses_router_table_mixin_for_dispatch():
    from core_runtime.pack_api_server import PackAPIHandler

    assert PackAPIHandler._dispatch_api_route.__module__ == "core_runtime.api.router_table"


def test_pack_api_handler_uses_response_writer_mixin():
    from core_runtime.pack_api_server import PackAPIHandler

    assert PackAPIHandler._send_response.__module__ == "core_runtime.api.http_response"


def test_pack_api_handler_uses_auth_gate_mixin():
    from core_runtime.pack_api_server import PackAPIHandler

    assert PackAPIHandler._check_auth.__module__ == "core_runtime.api.auth_gate"


def test_pack_api_handler_uses_web_mount_mixin():
    from core_runtime.pack_api_server import PackAPIHandler

    assert PackAPIHandler._serve_static_file.__module__ == "core_runtime.api.web_mounts"


def test_pack_api_handler_uses_request_body_mixin():
    from core_runtime.pack_api_server import PackAPIHandler

    assert PackAPIHandler._parse_body.__module__ == "core_runtime.api.request_body"


def test_router_table_function_route_error_status_contract():
    from core_runtime.api.api_response import APIResponse
    from core_runtime.api.router_table import APIRouteTableMixin

    class Handler(APIRouteTableMixin):
        _api_route_exact = {
            ("POST", "/demo"): {
                "handler": "",
                "function_id": "demo_function",
                "pack_id": "defaultspack",
                "pass_body": True,
                "pass_query": False,
                "response_mode": "result",
                "args": {},
                "path_param_map": {},
            }
        }
        _api_route_patterns = []

        @classmethod
        def _is_pack_approved_for_runtime_routes(cls, pack_id):
            return pack_id == "defaultspack"

        @classmethod
        def _pack_allows_in_process_api_metadata(cls, pack_id):
            return pack_id == "defaultspack"

        @staticmethod
        def _is_safe_id(value):
            return bool(value)

        def _send_response(self, response: APIResponse, status=200):
            self.sent = (status, response.error)

    class Executor:
        def __init__(self, error_type):
            self.error_type = error_type

        def execute(self, pack_id, request):
            assert pack_id == "defaultspack"
            assert request["context"]["_api_route"] is True
            return SimpleNamespace(success=False, error_type=self.error_type, error="boom")

    for error_type, expected in {
        "grant_denied": (403, "Forbidden"),
        "trust_denied": (403, "Forbidden"),
        "rate_limited": (429, "boom"),
        "invalid_request": (400, "boom"),
    }.items():
        handler = Handler()
        with patch("core_runtime.capability_executor.get_capability_executor", return_value=Executor(error_type)):
            assert handler._dispatch_api_route("POST", "/demo", body={"ok": True}) is True
        assert handler.sent == expected
