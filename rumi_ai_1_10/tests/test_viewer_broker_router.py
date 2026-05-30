from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_viewer_broker_client_reads_env_url_and_token(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_URL", "http://127.0.0.1:8770")
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_TOKEN", "secret-token")

    client = ViewerBrokerClient.from_environment()

    assert client.available() is True
    assert client.url == "http://127.0.0.1:8770"
    assert client.token == "secret-token"


def test_viewer_broker_client_reads_connection_json(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    connection = tmp_path / "host_broker" / "connection.json"
    connection.parent.mkdir(parents=True, exist_ok=True)
    connection.write_text(
        json.dumps({"url": "http://127.0.0.1:8771", "token": "file-token"}),
        encoding="utf-8",
    )
    monkeypatch.delenv("RUMI_VIEWER_HOST_BROKER_URL", raising=False)
    monkeypatch.delenv("RUMI_VIEWER_HOST_BROKER_TOKEN", raising=False)
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_CONNECTION", str(connection))

    client = ViewerBrokerClient.from_environment()

    assert client.available() is True
    assert client.url == "http://127.0.0.1:8771"
    assert client.token == "file-token"


def test_computer_router_routes_darwin_computer_calls_to_viewer(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {"action": function_id, "routed": True, "payload": dict(args), "context": dict(context or {})}

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "approval_token": "tok"},
        {"conversation_id": "conv_1"},
    )

    assert result["routed"] is True
    assert result["action"] == "computer.click"
    assert result["context"]["conversation_id"] == "conv_1"


def test_computer_router_uses_context_token_for_viewer_approval(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {"action": function_id, "approval_token_seen": args.get("approval_token")}

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10},
        {"tool_approval_tokens": {"computer.click": "tok_ctx"}},
        tool_name="computer_use",
    )

    assert result["approval_token_seen"] == "tok_ctx"


def test_computer_router_skips_viewer_for_internal_host_execution(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    captured: dict[str, object] = {}

    def fake_run(self, action, payload, *, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["yolo_mode"] = yolo_mode
        return {"action": action, "local": True}

    monkeypatch.setenv("RUMI_COMPUTER_HOST_INTERNAL", "1")
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "run", fake_run)

    result = computer_router.run_computer_action(
        "computer.type",
        {"text": "hello"},
        {"conversation_id": "conv_1"},
        artifact_root=tmp_path,
        yolo_mode=True,
    )

    assert result["local"] is True
    assert captured["action"] == "computer.type"
    assert captured["payload"] == {"text": "hello"}
    assert captured["yolo_mode"] is True


def test_computer_router_returns_recovery_when_viewer_is_unavailable(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return False

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action("computer.screenshot", {}, {})

    assert result["is_error"] is True
    assert result["permission_subject"] == "Rumi Viewer"
    assert "Open Rumi Viewer" in result["recovery"]["note"]


def test_computer_router_returns_recovery_when_viewer_connection_is_stale(monkeypatch, tmp_path):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action("computer.screenshot", {}, {}, artifact_root=tmp_path)

    assert result["is_error"] is True
    assert "unavailable" in result["reason"]
    assert result["permission_subject"] == "Rumi Viewer"


def test_viewer_broker_client_includes_artifact_root_in_run_request(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = dict(payload or {})
        return {"ok": True, "result": {"action": "computer.screenshot"}}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    client.run_computer("computer.screenshot", {}, context={"conversation_id": "conv_1"}, artifact_root=tmp_path)

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/host/computer/run"
    assert captured["payload"]["artifact_root"] == str(tmp_path)


def test_viewer_broker_client_preserves_approval_payload_from_broker(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    def fake_request(self, method, path, payload=None):
        return {
            "ok": False,
            "audit_id": "host-audit-1",
            "result": {
                "action": "computer.click",
                "requires_approval": True,
                "approval_token": "tok",
            },
            "error": {"code": "APPROVAL_REQUIRED", "message": "Approval required."},
        }

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    result = client.run_computer("computer.click", {"x": 10})

    assert result["requires_approval"] is True
    assert result["approval_token"] == "tok"
    assert result["error_code"] == "APPROVAL_REQUIRED"
    assert result["host_audit_id"] == "host-audit-1"


def test_computer_router_wraps_viewer_approval_into_request_id(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {
                "action": function_id,
                "requires_approval": True,
                "approval_token": "viewer_tok",
                "approval_hint": "approval required",
            }

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "y": 20},
        {"conversation_id": "conv_1"},
        tool_name="computer_use",
    )

    assert result["requires_approval"] is True
    assert result["approval_required"] is True
    assert result["tool_name"] == "computer_use"
    assert result["operation"] == "computer.click"
    assert result["payload"] == {"x": 10, "y": 20}
    assert str(result["approval_request_id"]).startswith("apr_")
    assert result["message"] == "approval required"


def test_tool_executor_routes_local_computer_tools_through_router(monkeypatch):
    from domain.tool.executor import ToolExecutor
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, tool_name="computer_use", artifact_root=None, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["context"] = dict(context or {})
        captured["tool_name"] = tool_name
        return {"action": action, "ok": True}

    monkeypatch.setattr(computer_router, "run_computer_action", fake_router)

    result = ToolExecutor()._execute_local(
        "computer_use",
        {"action": "click", "x": 10, "y": 20},
        {"conversation_id": "conv_1"},
    )

    assert result["is_error"] is False
    assert captured["action"] == "computer.click"
    assert captured["payload"]["x"] == 10
    assert captured["payload"]["y"] == 20
    assert captured["tool_name"] == "computer_use"
    assert captured["context"]["conversation_id"] == "conv_1"


def test_computer_host_helper_accepts_workspace_artifact_root(monkeypatch, tmp_path):
    from core_runtime.host_broker import computer_host_helper

    chat_store_path = tmp_path / "chat" / "conversations.json"
    artifact_root = chat_store_path.parent / "conversations" / "conv-1" / "workspace" / "tools" / "computer"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(chat_store_path))

    result = computer_host_helper._validated_artifact_root(str(artifact_root))

    assert result == artifact_root.resolve()


def test_computer_host_helper_rejects_non_workspace_artifact_root(tmp_path):
    from core_runtime.host_broker import computer_host_helper

    invalid_root = tmp_path / "rogue" / "computer"

    try:
        computer_host_helper._validated_artifact_root(str(invalid_root))
    except ValueError as exc:
        assert "artifact_root" in str(exc)
    else:  # pragma: no cover - safety net for explicit failure messaging
        raise AssertionError("expected artifact_root validation to fail")


def test_defaultspack_browser_computer_block_uses_router(monkeypatch):
    import ecosystem.defaultspack.blocks.tool.browser_computer as browser_computer_block

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, tool_name="computer_use", artifact_root=None, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["context"] = dict(context or {})
        captured["tool_name"] = tool_name
        captured["artifact_root"] = artifact_root
        captured["yolo_mode"] = yolo_mode
        return {"action": action, "ok": True}

    monkeypatch.setattr(browser_computer_block, "run_computer_action", fake_router)

    result = browser_computer_block.run(
        {"action": "computer.observe", "payload": {"detail": "full"}},
        {"conversation_workspace_dir": "/tmp/work", "yolo_mode": "true"},
    )

    assert result["status"] == "ok"
    assert captured["action"] == "computer.observe"
    assert captured["payload"]["detail"] == "full"
    assert captured["context"]["conversation_workspace_dir"] == "/tmp/work"
    assert captured["tool_name"] == "browser_computer"
    assert captured["yolo_mode"] is True
