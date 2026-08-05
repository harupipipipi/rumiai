"""Real-server proof for the production frontend-to-Broker contract path."""

from __future__ import annotations

import http.client
import json
import time
import uuid
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

import pytest

from core_runtime.authority.v4 import AuthorityStore
from core_runtime.bootstrap.production_v4 import capture_production_dispatch
from core_runtime.bootstrap.profile_capture import (
    capture_default_profile,
    prepare_default_profile_confirmation,
)
from core_runtime.frontend_contract_routes import load_frontend_contract_bindings
from core_runtime.frontend_contract_routes import (
    FrontendContractBinding,
    FrontendContractTarget,
)
from core_runtime.pack_api_server import PackAPIServer
from core_runtime.panel_auth import PanelAuthManager
from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog
from tobkiri_host.backends import BackendRegistry
from tobkiri_host.errors import BackendUnavailableError


pytestmark = pytest.mark.contract


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = RUNTIME_ROOT / "ecosystem" / "defaultspack" / "v4"
MAP_PATH = (
    RUNTIME_ROOT / "ecosystem" / "defaultspack" / "defaultspack" / "frontend_contract_map.v4.json"
)


def _contract(method: str, target: str) -> str:
    return "/api/contracts/defaultspack/" + quote(f"{method.upper()} {target}", safe="")


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
    payload = json.loads(response.read().decode("utf-8"))
    response_headers = response.getheaders()
    connection.close()
    return response.status, payload, response_headers


def _authenticate(server: PackAPIServer) -> tuple[str, str, str]:
    origin = f"http://127.0.0.1:{server.port}"
    status, bootstrap, _headers = _request(
        server,
        "POST",
        "/api/panel/auth/bootstrap",
        body={},
        headers={"X-Rumi-Desktop-Bootstrap": "desktop-bootstrap"},
    )
    assert status == 200, bootstrap
    status, exchange, headers = _request(
        server,
        "POST",
        "/api/panel/auth/exchange",
        body={"code": bootstrap["data"]["code"]},
        headers={"Origin": origin},
    )
    assert status == 200
    cookie = next(value for key, value in headers if key.lower() == "set-cookie")
    return cookie.split(";", 1)[0], str(exchange["data"]["csrf_token"]), origin


@pytest.fixture
def production_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    user_data = tmp_path / "user-data"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    active = capture_default_profile(confirmation=prepare_default_profile_confirmation())
    authority = AuthorityStore(user_data / "authority" / "v4.sqlite3")
    session = capture_production_dispatch(
        active,
        bundle_root=BUNDLE_ROOT,
        ecosystem_root=RUNTIME_ROOT / "ecosystem",
        authority_store=authority,
    )
    catalog = BundledCatalog.load(BUNDLE_ROOT)
    bindings = load_frontend_contract_bindings(
        MAP_PATH,
        catalog.packs["runtime.tauri.application.default"],
    )
    server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="desktop-bootstrap"),
        dispatch_session=session,
        contract_bindings=bindings,
    )
    server.start()
    try:
        yield server, session, authority
    finally:
        server.stop()
        session.broker.close()


