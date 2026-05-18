from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_chat_run_engine_retries_focus_blocked_computer_use_after_refocus(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine
    from domain.tool.executor import ToolExecutor

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def supports_stream(self, model):
            return True

        def stream(self, model, messages, tools=None, params=None):
            self.calls += 1
            if self.calls == 1:
                yield {"type": "tool_call_start", "id": "call_focus_retry", "name": "browser_computer"}
                yield {
                    "type": "tool_call_delta",
                    "id": "call_focus_retry",
                    "name": "browser_computer",
                    "arguments_chunk": "{\"action\":\"computer.click\",\"payload\":{\"x\":10,\"y\":20,\"physical\":true}}",
                }
                yield {"type": "tool_call_end", "id": "call_focus_retry", "name": "browser_computer"}
                yield {"type": "stream_end", "finish_reason": "tool_calls"}
                return
            yield {"type": "content_delta", "delta": {"type": "text", "text": "sent"}}
            yield {"type": "stream_end", "finish_reason": "stop"}

        def complete(self, model, messages, tools=None, params=None):
            raise AssertionError("complete should not be called")

    calls: list[tuple[str, str]] = []

    def fake_execute(self, tool_name, arguments, context):
        action = str(arguments.get("action") or "")
        calls.append((tool_name, action))
        if action == "computer.select_window":
            return {
                "result": "browser_computer computer.select_window completed",
                "is_error": False,
                "widget": {
                    "type": "browser_computer",
                    "action": "computer.select_window",
                    "selected": True,
                    "target_window": {
                        "app": "Google Chrome",
                        "title": "LINE Chat - Google Chrome",
                        "x": 10,
                        "y": 10,
                        "width": 900,
                        "height": 700,
                        "window_id": 200,
                    },
                },
            }
        click_attempt = len([item for item in calls if item == ("browser_computer", "computer.click")])
        if click_attempt == 1:
            return {
                "result": "browser_computer computer.click failed: Foreground input target is not active",
                "is_error": True,
                "widget": {
                    "type": "browser_computer",
                    "action": "computer.click",
                    "executed": False,
                    "is_error": True,
                    "active_window": {
                        "app": "Codex",
                        "title": "Codex",
                        "x": 0,
                        "y": 0,
                        "width": 900,
                        "height": 700,
                        "window_id": 100,
                    },
                    "selected_window": {
                        "app": "Google Chrome",
                        "title": "LINE Chat - Google Chrome",
                        "x": 10,
                        "y": 10,
                        "width": 900,
                        "height": 700,
                        "window_id": 200,
                    },
                    "recovery": {
                        "kind": "focus_required",
                        "note": "Bring the selected app/window to the foreground, then retry the foreground input action.",
                    },
                },
                "recovery": {
                    "kind": "focus_required",
                    "note": "Bring the selected app/window to the foreground, then retry the foreground input action.",
                },
            }
        return {
            "result": "browser_computer computer.click completed",
            "is_error": False,
            "widget": {
                "type": "browser_computer",
                "action": "computer.click",
                "executed": True,
            },
        }

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    monkeypatch.setattr(ChatRunEngine, "_provider_supports_stream_tool_calls", staticmethod(lambda _model: True))

    store = ChatStore()
    conversation = store.create_conversation(model="openai/gpt-5.4")
    events = list(
        ChatRunEngine(client=FakeClient()).stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "send hello"},
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "browser_computer",
                            "parameters": {"type": "object", "properties": {}, "required": []},
                        },
                    }
                ],
            },
            {
                "user_requested_computer_use": True,
                "computer_use_target_app": "Google Chrome",
                "computer_use_target_title": "LINE Chat",
            },
            stream_mode=True,
        )
    )

    assert calls == [
        ("browser_computer", "computer.select_window"),
        ("browser_computer", "computer.click"),
        ("browser_computer", "computer.select_window"),
        ("browser_computer", "computer.click"),
    ]
    status_phases = [event.get("phase") for event in events if event["type"] == "status"]
    assert "tool_recovery_retry" in status_phases
    assert "tool_blocked" not in status_phases
    final_message = [event["data"]["message"] for event in events if event["type"] == "done"][-1]
    assert final_message["raw_text"] == "sent"
    ChatStore._instance = None
