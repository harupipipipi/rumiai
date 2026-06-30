from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _computer_control_tool_def(tool_name: str) -> dict[str, object]:
    return {
        "tool_id": tool_name,
        "name": tool_name,
        "risk": "high",
        "requires_approval": True,
        "capability_grants": ["browser.control", "computer.control"],
        "execution": {
            "type": "rumi_function",
            "qualified_name": f"rumi_default_tools_pack:{tool_name}",
        },
    }


def _computer_router_module():
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    return computer_router


def test_run_computer_action_wraps_controller_approval_with_request_id(monkeypatch) -> None:
    from domain.safety import approval

    computer_router = _computer_router_module()
    approval.reset_approval_state_for_tests()
    monkeypatch.setenv("RUMI_COMPUTER_HOST_INTERNAL", "1")

    class _FakeController:
        def __init__(self, artifact_root=None):
            self.artifact_root = artifact_root

        def run(self, action, payload, *, yolo_mode=False):
            return {
                "action": action,
                "requires_approval": True,
                "approval_token": "legacy-token",
                "approval_expires_in_seconds": 300,
                "payload": dict(payload),
            }

    monkeypatch.setattr(computer_router, "BrowserComputerController", _FakeController)

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "y": 20},
        {"conversation_id": "conv_1"},
        tool_name="computer_use",
        tool_arguments={"action": "computer.click", "x": 10, "y": 20},
    )

    assert result["approval_required"] is True
    assert result["tool_name"] == "computer_use"
    assert result["action"] == "computer.click"
    assert str(result["approval_request_id"]).startswith("apr_")
    assert result["payload"] == {"x": 10, "y": 20}


def test_tool_executor_local_computer_use_uses_router(monkeypatch) -> None:
    from domain.tool.executor import ToolExecutor

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, tool_name="computer_use", tool_arguments=None, artifact_root=None, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["tool_name"] = tool_name
        captured["tool_arguments"] = dict(tool_arguments or {})
        captured["artifact_root"] = artifact_root
        captured["yolo_mode"] = yolo_mode
        return {"action": action, "routed": True}

    monkeypatch.setattr(_computer_router_module(), "run_computer_action", fake_router)

    result = ToolExecutor()._execute_local(
        "computer_use",
        {"action": "apps"},
        {"conversation_id": "conv_1", "conversation_workspace_dir": "/tmp/conversation/workspace"},
        tool_def=_computer_control_tool_def("computer_use"),
    )

    assert result["is_error"] is False
    assert captured["action"] == "computer.apps"
    assert captured["tool_name"] == "computer_use"
    assert captured["tool_arguments"] == {"action": "apps"}


def test_tool_executor_local_computer_use_accepts_context_approval_token(monkeypatch) -> None:
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    arguments = {"action": "apps"}
    request = approval.create_approval_request(
        "computer.apps",
        "high",
        {"action": "computer.apps"},
        details={"pack_id": "defaultspack", "conversation_id": "conv_1"},
    )
    decision = approval.approve(request["request_id"])
    assert decision["approved"] is True

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, tool_name="computer_use", tool_arguments=None, artifact_root=None, yolo_mode=False):
        captured["payload"] = dict(payload)
        captured["context"] = dict(context or {})
        captured["tool_arguments"] = dict(tool_arguments or {})
        return {"action": action, "routed": True}

    monkeypatch.setattr(_computer_router_module(), "run_computer_action", fake_router)

    result = ToolExecutor()._execute_local(
        "computer_use",
        arguments,
        {
            "conversation_id": "conv_1",
            "tool_approval_tokens": {
                "computer_use": decision["token"],
                "computer.apps": decision["token"],
            },
        },
        tool_def=_computer_control_tool_def("computer_use"),
    )

    assert result["is_error"] is False
    assert captured["payload"]["approval_token"] == decision["token"]
    assert captured["context"]["_tool_server_approved"] is True


def test_computer_use_pack_function_routes_original_arguments(monkeypatch) -> None:
    from ecosystem.rumi_default_tools_pack.functions.computer_use.main import run

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, tool_name="computer_use", tool_arguments=None, artifact_root=None, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["context"] = dict(context or {})
        captured["tool_name"] = tool_name
        captured["tool_arguments"] = dict(tool_arguments or {})
        return {"action": action, "tool_name": tool_name, "apps": [{"name": "Google Chrome"}]}

    monkeypatch.setattr(_computer_router_module(), "run_computer_action", fake_router)

    result = run(
        {"conversation_workspace_dir": "/tmp/conversation/workspace"},
        {"action": "apps"},
    )

    assert result["is_error"] is False
    assert captured["action"] == "computer.apps"
    assert captured["tool_name"] == "computer_use"
    assert captured["tool_arguments"] == {"action": "apps"}
    assert result["widget"]["type"] == "computer_use"