def test_home_and_pack_workflow_use_only_real_broker_contracts(
    production_server,
) -> None:
    server, _session, authority = production_server
    cookie, csrf, origin = _authenticate(server)
    read_headers = {
        "Cookie": cookie,
        "X-Tobkiri-Request-ID": str(uuid.uuid4()),
    }
    before = len(authority.audit_events())
    status, dashboard, _ = _request(
        server,
        "GET",
        _contract("GET", "/api/home/dashboard"),
        headers=read_headers,
    )
    assert status == 200
    assert dashboard["data"]["kernel"]["status"] == "running"
    events = authority.audit_events()
    assert len(events) == before + 4
    assert [event["event_state"] for event in events[-3:]] == [
        "reserved",
        "dispatched",
        "committed",
    ]

    status, catalog, _ = _request(
        server,
        "GET",
        _contract("GET", "/api/pack-control/catalog"),
        headers={**read_headers, "X-Tobkiri-Request-ID": str(uuid.uuid4())},
    )
    assert status == 200
    assert catalog["data"]["profile_id"] == "defaults"

    status, ui_catalog, _ = _request(
        server,
        "GET",
        _contract("GET", "/api/ui/catalog"),
        headers={**read_headers, "X-Tobkiri-Request-ID": str(uuid.uuid4())},
    )
    assert status == 200
    dynamic_host = ui_catalog["data"]["dynamic_host"]
    status_contribution = next(
        item for item in dynamic_host["contributions"] if item["label"] == "pack.status"
    )

    mutation_headers = {
        "Cookie": cookie,
        "Origin": origin,
        "X-Rumi-CSRF": csrf,
    }

    audit_before_capability = len(authority.audit_events())
    status, capability_result, _ = _request(
        server,
        "POST",
        _contract("POST", "/api/ui/capability/invoke"),
        body={
            "request_id": str(uuid.uuid4()),
            "expires_at": time.time() + 30,
            "profile_id": dynamic_host["profile_id"],
            "plan_hash": dynamic_host["plan_hash"],
            "catalog_hash": dynamic_host["catalog_hash"],
            "contribution_id": status_contribution["contribution_id"],
            "owner_pack_id": status_contribution["owner_pack_id"],
            "contract_id": status_contribution["action_contract"],
            "payload": {"pack_id": "defaultspack"},
        },
        headers={
            **mutation_headers,
            "X-Tobkiri-Request-ID": str(uuid.uuid4()),
        },
    )
    assert status == 200, capability_result
    assert capability_result["data"]["pack_id"] == "defaultspack"
    assert len(authority.audit_events()) == audit_before_capability + 3

    def post(target: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
        status_code, payload, _ = _request(
            server,
            "POST",
            _contract("POST", target),
            body=body,
            headers={
                **mutation_headers,
                "X-Tobkiri-Request-ID": str(uuid.uuid4()),
            },
        )
        return status_code, payload

    target_pack = "rumi_git_read_pack"
    assert post("/api/pack-control/install", {"pack_id": target_pack})[0] == 200
    candidate_status, candidate = post(
        "/api/pack-control/approval-candidate", {"pack_id": target_pack}
    )
    assert candidate_status == 200
    assert (
        post(
            "/api/pack-control/approval-approve",
            {
                "pack_id": target_pack,
                "candidate_id": candidate["data"]["candidate_id"],
            },
        )[0]
        == 200
    )
    assert post("/api/pack-control/enable", {"pack_id": "defaultspack"})[0] == 200
    assert post("/api/pack-control/disable", {"pack_id": target_pack})[0] == 200
    assert post("/api/pack-control/restart", {})[0] == 200

    audit_before_legacy = len(authority.audit_events())
    status, retired, _ = _request(
        server,
        "GET",
        "/api/panel/dashboard",
        headers={"Cookie": cookie},
    )
    assert status == 410
    assert retired["data"]["state"] == "legacy_api_retired"
    assert len(authority.audit_events()) == audit_before_legacy


def test_contract_replay_unknown_and_stale_capture_fail_closed(
    production_server,
) -> None:
    server, session, authority = production_server
    cookie, _csrf, _origin = _authenticate(server)
    request_id = str(uuid.uuid4())
    path = _contract("GET", "/api/home/dashboard")
    headers = {"Cookie": cookie, "X-Tobkiri-Request-ID": request_id}
    first = _request(server, "GET", path, headers=headers)
    assert first[0] == 200, first[1]
    audit_after_first = len(authority.audit_events())
    assert _request(server, "GET", path, headers=headers)[0] == 409
    assert len(authority.audit_events()) == audit_after_first

    traversal = "/api/contracts/defaultspack/GET%20%2Fapi%2F..%2Fsecrets"
    assert (
        _request(
            server,
            "GET",
            traversal,
            headers={"Cookie": cookie, "X-Tobkiri-Request-ID": str(uuid.uuid4())},
        )[0]
        == 400
    )
    assert len(authority.audit_events()) == audit_after_first

    assert (
        _request(
            server,
            "GET",
            "/api/ui/catalog",
            headers={"Cookie": cookie},
        )[0]
        == 404
    )
    assert len(authority.audit_events()) == audit_after_first

    unknown = _contract("GET", "/api/pack-control/not-selected")
    assert (
        _request(
            server,
            "GET",
            unknown,
            headers={"Cookie": cookie, "X-Tobkiri-Request-ID": str(uuid.uuid4())},
        )[0]
        == 404
    )
    assert len(authority.audit_events()) == audit_after_first

    authority.advance_security_epoch("test stale frontend capture")
    stale_server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="other"),
        dispatch_session=session,
        contract_bindings=tuple(server._contract_routes.values()),
    )
    with pytest.raises(Exception, match="stale|epoch"):
        stale_server.start()
    assert stale_server.server is None


