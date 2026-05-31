from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

for path in (ROOT, DEFAULTSPACK_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

sys.modules.setdefault("domain", importlib.import_module("ecosystem.defaultspack.domain"))


def test_computer_use_main_normalizes_compound_context_action(monkeypatch):
    from ecosystem.rumi_default_tools_pack.functions.computer_use import main as computer_use_main

    captured: dict[str, object] = {}

    def fake_run_browser_computer(context, args):
        captured["context"] = context
        captured["args"] = args
        return {"result": "ok", "is_error": False, "widget": None}

    monkeypatch.setattr(computer_use_main, "_run_browser_computer", fake_run_browser_computer)

    computer_use_main.run({}, {"action": "context/apps/windows"})

    assert captured["args"]["action"] == "computer.context"


def test_browser_computer_controller_normalizes_compound_context_alias():
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    assert BrowserComputerController._normalize_action("context/apps/windows") == "computer.context"
    assert BrowserComputerController._normalize_action("computer.context/apps/windows") == "computer.context"


def test_browser_computer_main_treats_server_approved_context_as_yolo(monkeypatch):
    from ecosystem.rumi_default_tools_pack.functions.browser_computer import main as browser_main
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    captured: dict[str, object] = {}

    def fake_run_computer_action(action, payload, context, **kwargs):
        captured["action"] = action
        captured["payload"] = payload
        captured["context"] = context
        captured["kwargs"] = kwargs
        return {"action": action, "opened": True}

    monkeypatch.setattr(computer_router, "run_computer_action", fake_run_computer_action)

    browser_main.run(
        {"_tool_server_approved": True, "conversation_workspace_dir": "/tmp/workspace"},
        {"action": "browser.open_url", "payload": {"url": "https://example.test"}},
    )

    assert captured["kwargs"]["yolo_mode"] is True


def test_tool_approval_followup_only_applies_to_matching_arguments(monkeypatch):
    from ecosystem.defaultspack.domain.safety import approval as approval_module
    from ecosystem.defaultspack.domain.tool.executor import _context_with_tool_approval_token

    approval_module.reset_approval_state_for_tests()
    approved_args = {"action": "context/apps/windows"}
    request = approval_module.create_approval_request(
        "tool.computer_use",
        "high",
        approved_args,
        details={"tool_name": "computer_use"},
    )
    decision = approval_module.approve(request["request_id"])

    tool_def = {"name": "computer_use", "risk": "high"}
    context = {
        "tool_approval_followups": [
            {
                "tool_name": "computer_use",
                "operation": "tool.computer_use",
                "request_id": request["request_id"],
                "token": decision["token"],
                "args_hash": request["args_hash"],
            }
        ],
        "tool_approval_tokens": {request["request_id"]: decision["token"]},
    }

    matching_args = dict(approved_args)
    next_context, approval_error = _context_with_tool_approval_token(context, tool_def, matching_args)

    assert approval_error is None
    assert next_context["_tool_server_approved"] is True
    assert matching_args["approval_token"] == decision["token"]

    different_args = {"action": "show_app", "app": "Vivaldi"}
    next_context, approval_error = _context_with_tool_approval_token(context, tool_def, different_args)

    assert approval_error is None
    assert "_tool_server_approved" not in next_context
    assert "approval_token" not in different_args

    approval_module.reset_approval_state_for_tests()
