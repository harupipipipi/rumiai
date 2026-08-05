"""Live and structural tests for the finite Pack v4 HTTP boundary."""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator, Mapping

import pytest

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


def test_setup_complete_is_unconditional_410_no_write(
    live_server: tuple[PackAPIServer, _Dispatch],
) -> None:
    server, _ = live_server
    status, payload, _ = _request(
        server,
        "POST",
        "/api/setup/complete",
        body={"username": "must-not-write"},
        headers={"Authorization": "Bearer formerly-valid-root"},
    )
    assert status == 410
    assert payload["data"]["state"] == "legacy_setup_retired"
    assert payload["data"]["write_set"] == []


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
    status, _, _ = _request(server, "POST", "/api/v4/dispatch", body=body)
    assert status == 401
    cookie, csrf, origin = _panel_session(server)
    status, _, _ = _request(
        server,
        "POST",
        "/api/v4/dispatch",
        body=body,
        headers={"Cookie": cookie, "Origin": origin},
    )
    assert status == 401
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
    assert status == 200
    assert payload["data"]["operation_id"] == "catalog.read"
    assert dispatch.calls[0][0:2] == ("pack.control.v4", "catalog.read")
    assert dispatch.calls[0][2]["_session_id"]


@pytest.mark.parametrize("body", [[], "text", 1, None])
def test_dispatch_rejects_non_object_json_roots(
    live_server: tuple[PackAPIServer, _Dispatch],
    body: object,
) -> None:
    server, dispatch = live_server
    cookie, csrf, origin = _panel_session(server)
    status, _, _ = _request(
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
    assert status == 400
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