def test_contract_server_rejects_missing_or_wrong_capture_before_bind(
    production_server,
) -> None:
    server, session, _authority = production_server
    bindings = tuple(server._contract_routes.values())
    missing = PackAPIServer(port=0, contract_bindings=bindings)
    with pytest.raises(RuntimeError, match="captured v4 session"):
        missing.start()
    assert missing.server is None

    route = bindings[0]
    target = route.targets[0]
    wrong_target = FrontendContractTarget(
        contribution_id=target.contribution_id,
        contract_id=target.contract_id,
        operation_id=target.operation_id,
        provider_id="unselected.provider",
        function_id="unselected.provider",
        allowed_payload_keys=target.allowed_payload_keys,
    )
    wrong_binding = FrontendContractBinding(
        method=route.method,
        path=route.path,
        presentation=route.presentation,
        targets=(wrong_target,),
    )
    wrong = PackAPIServer(
        port=0,
        dispatch_session=session,
        contract_bindings=(wrong_binding,),
    )
    with pytest.raises(RuntimeError, match="Provider identity"):
        wrong.start()
    assert wrong.server is None


def test_contract_server_rejects_empty_and_wrong_backend_registry_before_bind(
    production_server,
) -> None:
    server, session, _authority = production_server
    bindings = tuple(server._contract_routes.values())
    selected_backends = session.broker._backends

    session.broker._backends = BackendRegistry(())
    empty = PackAPIServer(
        port=0,
        dispatch_session=session,
        contract_bindings=bindings,
    )
    with pytest.raises(BackendUnavailableError, match="not installed"):
        empty.start()
    assert empty.server is None

    selected = selected_backends.registered[0]
    original_status = selected.status
    selected.status = type(original_status)(
        backend_id=original_status.backend_id,
        execution_kind=original_status.execution_kind,
        platform=original_status.platform,
        backend_digest="sha256:" + "0" * 64,
        production_enabled=True,
        conformance_only=False,
        satisfied_gates=original_status.satisfied_gates,
    )
    session.broker._backends = BackendRegistry((selected,))
    wrong = PackAPIServer(
        port=0,
        dispatch_session=session,
        contract_bindings=bindings,
    )
    with pytest.raises(RuntimeError, match="metadata is stale or wrong"):
        wrong.start()
    assert wrong.server is None

    selected.status = original_status
    session.broker._backends = selected_backends
    exact = PackAPIServer(
        port=0,
        dispatch_session=session,
        contract_bindings=bindings,
    )
    exact._validate_contract_runtime()
    assert exact.server is None


def test_selected_desktop_entrypoint_has_no_compatibility_server_authority() -> None:
    desktop = (
        RUNTIME_ROOT / "ecosystem" / "defaultspack" / "defaultspack" / "desktop_app.py"
    ).read_text(encoding="utf-8")
    assert "DefaultsHttpServer" not in desktop
    assert "transport.http" not in desktop
    assert "build_fallback_http_routes" not in desktop
