from __future__ import annotations

import sys
from pathlib import Path
from collections import deque

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _Transport:
    def __init__(self, incoming=()):
        self.incoming = deque(incoming)
        self.sent = []
        self.closed = False

    def send(self, message):
        self.sent.append(message)

    def receive(self, timeout):
        del timeout
        if not self.incoming:
            from blocks.coding.codex_app_server import RequestTimeout

            raise RequestTimeout("empty fake transport")
        return self.incoming.popleft()

    def close(self):
        self.closed = True


def _initialized_client(incoming=(), **kwargs):
    from blocks.coding.codex_app_server import CodexAppServerClient

    transport = _Transport([{"id": 1, "result": {"platformFamily": "windows"}}, *incoming])
    client = CodexAppServerClient(transport, **kwargs)
    client.initialize(version="test")
    return client, transport


def test_codex_app_server_is_coding_backend_not_provider():
    from domain.ai_client.providers import get_provider_catalog_map
    from domain.components.registry import DomainComponentRegistry, build_domain_component_roots

    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))
    backend = registry.get("coding_backends", "codex-app-server")

    assert backend is not None
    assert backend.kind == "coding_backend"
    assert backend.as_dict()["policy"]["do_not_treat_as_llm_provider"] is True
    assert "codex-app-server" not in get_provider_catalog_map()


