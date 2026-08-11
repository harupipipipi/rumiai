from __future__ import annotations

from typing import Any, cast

def test_pack_api_handler_excludes_router_table_mixin_from_dispatch():
    from core_runtime.pack_api_server import PackAPIHandler

    assert not hasattr(PackAPIHandler, "_dispatch_api_route")
    assert not hasattr(PackAPIHandler, "load_api_routes")


def test_pack_api_handler_uses_response_writer_mixin():
    from core_runtime.pack_api_server import PackAPIHandler

    assert PackAPIHandler._send_response.__module__ == "core_runtime.api.http_response"


def test_pack_api_handler_uses_auth_gate_mixin(monkeypatch):
    from core_runtime.api.auth_gate import AuthGateMixin
    from core_runtime.pack_api_server import PackAPIHandler

    assert AuthGateMixin in PackAPIHandler.__mro__
    handler = object.__new__(PackAPIHandler)
    handler._panel_session = None

    class ReplayGuard:
        def __init__(self):
            self.renewals = []

        def renew_session(self, session_id, *, session_ttl_seconds):
            self.renewals.append((session_id, session_ttl_seconds))

    replay_guard = ReplayGuard()
    cast(Any, handler)._contract_replay_guard = replay_guard
    delegated = []

    def deny(_handler, method, path):
        delegated.append((method, path))
        return False

    monkeypatch.setattr(AuthGateMixin, "_check_auth", deny)
    assert handler._check_auth("POST", "/api/contracts/example") is False
    assert delegated == [("POST", "/api/contracts/example")]
    assert replay_guard.renewals == []

    def authenticate(bound_handler, method, path):
        delegated.append((method, path))
        bound_handler._panel_session = {
            "session_id": "verified-session",
            "expires_in": 60,
        }
        return True

    monkeypatch.setattr(AuthGateMixin, "_check_auth", authenticate)
    assert handler._check_auth("GET", "/api/contracts/example") is True
    assert delegated[-1] == ("GET", "/api/contracts/example")
    assert replay_guard.renewals == [("verified-session", 60.0)]


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
    assert_retired_module_absent("core_runtime.api.router_table")
    assert_retired_module_absent("core_runtime.api.lifecycle.pack_handlers")
    assert_profile_resolver_requires_authority_snapshot()
    with TemporaryDirectory() as root:
        assert_payload_mutations_denied(harness(Path(root)))
