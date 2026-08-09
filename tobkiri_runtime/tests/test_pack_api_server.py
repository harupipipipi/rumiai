"""Live and structural tests for the finite Pack v4 HTTP boundary."""

from __future__ import annotations

import http.client
import json
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from core_runtime.authority.v4 import AuthorityStore
from core_runtime.bootstrap.production_v4 import capture_production_dispatch
from core_runtime.bootstrap.profile_capture import (
    capture_default_profile,
    prepare_default_profile_confirmation,
)
from core_runtime.pack_api_server import (
    PackAPIHandler,
    PackAPIServer,
    RuntimeHTTPConfig,
)
from core_runtime.panel_auth import PanelAuthManager


class _Dispatch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    def invoke(
        self,
        contract_id: str,
        operation_id: str,
        payload: Mapping[str, object],
        *,
        version_range: str = ">=1,<2",
    ) -> Mapping[str, object]:
        self.calls.append((contract_id, operation_id, dict(payload)))
        return {"contract_id": contract_id, "operation_id": operation_id}


class _Lifecycle:
    def check_setup_status(self) -> dict[str, object]:
        return {"needs_setup": False, "setup_state": "complete"}

    def get_health(self) -> dict[str, object]:
        return {"status": "ok", "runtime_ready": True}


class _PackVMLifecycle:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def prepare(self) -> Mapping[str, object]:
        self.calls.append(("prepare", {}))
        return {
            "instance": "tobkiri-packvm-v4",
            "image_source": "https://images.invalid/pinned.img",
            "image_digest": "sha256:" + "a" * 64,
            "image_size_bytes": 700_000_000,
            "plan_digest": "sha256:" + "b" * 64,
            "ceremony_nonce": "c" * 32,
            "confirmation": "PROVISION tobkiri-packvm-v4 bbbbbbbbbbbb",
        }

    def consent(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(("consent", dict(payload)))
        return {"consent_id": "packvm-consent.test"}

    def provision(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(("provision", dict(payload)))
        return {"operation_id": payload["operation_id"], "state": "queued"}

    def doctor(self) -> Mapping[str, object]:
        self.calls.append(("doctor", {}))
        return {"ready": True, "attestation_digest": "sha256:" + "d" * 64}

    def readiness_snapshot(self) -> Mapping[str, object]:
        self.calls.append(("readiness_snapshot", {}))
        return {"ready": False}

    def progress(self, operation_id: str) -> Mapping[str, object]:
        self.calls.append(("progress", {"operation_id": operation_id}))
        return {"operation_id": operation_id, "state": "succeeded"}

    def cancel(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(("cancel", dict(payload)))
        return {"operation_id": payload["operation_id"], "state": "cancelled"}

    def stop(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(("stop", dict(payload)))
        return {"ready": False}

    def cleanup(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(("cleanup", dict(payload)))
        return {"ready": False, "instance": "tobkiri-packvm-v4"}


def test_profile_activation_refresh_requires_durable_success_result() -> None:
    handler = object.__new__(PackAPIHandler)
    refreshes: list[object] = []
    handler._runtime_refresh = refreshes.append

    handler._refresh_after_operation(
        "profile.change.activate",
        {"state": "error", "code": "UNAPPROVED"},
    )
    assert refreshes == []

    handler._refresh_after_operation(
        "profile.change.activate",
        {"state": "active", "activation_id": "activation.test"},
    )
    assert refreshes == [None]


@pytest.fixture
def live_server() -> Iterator[tuple[PackAPIServer, _Dispatch]]:
    dispatch = _Dispatch()
    server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="verified-desktop"),
        dispatch_session=dispatch,
        app_lifecycle_manager=_Lifecycle(),
    )
    server.start()
    try:
        yield server, dispatch
    finally:
        server.stop()


def _request(
    server: PackAPIServer,
    method: str,
    path: str,
    *,
    body: object | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, object], list[tuple[str, str]]]:
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = dict(headers or {})
    if encoded is not None:
        request_headers.setdefault("Content-Type", "application/json")
    connection.request(method, path, body=encoded, headers=request_headers)
    response = connection.getresponse()
    raw = response.read()
    response_headers = response.getheaders()
    connection.close()
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    return response.status, payload, response_headers


def _panel_session(
    server: PackAPIServer,
) -> tuple[str, str, str]:
    origin = f"http://127.0.0.1:{server.port}"
    status, bootstrap, _ = _request(
        server,
        "POST",
        "/api/panel/auth/bootstrap",
        body={},
        headers={"X-Rumi-Desktop-Bootstrap": "verified-desktop"},
    )
    assert status == 200
    code = bootstrap["data"]["code"]
    status, exchange, headers = _request(
        server,
        "POST",
        "/api/panel/auth/exchange",
        body={"code": code},
        headers={"Origin": origin},
    )
    assert status == 200
    cookie = next(value for key, value in headers if key.lower() == "set-cookie")
    return cookie.split(";", 1)[0], exchange["data"]["csrf_token"], origin


def _assert_retired_generic_dispatch(
    status: int,
    payload: Mapping[str, object],
) -> None:
    """Assert the typed no-write retirement contract for generic dispatch."""

    assert status == 410
    assert payload["data"] == {
        "api_version": "io.tobkiri.pack-api.v4",
        "state": "legacy_api_retired",
        "retired_route": "/api/v4/dispatch",
        "write_set": [],
    }
    assert payload["error"] == ("Legacy API route is retired; use an exact Pack v4 operation")


def test_packvm_lifecycle_routes_require_auth_csrf_and_fresh_request_id() -> None:
    lifecycle = _PackVMLifecycle()
    server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="verified-desktop"),
        packvm_lifecycle=lifecycle,
    )
    refreshed: list[object] = []
    server._refresh_runtime_capture = lambda session=None: refreshed.append(session)  # type: ignore[method-assign]
    server.start()
    try:
        status, _payload, _headers = _request(
            server,
            "POST",
            "/api/v4/packvm/prepare",
            body={},
        )
        assert status == 401
        cookie, csrf, origin = _panel_session(server)
        authenticated = {
            "Cookie": cookie,
            "Origin": origin,
            "X-Rumi-CSRF": csrf,
        }
        request_id = str(uuid.uuid4())
        status, prepared, _headers = _request(
            server,
            "POST",
            "/api/v4/packvm/prepare",
            body={},
            headers={**authenticated, "X-Tobkiri-Request-ID": request_id},
        )
        assert status == 200
        assert prepared["data"]["image_size_bytes"] == 700_000_000
        assert prepared["data"]["image_digest"] == "sha256:" + "a" * 64

        replay_status, _replay, _headers = _request(
            server,
            "POST",
            "/api/v4/packvm/prepare",
            body={},
            headers={**authenticated, "X-Tobkiri-Request-ID": request_id},
        )
        assert replay_status == 409
        assert [call[0] for call in lifecycle.calls].count("prepare") == 1

        consent_body = {
            "plan_digest": prepared["data"]["plan_digest"],
            "ceremony_nonce": prepared["data"]["ceremony_nonce"],
            "confirmation": prepared["data"]["confirmation"],
            "approve_image_download": True,
        }
        status, consent, _headers = _request(
            server,
            "POST",
            "/api/v4/packvm/consent",
            body=consent_body,
            headers={
                **authenticated,
                "X-Tobkiri-Request-ID": str(uuid.uuid4()),
            },
        )
        assert status == 200
        status, provisioned, _headers = _request(
            server,
            "POST",
            "/api/v4/packvm/provision",
            body={
                "consent_id": consent["data"]["consent_id"],
                "operation_id": "11111111-1111-4111-8111-111111111111",
            },
            headers={
                **authenticated,
                "X-Tobkiri-Request-ID": str(uuid.uuid4()),
            },
        )
        assert status == 200
        assert provisioned["data"]["state"] == "queued"
        assert refreshed == []

        status, progress, _headers = _request(
            server,
            "GET",
            "/api/v4/packvm/progress?operation_id=11111111-1111-4111-8111-111111111111",
            headers={"Cookie": cookie, "Origin": origin},
        )
        assert status == 200
        assert progress["data"]["state"] == "succeeded"

        status, cancelled, _headers = _request(
            server,
            "POST",
            "/api/v4/packvm/cancel",
            body={"operation_id": "11111111-1111-4111-8111-111111111111"},
            headers={
                **authenticated,
                "X-Tobkiri-Request-ID": str(uuid.uuid4()),
            },
        )
        assert status == 200
        assert cancelled["data"]["state"] == "cancelled"

        status, doctor, _headers = _request(
            server,
            "GET",
            "/api/v4/packvm/doctor",
            headers={"Cookie": cookie, "Origin": origin},
        )
        assert status == 200
        assert doctor["data"]["ready"] is True
        assert refreshed == [None]
    finally:
        server.stop()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_runtime_http_config_canonicalizes_loopback(host: str) -> None:
    assert RuntimeHTTPConfig.verify(host, 8765).host == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.1", "example.com"])