def test_codex_app_server_workspace_boundary_and_server_approval(tmp_path):
    from blocks.coding.codex_app_server import (
        CodexAppServerBackend,
        ServerApprovalRequiredError,
        WorkspaceBoundaryError,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inside = workspace / "notes.txt"
    inside.write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    backend = CodexAppServerBackend()
    session = backend.create_session(str(workspace), profile={"name": "test"})

    with pytest.raises(ServerApprovalRequiredError):
        backend.validate_action(
            session,
            "file.write",
            target_path=inside,
            client_supplied_approved=True,
        )

    backend.validate_action(
        session,
        "file.write",
        target_path=inside,
        context={"server_approvals": {"file.write": True}},
        client_supplied_approved=False,
    )

    with pytest.raises(WorkspaceBoundaryError):
        backend.validate_action(
            session,
            "file.write",
            target_path=outside,
            context={"server_approvals": {"file.write": True}},
        )


def test_initialize_handshake_precedes_all_other_calls():
    from blocks.coding.codex_app_server import CodexAppServerClient, ProtocolError

    transport = _Transport([{"id": 1, "result": {}}])
    client = CodexAppServerClient(transport)
    with pytest.raises(ProtocolError, match="initialize"):
        client.list_models()
    client.initialize()
    assert [message["method"] for message in transport.sent] == ["initialize", "initialized"]


def test_model_inventory_consumes_every_cursor_and_preserves_metadata():
    client, transport = _initialized_client(
        [
            {
                "id": 2,
                "result": {
                    "data": [{
                        "id": "exact/model:preview",
                        "displayName": "Exact",
                        "defaultReasoningEffort": "medium",
                        "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
                        "supportsPersonality": True,
                        "isDefault": True,
                        "upgrade": "exact/model:next",
                    }],
                    "nextCursor": "page-2",
                },
            },
            {
                "id": 3,
                "result": {
                    "data": [{"id": "hidden/model", "hidden": True, "inputModalities": ["text"]}],
                    "nextCursor": None,
                },
            },
        ]
    )
    models = client.list_models(include_hidden=True)
    assert [model["id"] for model in models] == ["exact/model:preview", "hidden/model"]
    assert models[0]["upgrade"] == "exact/model:next"
    assert models[0]["input_modalities"] == ["text", "image"]
    assert transport.sent[-1]["params"]["cursor"] == "page-2"


def test_thread_start_is_read_only_and_preserves_session_tree_identity(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    client, transport = _initialized_client(
        [
            {"id": 2, "result": {"data": [], "nextCursor": None}},
            {
                "id": 3,
                "result": {"thread": {"id": "thr_child", "sessionId": "thr_root"}},
            },
        ]
    )
    session = client.start_thread(workspace)
    assert session.thread_id == "thr_child"
    assert session.session_id == "thr_root"
    request = transport.sent[-1]
    assert request["method"] == "thread/start"
    assert request["params"]["sandbox"] == "readOnly"
    assert request["params"]["approvalPolicy"] == "unlessTrusted"


def test_permission_profile_and_legacy_sandbox_are_mutually_exclusive(tmp_path):
    from blocks.coding.codex_app_server import CodexAppServerClient

    with pytest.raises(ValueError, match="mutually exclusive"):
        CodexAppServerClient._thread_config(
            tmp_path,
            permissions="workspace-write",
            sandbox="readOnly",
        )


def test_required_mcp_failure_stops_thread_start(tmp_path):
    from blocks.coding.codex_app_server import RequiredMcpServerError

    client, transport = _initialized_client(
        [{
            "id": 2,
            "result": {
                "data": [{"name": "required-tools", "required": True, "status": "failed"}],
                "nextCursor": None,
            },
        }]
    )
    with pytest.raises(RequiredMcpServerError, match="required-tools"):
        client.start_thread(tmp_path)
    assert not any(message.get("method") == "thread/start" for message in transport.sent)


def test_server_approval_defaults_to_decline_and_uses_authority_when_present():
    requests = [
        {
            "method": "item/commandExecution/requestApproval",
            "id": "approval-1",
            "params": {"threadId": "thr", "turnId": "turn", "command": "echo ok"},
        },
        {"id": 2, "result": {"account": None}},
    ]
    client, transport = _initialized_client(requests, authority=lambda operation, _params: operation == "terminal.exec")
    client.read_account()
    response = next(message for message in transport.sent if message.get("id") == "approval-1")
    assert response["result"] == {"decision": "accept"}

    denied, denied_transport = _initialized_client()
    denied._dispatch_incoming(requests[0])
    assert denied_transport.sent[-1]["result"] == {"decision": "decline"}


def test_permission_grant_cannot_exceed_requested_subset():
    client, transport = _initialized_client(
        authority=lambda _operation, _params: {"permissions": ["network", "filesystem"]}
    )
    client._dispatch_incoming(
        {
            "method": "item/permissions/requestApproval",
            "id": "permissions-1",
            "params": {"permissions": ["network"]},
        }
    )
    assert transport.sent[-1]["result"] == {"permissions": ["network"], "scope": "turn"}


def test_auth_and_usage_notifications_are_redacted():
    client, _transport = _initialized_client()
    client._dispatch_incoming(
        {
            "method": "account/updated",
            "params": {"authMode": "chatgpt", "access_token": "secret", "planType": "pro"},
        }
    )
    assert client.account["access_token"] == "[REDACTED]"
    assert "secret" not in str(client.events)


def test_malformed_message_fails_closed():
    from blocks.coding.codex_app_server import ProtocolError

    client, _transport = _initialized_client()
    with pytest.raises(ProtocolError):
        client._dispatch_incoming({"unexpected": True})


def test_stdio_transport_process_lifecycle_is_cross_platform(tmp_path):
    from blocks.coding.codex_app_server import CodexAppServerClient, StdioJsonRpcTransport

    script = (
        "import json,sys; "
        "m=json.loads(sys.stdin.readline()); "
        "print(json.dumps({'id':m['id'],'result':{'platformFamily':sys.platform}}),flush=True); "
        "sys.stdin.readline()"
    )
    transport = StdioJsonRpcTransport(
        [sys.executable, "-u", "-c", script],
        cwd=tmp_path,
    )
    client = CodexAppServerClient(transport, timeout=3)
    result = client.initialize()
    assert result["platformFamily"] == sys.platform
    assert transport.pid > 0
    client.close()
