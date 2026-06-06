from __future__ import annotations


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
