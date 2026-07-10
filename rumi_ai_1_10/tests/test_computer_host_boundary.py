from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_computer_router_accepts_injected_model_agnostic_host(tmp_path, monkeypatch) -> None:
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    captured: dict[str, object] = {}

    class FakeHost:
        host_id = "fake"
        permission_subject = "Fake host"

        def available(self) -> bool:
            return True

        def run(self, action, payload, *, context=None, artifact_root=None, yolo_mode=False):
            captured["action"] = action
            captured["payload"] = dict(payload)
            captured["context"] = dict(context or {})
            captured["artifact_root"] = artifact_root
            captured["yolo_mode"] = yolo_mode
            return {"action": action, "executed": True, "host_id": self.host_id}

    class ExplodingController:
        def __init__(self, artifact_root=None):
            raise AssertionError("native controller must not be constructed when a host is injected")

    monkeypatch.setattr(computer_router, "BrowserComputerController", ExplodingController)

    result = computer_router.run_computer_action(
        "computer.type",
        {"text": "hello"},
        {"conversation_id": "conv_1"},
        artifact_root=tmp_path,
        yolo_mode=True,
        computer_host=FakeHost(),
    )

    assert result == {"action": "computer.type", "executed": True, "host_id": "fake"}
    assert captured == {
        "action": "computer.type",
        "payload": {"text": "hello"},
        "context": {"conversation_id": "conv_1"},
        "artifact_root": tmp_path,
        "yolo_mode": True,
    }


def test_injected_host_still_uses_defaultspack_approval_contract() -> None:
    from domain.safety import approval
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    approval.reset_approval_state_for_tests()

    class FakeHost:
        host_id = "fake"
        permission_subject = "Fake host"

        def available(self) -> bool:
            return True

        def run(self, action, payload, *, context=None, artifact_root=None, yolo_mode=False):
            return {
                "action": action,
                "requires_approval": True,
                "approval_token": "host-local-token",
                "payload": dict(payload),
            }

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "y": 20},
        {"conversation_id": "conv_1"},
        tool_name="computer_use",
        computer_host=FakeHost(),
    )

    assert result["approval_required"] is True
    assert str(result["approval_request_id"]).startswith("apr_")
    assert result["payload"] == {"x": 10, "y": 20}
    assert "approval_token" not in result


def test_local_controller_host_adapts_existing_controller(tmp_path) -> None:
    from ecosystem.defaultspack.domain.host_bridge.computer_host import LocalControllerComputerHost

    captured: dict[str, object] = {}

    class FakeController:
        def __init__(self, artifact_root=None):
            captured["artifact_root"] = artifact_root

        def run(self, action, payload, *, yolo_mode=False):
            captured["action"] = action
            captured["payload"] = dict(payload)
            captured["yolo_mode"] = yolo_mode
            return {"action": action, "local": True}

    host = LocalControllerComputerHost(FakeController)
    result = host.run(
        "computer.key",
        {"key_combo": "ctrl+s"},
        context={"ignored_by_native_host": True},
        artifact_root=tmp_path,
        yolo_mode=True,
    )

    assert host.available() is True
    assert result == {"action": "computer.key", "local": True}
    assert captured == {
        "artifact_root": tmp_path,
        "action": "computer.key",
        "payload": {"key_combo": "ctrl+s"},
        "yolo_mode": True,
    }


def test_viewer_host_preserves_recovery_when_native_broker_is_unavailable() -> None:
    from ecosystem.defaultspack.domain.host_bridge.computer_host import ViewerBrokerComputerHost

    class FakeClient:
        def available(self) -> bool:
            return False

    result = ViewerBrokerComputerHost(FakeClient()).run("computer.screenshot", {})

    assert result["is_error"] is True
    assert result["permission_subject"] == "Rumi Viewer"
    assert result["recovery"]["kind"] == "open_rumi_viewer"