def test_runtime_http_config_rejects_non_loopback(host: str) -> None:
    with pytest.raises(ValueError, match="loopback-only"):
        RuntimeHTTPConfig.verify(host, 8765)


@pytest.mark.parametrize("port", [-1, 65536])
def test_runtime_http_config_rejects_invalid_port(port: int) -> None:
    with pytest.raises(ValueError, match="port"):
        RuntimeHTTPConfig.verify("127.0.0.1", port)


def test_bind_environment_has_no_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUMI_API_BIND_ADDRESS", "0.0.0.0")
    server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="verified"),
    )
    assert server.host == "127.0.0.1"


def test_production_handler_has_no_legacy_route_state() -> None:
    for name in (
        "approval_manager",
        "internal_token",
        "load_api_routes",
        "load_pack_routes",
        "load_pre_auth_routes",
        "load_web_mounts",
        "_api_route_exact",
        "_pack_routes",
        "_pre_auth_table",
        "_web_mounts",
    ):
        assert not hasattr(PackAPIHandler, name)


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/packs"),
        ("GET", "/api/authority/events"),
        ("GET", "/api/runtime/available"),
        ("POST", "/api/packs/scan"),
        ("POST", "/api/routes/reload"),
        ("PUT", "/api/packs/example"),
        ("DELETE", "/api/packs/example"),
        ("PATCH", "/api/packs/example"),
    ],
)
def test_legacy_api_roots_have_one_typed_retirement(
    live_server: tuple[PackAPIServer, _Dispatch],
    method: str,
    path: str,
) -> None:
    server, _ = live_server
    status, payload, _ = _request(
        server,
        method,
        path,
        body={} if method != "GET" else None,
        headers={"Authorization": "Bearer formerly-valid-root"},
    )
    assert status == 410
    assert payload["data"] == {
        "api_version": "io.tobkiri.pack-api.v4",
        "state": "legacy_api_retired",
        "retired_route": path,
        "write_set": [],
    }


