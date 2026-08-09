"""Real loopback coverage for the selected Media Inspect Pack contribution."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import pytest

from core_runtime.authority.v4 import AuthorityStore
from core_runtime.bootstrap.production_v4 import capture_production_dispatch
from core_runtime.bootstrap.profile_capture import (
    capture_default_profile,
    prepare_default_profile_confirmation,
)
from core_runtime.frontend_contract_routes import load_frontend_contract_bindings
from core_runtime.pack_api_server import PackAPIServer
from core_runtime.pack_control_v4 import (
    PACK_CONTROL_CONTRACT,
    capture_pack_catalog_reader,
    capture_pack_control_session,
)
from core_runtime.panel_auth import PanelAuthManager
from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog
from ecosystem.rumi_file_inspect_pack.runtime.inspect import FileInspectService
from ecosystem.rumi_media_inspect_service_pack.runtime.inspect import (
    MediaInspectService,
)
from ecosystem.rumi_workspace_mount_pack.runtime.mounts import WorkspaceMountStore
from tobkiri_host.backends import (
    REQUIRED_PRODUCTION_GATES,
    BackendRegistry,
    BackendStatus,
)
from tobkiri_host.effects import ProviderOutcome
from tobkiri_host.models import ExecutionKind, OpaqueAuthorityRef, RuntimeEvidence
from tobkiri_protocol.canonical import canonical_digest


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = RUNTIME_ROOT / "ecosystem" / "defaultspack" / "v4"
MAP_PATH = (
    RUNTIME_ROOT
    / "ecosystem"
    / "defaultspack"
    / "defaultspack"
    / "frontend_contract_map.v4.json"
)
MEDIA_PACK = "rumi_media_inspect_service_pack"
MEDIA_CONTRACT = "tobkiri.service.media.inspect.v1"
MEDIA_OPERATION = "rumi_media_inspect_service_pack.media-inspect"
FILE_CONTRACT = "tobkiri.service.file.inspect.v1"
FILE_OPERATION = "rumi_file_inspect_pack.file-inspect"
WORKSPACE_CONTRACT = "tobkiri.resource.workspace.v1"


def _contract(method: str, path: str) -> str:
    return "/api/contracts/defaultspack/" + quote(
        f"{method.upper()} {path}", safe=""
    )


class _WorkspaceClient:
    def __init__(self, store: WorkspaceMountStore) -> None:
        self.store = store

    def invoke(
        self,
        contract_id: str,
        operation_id: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        assert contract_id == WORKSPACE_CONTRACT
        if operation_id == "get":
            mount = self.store.get(str(payload["workspace_id"]))
            if mount is None:
                raise KeyError("workspace mount is unknown")
            return mount
        if operation_id == "list":
            return self.store.snapshot()
        raise AssertionError(operation_id)


def _workspace_binding(store: WorkspaceMountStore) -> dict[str, Any]:
    mount = store.get("defaults")
    assert mount is not None
    root = Path(str(mount["root_path"])).resolve(strict=True)
    root_stat = root.stat()
    binding: dict[str, Any] = {
        "workspace_id": "defaults",
        "access": "read_only",
        "mount_revision": str(
            mount.get("revision")
            or mount.get("updated_at_ms")
            or mount.get("updated_at")
            or ""
        ),
        "canonical_root": str(root),
        "root_st_dev": int(root_stat.st_dev),
        "root_st_ino": int(root_stat.st_ino),
    }
    binding["root_identity"] = hashlib.sha256(
        json.dumps(
            binding,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return binding


class _BrokerMediaClient:
    def __init__(
        self,
        backend: "_MediaBackend",
        session_id: str,
        binding: Mapping[str, Any],
    ) -> None:
        self.backend = backend
        self.session_id = session_id
        self.binding = dict(binding)

    def invoke(
        self,
        contract_id: str,
        operation_id: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if contract_id != FILE_CONTRACT:
            raise AssertionError(contract_id)
        return self.backend.session.invoke(
            FILE_CONTRACT,
            FILE_OPERATION,
            {
                **dict(payload),
                "_file_operation": operation_id,
                "_workspace_binding": self.binding,
                "_session_id": self.session_id,
            },
        )


class _MediaBackend:
    """Production-gated PackVM harness executing the real read-only services."""

    def __init__(
        self,
        store: WorkspaceMountStore,
        binding: Mapping[str, Any],
    ) -> None:
        self.status = BackendStatus(
            backend_id="tobkiri.python-pack-v4",
            execution_kind=ExecutionKind.PACK_VM,
            platform="any",
            backend_digest=canonical_digest({"backend": "media-test-v4"}),
            production_enabled=True,
            conformance_only=False,
            satisfied_gates=REQUIRED_PRODUCTION_GATES,
        )
        self.store = store
        self.binding = dict(binding)
        self.session: Any = None
        self.target_domains: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def materialize(self, binding: Any, reservation_id: str) -> RuntimeEvidence:
        del reservation_id
        return RuntimeEvidence(
            domain_ref=OpaqueAuthorityRef(
                self.target_domains[binding.principal_ref.value]
            ),
            executable_digest=binding.function.implementation_digest,
            backend_digest=self.status.backend_digest,
            authenticated_channel=True,
            nonce_fresh=True,
        )

    def invoke(self, request: Any) -> ProviderOutcome:
        self.calls.append((request.contract_id, request.operation_id))
        if request.contract_id == MEDIA_CONTRACT:
            client = _BrokerMediaClient(
                self,
                request.context.caller_session_id,
                self.binding,
            )
            result = MediaInspectService(client).invoke(
                str(request.payload.get("name") or ""),
                request.payload,
            )
            return ProviderOutcome(result)
        if request.contract_id == FILE_CONTRACT:
            payload = dict(request.payload)
            operation = str(payload.pop("_file_operation", ""))
            result = FileInspectService(_WorkspaceClient(self.store)).invoke(
                operation,
                payload,
            )
            return ProviderOutcome(result)
        raise AssertionError((request.contract_id, request.operation_id))

    def cancel(self, request_id: str) -> None:
        del request_id

    def terminate(self, domain_id: str) -> None:
        del domain_id


@pytest.fixture
def media_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    user_data = tmp_path / "user-data"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.png").write_bytes(b"\x89PNG\r\n")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    try:
        (workspace / "outside-link.png").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    store = WorkspaceMountStore("defaults", user_data_root=user_data)
    mounted = store.mount("defaults", str(workspace), expected_revision=0)
    store.select("defaults", expected_revision=int(mounted["revision"]))
    binding = _workspace_binding(store)

    active = capture_default_profile(confirmation=prepare_default_profile_confirmation())
    control = capture_pack_control_session()
    control.invoke(
        PACK_CONTROL_CONTRACT,
        "pack.install",
        {"pack_id": MEDIA_PACK, "_session_id": "setup"},
    )
    candidate = control.invoke(
        PACK_CONTROL_CONTRACT,
        "approval.candidate",
        {"pack_id": MEDIA_PACK, "_session_id": "setup"},
    )
    control.invoke(
        PACK_CONTROL_CONTRACT,
        "approval.approve",
        {
            "pack_id": MEDIA_PACK,
            "candidate_id": candidate["candidate_id"],
            "_session_id": "setup",
        },
    )
    control.invoke(
        PACK_CONTROL_CONTRACT,
        "pack.enable",
        {"pack_id": MEDIA_PACK, "_session_id": "setup"},
    )
    active = capture_default_profile()

    backend = _MediaBackend(store, binding)
    authority = AuthorityStore(user_data / "authority" / "v4.sqlite3")
    session = capture_production_dispatch(
        active,
        bundle_root=BUNDLE_ROOT,
        ecosystem_root=RUNTIME_ROOT / "ecosystem",
        authority_store=authority,
        backends=BackendRegistry((backend,)),
    )
    for contract_id, operation_id in (
        (MEDIA_CONTRACT, MEDIA_OPERATION),
        (FILE_CONTRACT, FILE_OPERATION),
    ):
        context = session.context_for(contract_id, operation_id, "preflight")
        resolved = session.broker._catalog.resolve(
            contract_id,
            operation_id,
            ">=1,<2",
        )
        backend.target_domains[resolved.principal_ref.value] = context.target_domain_id
    backend.session = session

    catalog = BundledCatalog.load(BUNDLE_ROOT)
    bindings = load_frontend_contract_bindings(
        MAP_PATH,
        catalog.packs["runtime.tauri.application.default"],
    )
    server = PackAPIServer(
        port=0,
        panel_auth_manager=PanelAuthManager(bootstrap_secret="media-test-secret"),
        dispatch_session=session,
        contract_bindings=bindings,
    )
    server.start()
    try:
        yield server, session, control, backend, authority
    finally:
        server.stop()
        session.close()


def _request(
    server: PackAPIServer,
    method: str,
    path: str,
    *,
    body: object | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, Any], list[tuple[str, str]]]:
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=15)
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


def _authenticated(server: PackAPIServer) -> dict[str, str]:
    origin = f"http://127.0.0.1:{server.port}"
    status, bootstrap, _ = _request(
        server,
        "POST",
        "/api/panel/auth/bootstrap",
        body={},
        headers={"X-Rumi-Desktop-Bootstrap": "media-test-secret"},
    )
    assert status == 200, bootstrap
    status, exchange, response_headers = _request(
        server,
        "POST",
        "/api/panel/auth/exchange",
        body={"code": bootstrap["data"]["code"]},
        headers={"Origin": origin},
    )
    assert status == 200, exchange
    cookie = next(
        value for key, value in response_headers if key.lower() == "set-cookie"
    ).split(";", 1)[0]
    return {
        "Cookie": cookie,
        "Origin": origin,
        "X-Rumi-CSRF": str(exchange["data"]["csrf_token"]),
    }


def _dynamic_request(
    server: PackAPIServer,
    headers: Mapping[str, str],
    host: Mapping[str, Any],
    target: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    request_id: str | None = None,
) -> tuple[int, dict[str, Any]]:
    request_id = request_id or str(uuid.uuid4())
    body = {
        "request_id": str(uuid.uuid4()),
        "expires_at": time.time() + 30,
        "profile_id": host["profile_id"],
        "plan_hash": host["plan_hash"],
        "catalog_hash": host["catalog_hash"],
        "contribution_id": target["contribution_id"],
        "owner_pack_id": target["owner_pack_id"],
        "contract_id": target["action_contract"],
        "payload": dict(payload),
    }
    status, result, _ = _request(
        server,
        "POST",
        _contract("POST", "/api/ui/capability/invoke"),
        body=body,
        headers={**headers, "X-Tobkiri-Request-ID": request_id},
    )
    return status, result


def test_media_catalog_and_real_loopback_broker_invoke(media_server) -> None:
    """The selected Pack projects exact metadata and invokes file.inspect via Broker."""

    server, session, _control, backend, authority = media_server
    row = next(
        item
        for item in capture_pack_catalog_reader().read()["packs"]
        if item["pack_id"] == MEDIA_PACK
    )
    assert row["enabled"] is True
    assert row["approved"] is True
    assert {item["name"] for item in row["capabilities"]} == {
        "file.inspect",
        "media.inspect",
    }
    operation = next(
        item for item in row["invokable_operations"] if item["contract_id"] == MEDIA_CONTRACT
    )
    assert operation["operation_id"] == MEDIA_OPERATION

    headers = _authenticated(server)
    status, catalog, _ = _request(
        server,
        "GET",
        _contract("GET", "/api/ui/catalog"),
        headers={**headers, "X-Tobkiri-Request-ID": str(uuid.uuid4())},
    )
    assert status == 200, catalog
    host = catalog["data"]["dynamic_host"]
    target = next(
        item
        for item in host["contributions"]
        if item["owner_pack_id"] == MEDIA_PACK
    )
    assert target["action_contract"] == MEDIA_CONTRACT
    assert target["operation_id"] == MEDIA_OPERATION
    assert target["owner_pack_hash"] == row["artifact_digest"]

    status, result = _dynamic_request(
        server,
        headers,
        host,
        target,
        {"name": "image.inspect", "path": "sample.png"},
    )
    assert status == 200, result
    assert result["data"]["success"] is True
    assert result["data"]["path"] == "sample.png"
    assert (MEDIA_CONTRACT, MEDIA_OPERATION) in backend.calls
    assert (FILE_CONTRACT, FILE_OPERATION) in backend.calls
    assert authority.audit_events()[-1]["event_state"] == "committed"


def test_media_invoke_rejects_path_contribution_and_replay_boundaries(media_server) -> None:
    """Traversal, symlink escape, wrong selection, stale capture, and replay fail closed."""

    server, _session, control, backend, _authority = media_server
    headers = _authenticated(server)
    status, catalog, _ = _request(
        server,
        "GET",
        _contract("GET", "/api/ui/catalog"),
        headers={**headers, "X-Tobkiri-Request-ID": str(uuid.uuid4())},
    )
    assert status == 200
    host = catalog["data"]["dynamic_host"]
    target = next(
        item
        for item in host["contributions"]
        if item["owner_pack_id"] == MEDIA_PACK
    )

    for path in ("../outside.png", "/outside.png", "sub\\outside.png"):
        status, result = _dynamic_request(
            server,
            headers,
            host,
            target,
            {"name": "image.inspect", "path": path},
        )
        assert status == 400, result
        assert result["data"]["code"] == "invalid_contract_payload"

    status, result = _dynamic_request(
        server,
        headers,
        host,
        target,
        {"name": "image.inspect", "path": "outside-link.png"},
    )
    assert status == 409, result

    wrong = {
        **target,
        "owner_pack_id": "defaultspack",
    }
    status, _ = _dynamic_request(
        server,
        headers,
        host,
        wrong,
        {"name": "image.inspect", "path": "sample.png"},
    )
    assert status == 404

    replay_id = str(uuid.uuid4())
    status, result = _dynamic_request(
        server,
        headers,
        host,
        target,
        {"name": "image.inspect", "path": "sample.png"},
        request_id=replay_id,
    )
    assert status == 200, result
    calls_after_first = len(backend.calls)
    status, replay = _dynamic_request(
        server,
        headers,
        host,
        target,
        {"name": "image.inspect", "path": "sample.png"},
        request_id=replay_id,
    )
    assert status == 409, replay
    assert len(backend.calls) == calls_after_first

    control.invoke(
        PACK_CONTROL_CONTRACT,
        "pack.disable",
        {"pack_id": MEDIA_PACK, "_session_id": "lifecycle"},
    )
    status, stale = _dynamic_request(
        server,
        headers,
        host,
        target,
        {"name": "image.inspect", "path": "sample.png"},
    )
    assert status == 404, stale
