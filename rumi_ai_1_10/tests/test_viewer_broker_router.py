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

        def run_computer(self, function_id, args, context=None):
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


def test_defaultspack_browser_computer_block_uses_router(monkeypatch):
    import ecosystem.defaultspack.blocks.tool.browser_computer as browser_computer_block

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, artifact_root=None, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["context"] = dict(context or {})
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
    assert captured["yolo_mode"] is True
