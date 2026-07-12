from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_APPROVAL_DB_PATH",
        str(tmp_path / "approval.sqlite3"),
    )
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CHAT_STORE_PATH",
        str(tmp_path / "chat" / "conversations.json"),
    )
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_MCP_REGISTRY_PATH",
        str(tmp_path / "mcp_servers.json"),
    )
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH",
        str(tmp_path / "workspaces.json"),
    )
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_AUDIT_PATH",
        str(tmp_path / "audit.jsonl"),
    )
    from domain.safety import approval

    approval.reset_approval_state_for_tests()
    yield
    approval.reset_approval_state_for_tests()


def _stdio_config() -> dict[str, object]:
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["fake_mcp.py"],
    }


def test_mcp_review_is_complete_and_never_persists_raw_secrets(
    tmp_path,
    monkeypatch,
):
    from blocks.tool import mcp_connect
    from domain.safety import approval

    fake_secret = "fixture-secret-never-persist"
    monkeypatch.setenv("FAKE_MCP_SECRET", fake_secret)
    result = mcp_connect.run(
        {
            "server_id": "review-server",
            "workspace_root": str(tmp_path),
            "config": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["fake_mcp.py", "--token=${FAKE_MCP_SECRET}"],
                "env": {"MCP_TOKEN": "${FAKE_MCP_SECRET}"},
                "capabilities": ["tools"],
                "tools": ["read_fixture"],
                "filesystem": {"access": "workspace"},
            },
        },
        {"approved": True, "_tool_server_approved": True},
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["approval_required"] is True
    review = data["review"]
    assert review["executable"] == sys.executable
    assert review["transport"] == "stdio"
    assert review["cwd"] == str(tmp_path.resolve())
    assert review["env"] == {"MCP_TOKEN": "<redacted>"}
    assert review["server_source"] == "inline"
    assert review["capabilities"] == ["tools"]
    assert review["tools"] == ["read_fixture"]
    assert review["network"]
    assert review["filesystem"] == {"access": "workspace"}
    assert review["persistence"]
    assert review["consequences"]
    assert fake_secret not in json.dumps(data)

    stored = approval.get_approval_request(data["approval_request_id"])
    mirror = tmp_path / "chat" / "approval_state.json"
    assert stored is not None
    assert fake_secret not in json.dumps(stored)
    assert fake_secret not in mirror.read_text(encoding="utf-8")
    assert stored["details"]["review"]["env"]["MCP_TOKEN"] == "<redacted>"


def test_mcp_token_rejects_mutation_cross_server_workspace_and_replay(
    tmp_path,
    monkeypatch,
):
    from blocks.tool import mcp_connect
    from domain.safety import approval

    workspace_a = tmp_path / "a"
    workspace_b = tmp_path / "b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    monkeypatch.setenv("FAKE_MCP_SECRET", "first-value")
    config = {
        **_stdio_config(),
        "env": {"MCP_TOKEN": "${FAKE_MCP_SECRET}"},
    }
    request_args = {
        "server_id": "scoped-server",
        "workspace_root": str(workspace_a),
        "config": config,
    }
    requested = mcp_connect.run(request_args, {})
    decision = approval.approve(requested["data"]["approval_request_id"])
    token = decision["token"]

    monkeypatch.setenv("FAKE_MCP_SECRET", "first-value")
    cross_server = mcp_connect.run(
        {
            **request_args,
            "server_id": "other-server",
            "approval_token": token,
        },
        {},
    )
    assert cross_server["error"]["code"] == "APPROVAL_ARGUMENTS_CHANGED"

    cross_workspace = mcp_connect.run(
        {
            **request_args,
            "workspace_root": str(workspace_b),
            "approval_token": token,
        },
        {},
    )
    assert cross_workspace["error"]["code"] == "APPROVAL_ARGUMENTS_CHANGED"

    class FakeClient:
        def connect(self, server_name, effective_config):
            assert server_name == "scoped-server"
            assert effective_config["env"]["MCP_TOKEN"] == "first-value"
            return 0

        def get_server_tools(self, server_name):
            return []

    monkeypatch.setattr(mcp_connect, "McpClient", FakeClient)
    connected = mcp_connect.run(
        {**request_args, "approval_token": token},
        {},
    )
    assert connected["status"] == "ok"
    replay = mcp_connect.run(
        {**request_args, "approval_token": token},
        {},
    )
    assert replay["status"] == "error"
    assert replay["error"]["code"] == "APPROVAL_TOKEN_USED"


def test_mcp_environment_change_invalidates_approved_review(tmp_path, monkeypatch):
    from blocks.tool import mcp_connect
    from domain.safety import approval

    monkeypatch.setenv("FAKE_MCP_SECRET", "before")
    args = {
        "server_id": "env-server",
        "workspace_root": str(tmp_path),
        "config": {
            **_stdio_config(),
            "env": {"MCP_TOKEN": "${FAKE_MCP_SECRET}"},
        },
    }
    requested = mcp_connect.run(args, {})
    token = approval.approve(requested["data"]["approval_request_id"])["token"]
    monkeypatch.setenv("FAKE_MCP_SECRET", "after")

    changed = mcp_connect.run({**args, "approval_token": token}, {})

    assert changed["status"] == "error"
    assert changed["error"]["code"] == "APPROVAL_ARGUMENTS_CHANGED"
    assert changed["error"]["details"]["recoverable"] is True