@pytest.mark.parametrize(
    "method",
    ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
def test_setup_complete_is_method_independent_410_no_write(
    live_server: tuple[PackAPIServer, _Dispatch],
    method: str,
) -> None:
    server, _ = live_server
    status, payload, _ = _request(
        server,
        method,
        "/api/setup/complete",
        body={"username": "must-not-write"} if method != "GET" else None,
        headers={"Authorization": "Bearer formerly-valid-root"},
    )
    assert status == 410
    assert payload["data"]["state"] == "legacy_setup_retired"
    assert payload["data"]["write_set"] == []


def test_setup_complete_head_uses_header_only_410_semantics(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    connection.request(
        "HEAD",
        "/api/setup/complete",
        headers={"Authorization": "Bearer formerly-valid-root"},
    )
    response = connection.getresponse()
    assert response.status == 410
    assert response.getheader("Content-Type") == "application/json; charset=utf-8"
    assert int(response.getheader("Content-Length", "0")) > 0
    assert response.read() == b""
    connection.close()


def test_setup_complete_query_is_retired_but_trailing_slash_is_absent(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    status, payload, _ = _request(
        server,
        "GET",
        "/api/setup/complete?source=legacy",
    )
    assert status == 410
    assert payload["data"]["retired_route"] == "/api/setup/complete"
    status, payload, _ = _request(server, "GET", "/api/setup/complete/")
    assert status == 404
    assert payload["error"] == "Not found"


@pytest.mark.parametrize(
    "path",
    [
        "/api//setup/complete",
        "/api/setup/./complete",
        "/api/setup/%63omplete",
        "/api/setup/complete%2F",
    ],
)
def test_setup_complete_noncanonical_variants_remain_absent(
    live_server: tuple[PackAPIServer, _Dispatch],
    path: str,
) -> None:
    server, _ = live_server
    status, _, _ = _request(server, "GET", path)
    assert status == 404


def test_setup_complete_method_matrix_is_filesystem_immutable_across_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_data = tmp_path / "fresh-home"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="verified"),
    )
    try:
        for _cycle in (1, 2):
            server.start()
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                status, payload, _ = _request(
                    server,
                    method,
                    "/api/setup/complete?invalid_credential=yes",
                    body={"mutation": True} if method != "GET" else None,
                    headers={"Authorization": "Bearer invalid"},
                )
                assert status == 410
                assert payload["data"]["write_set"] == []
            server.stop()
        assert not user_data.exists()
        assert list(tmp_path.iterdir()) == []
    finally:
        server.stop()


def test_unknown_api_route_is_physically_absent(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    status, payload, _ = _request(server, "GET", "/api/setup/unknown")
    assert status == 404
    assert payload["error"] == "Not found"


def test_health_is_public_and_typed(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    status, payload, _ = _request(server, "GET", "/health")
    assert status == 200
    assert payload["data"] == {"status": "ok", "runtime_ready": True}


def test_panel_bootstrap_rejects_wrong_secret(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    status, _, _ = _request(
        server,
        "POST",
        "/api/panel/auth/bootstrap",
        body={},
        headers={"X-Rumi-Desktop-Bootstrap": "wrong"},
    )
    assert status == 401


def test_panel_exchange_rejects_foreign_origin(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    status, bootstrap, _ = _request(
        server,
        "POST",
        "/api/panel/auth/bootstrap",
        body={},
        headers={"X-Rumi-Desktop-Bootstrap": "verified-desktop"},
    )
    assert status == 200
    status, _, _ = _request(
        server,
        "POST",
        "/api/panel/auth/exchange",
        body={"code": bootstrap["data"]["code"]},
        headers={"Origin": "https://attacker.invalid"},
    )
    assert status == 403


def test_dispatch_requires_panel_cookie_and_csrf(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, dispatch = live_server
    body = {
        "contract_id": "pack.control.v4",
        "operation_id": "catalog.read",
        "payload": {},
    }
    status, payload, _ = _request(server, "POST", "/api/v4/dispatch", body=body)
    _assert_retired_generic_dispatch(status, payload)
    cookie, csrf, origin = _panel_session(server)
    status, payload, _ = _request(
        server,
        "POST",
        "/api/v4/dispatch",
        body=body,
        headers={"Cookie": cookie, "Origin": origin},
    )
    _assert_retired_generic_dispatch(status, payload)
    status, payload, _ = _request(
        server,
        "POST",
        "/api/v4/dispatch",
        body=body,
        headers={
            "Cookie": cookie,
            "Origin": origin,
            "X-Rumi-CSRF": csrf,
        },
    )
    _assert_retired_generic_dispatch(status, payload)
    assert dispatch.calls == []


def test_authenticated_generic_dispatch_is_retired_before_production_broker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retired generic dispatch cannot reach the production Broker or ledger."""
    user_data = tmp_path / "clean-home"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    active = capture_default_profile(confirmation=prepare_default_profile_confirmation())
    dispatch = capture_production_dispatch(
        active,
        bundle_root=Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack" / "v4",
        ecosystem_root=Path(__file__).resolve().parents[1] / "ecosystem",
        authority_store=AuthorityStore(user_data / "authority" / "v4.sqlite3"),
    )
    server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="verified-desktop"),
        dispatch_session=dispatch,
        app_lifecycle_manager=_Lifecycle(),
    )
    server.start()
    try:
        cookie, csrf, origin = _panel_session(server)
        with AuthorityStore(user_data / "authority" / "v4.sqlite3") as authority:
            audit_before = authority.audit_events()
        headers = {
            "Cookie": cookie,
            "Origin": origin,
            "X-Rumi-CSRF": csrf,
        }
        status, payload, _ = _request(
            server,
            "POST",
            "/api/v4/dispatch",
            body={
                "contract_id": "tobkiri.host.pack-control.v4",
                "operation_id": "catalog.read",
                "payload": {},
            },
            headers=headers,
        )
        _assert_retired_generic_dispatch(status, payload)

        status, payload, _ = _request(
            server,
            "POST",
            "/api/v4/dispatch",
            body={
                "contract_id": "tobkiri.host.pack-control.v4",
                "operation_id": "pack.install",
                "payload": {"pack_id": "rumi_git_read_pack"},
            },
            headers=headers,
        )
        _assert_retired_generic_dispatch(status, payload)
        with AuthorityStore(user_data / "authority" / "v4.sqlite3") as authority:
            assert authority.audit_events() == audit_before
    finally:
        server.stop()


@pytest.mark.parametrize("body", [[], "text", 1, None])
def test_dispatch_rejects_non_object_json_roots(
    live_server: tuple[PackAPIServer, _Dispatch],
    body: object,
) -> None:
    server, dispatch = live_server
    cookie, csrf, origin = _panel_session(server)
    status, payload, _ = _request(
        server,
        "POST",
        "/api/v4/dispatch",
        body=body,
        headers={
            "Cookie": cookie,
            "Origin": origin,
            "X-Rumi-CSRF": csrf,
        },
    )
    _assert_retired_generic_dispatch(status, payload)
    assert dispatch.calls == []


def test_server_restart_keeps_legacy_routes_retired(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    server.stop()
    server.start()
    status, payload, _ = _request(server, "GET", "/api/packs")
    assert status == 410
    assert payload["data"]["state"] == "legacy_api_retired"


def test_log_redaction_removes_bootstrap_code() -> None:
    redacted = PackAPIHandler._redact_log_value("/panel/?code=top-secret&x=1")
    assert redacted == "/panel/?code=[REDACTED]&x=1"
    assert "top-secret" not in redacted
