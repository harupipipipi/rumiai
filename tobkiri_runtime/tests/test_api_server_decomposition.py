from __future__ import annotations

def test_pack_api_handler_excludes_router_table_mixin_from_dispatch():
    from core_runtime.pack_api_server import PackAPIHandler

    assert not hasattr(PackAPIHandler, "_dispatch_api_route")
    assert not hasattr(PackAPIHandler, "load_api_routes")


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
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from tests.legacy_authority_contracts import (
        assert_profile_resolver_requires_authority_snapshot,
        assert_retired_module_absent,
    )
    from tests.v4_batch_support import assert_payload_mutations_denied, harness

    assert_retired_module_absent("core_runtime.capability_executor")
    assert_profile_resolver_requires_authority_snapshot()
    with TemporaryDirectory() as root:
        assert_payload_mutations_denied(harness(Path(root)))