def test_registry_mutation_obsoletes_pending_mcp_review(tmp_path):
    from blocks.tool import mcp_connect, mcp_registry
    from domain.safety import approval

    requested = mcp_connect.run(
        {
            "server_id": "mutable-server",
            "workspace_root": str(tmp_path),
            "config": _stdio_config(),
        },
        {},
    )
    request_id = requested["data"]["approval_request_id"]

    updated = mcp_registry.run(
        {
            "_method": "POST",
            "server_id": "mutable-server",
            "transport": "stdio",
            "command": "different-command",
        },
        {},
    )

    assert updated["status"] == "ok"
    assert approval.get_approval_request(request_id)["status"] == "obsolete"
    settled = approval.approve(request_id)
    assert settled["approved"] is False
    assert settled["status"] == "obsolete"


def test_approval_settlement_is_single_winner_and_already_settled():
    from domain.safety import approval

    request = approval.create_approval_request(
        "tool.mcp_connect",
        "high",
        {"scope": "fixture"},
    )
    results = []
    barrier = threading.Barrier(3)

    def approve_request():
        barrier.wait()
        results.append(approval.approve(request["request_id"]))

    def deny_request():
        barrier.wait()
        results.append(approval.deny(request["request_id"], "fixture denial"))

    approve_thread = threading.Thread(target=approve_request)
    deny_thread = threading.Thread(target=deny_request)
    approve_thread.start()
    deny_thread.start()
    barrier.wait()
    approve_thread.join()
    deny_thread.join()

    statuses = {result["status"] for result in results}
    assert statuses in ({"approved"}, {"denied"})
    assert sum(bool(result["approved"]) for result in results) <= 1
    repeated = approval.approve(request["request_id"])
    assert repeated["approved"] is False
    assert "already settled" in repeated["reason"] or repeated["status"] == "denied"


def test_token_consumption_cannot_overwrite_concurrent_obsolete_transition(tmp_path):
    from domain.safety.approval_store import ApprovalStore

    path = tmp_path / "race.sqlite3"
    first = ApprovalStore(path)
    second = ApprovalStore(path)
    request = {
        "request_id": "apr_race_fixture",
        "operation": "tool.mcp_connect",
        "risk_level": "high",
        "args_hash": "fixture-args-hash",
        "details": {},
        "created_at": 1,
        "expires_at": 9999999999,
        "status": "approved",
        "decision_at": 2,
    }
    first.save_request(request)
    barrier = threading.Barrier(3)
    results: dict[str, bool] = {}

    def consume():
        barrier.wait()
        results["consumed"] = first.mark_token_used(
            "tok_race_fixture",
            request["request_id"],
            request["operation"],
            request["args_hash"],
        )

    def obsolete():
        barrier.wait()
        results["obsoleted"] = second.settle_request(
            request["request_id"],
            "obsolete",
            allowed_statuses=("approved",),
        )[0]

    consume_thread = threading.Thread(target=consume)
    obsolete_thread = threading.Thread(target=obsolete)
    consume_thread.start()
    obsolete_thread.start()
    barrier.wait()
    consume_thread.join()
    obsolete_thread.join()

    assert sum(results.values()) == 1
    final = first.get_request(request["request_id"])
    assert final is not None
    assert final["status"] == ("consumed" if results["consumed"] else "obsolete")


def test_mcp_start_failure_is_recoverable_and_requires_fresh_approval(
    tmp_path,
    monkeypatch,
):
    from blocks.tool import mcp_connect
    from domain.safety import approval
    from domain.tool.mcp_registry import McpRegistry

    args = {
        "server_id": "failing-server",
        "workspace_root": str(tmp_path),
        "config": _stdio_config(),
    }
    requested = mcp_connect.run(args, {})
    token = approval.approve(requested["data"]["approval_request_id"])["token"]

    class FailingClient:
        def connect(self, server_name, effective_config):
            raise RuntimeError("fixture failure with no secrets")

    monkeypatch.setattr(mcp_connect, "McpClient", FailingClient)
    failed = mcp_connect.run({**args, "approval_token": token}, {})

    assert failed["status"] == "error"
    assert failed["error"]["code"] == "MCP_CONNECT_ERROR"
    assert failed["error"]["details"] == {
        "recoverable": True,
        "action": "retry_connection",
        "requires_new_approval": True,
        "server_id": "failing-server",
    }
    persisted = McpRegistry().get_server("failing-server")
    assert persisted["status"] == "failed"
    assert persisted["permissions"]["approved"] is False

    replay = mcp_connect.run({**args, "approval_token": token}, {})
    assert replay["error"]["code"] == "APPROVAL_TOKEN_USED"
    fresh = mcp_connect.run(args, {})
    assert fresh["data"]["approval_required"] is True
    assert fresh["data"]["approval_request_id"] != requested["data"]["approval_request_id"]
