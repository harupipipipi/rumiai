from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _completed_message(events: list[dict]) -> dict:
    for event in events:
        if event.get("type") == "assistant_message_completed":
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            message = data.get("message")
            if isinstance(message, dict):
                return message
    raise AssertionError("assistant_message_completed not found")


def test_assistant_progress_emits_activity_without_counting_as_tool_log(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    turns = {"count": 0}
    executed = []

    def fake_model_turn(self, prepared, messages, draft):
        if False:
            yield {}
        turns["count"] += 1
        if turns["count"] == 1:
            return (
                {"content": [], "finish_reason": "tool_calls", "usage": {}},
                [
                    {
                        "type": "tool_use",
                        "id": "progress-1",
                        "name": "assistant_progress",
                        "input": {
                            "phase": "inspect",
                            "status": "active",
                            "summary": "原因を確認しています",
                            "next_action": "ファイルを読みます",
                        },
                    },
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "lookup",
                        "input": {"path": "src/App.tsx"},
                    },
                ],
            )
        return {"content": [{"type": "text", "text": "done"}], "finish_reason": "stop", "usage": {}}, []

    def fake_execute_tool(self, prepared, tool_name, tool_call_id, arguments):
        executed.append((tool_name, dict(arguments)))
        result = {"status": "ok", "data": {"content": "ok", "path": arguments.get("path")}}
        self._tool_logs.append(
            {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": dict(arguments),
                "result": result,
                "timestamp": "2026-06-24T10:20:30Z",
            }
        )
        return result

    monkeypatch.setattr(ChatRunEngine, "_model_turn", fake_model_turn)
    monkeypatch.setattr(ChatRunEngine, "_execute_tool", fake_execute_tool)

    events = list(
        ChatRunEngine().stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "inspect then read"},
                "tools": [{"name": "lookup", "description": "lookup"}],
                "params": {"max_tool_calls": 1},
            },
            {},
        )
    )

    message = _completed_message(events)
    assert executed == [("lookup", {"path": "src/App.tsx"})]
    assert [log["tool_name"] for log in message["tool_logs"]] == ["lookup"]
    assert message["metadata"]["executed_tools"] == ["lookup"]
    assert "assistant_progress" not in message["metadata"]["attached_tools"]
    progress_events = [event for event in message["events"] if event.get("type") == "assistant_progress"]
    assert len(progress_events) == 1
    assert progress_events[0]["summary"] == "原因を確認しています"
    assert progress_events[0]["next_action"] == "ファイルを読みます"
    ChatStore._instance = None


def test_assistant_progress_only_loop_pauses_without_tool_logs(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    turns = {"count": 0}

    def fake_model_turn(self, prepared, messages, draft):
        if False:
            yield {}
        turns["count"] += 1
        return (
            {"content": [], "finish_reason": "tool_calls", "usage": {}},
            [
                {
                    "type": "tool_use",
                    "id": f"progress-{turns['count']}",
                    "name": "assistant_progress",
                    "input": {
                        "phase": "inspect",
                        "status": "active",
                        "summary": f"確認中 {turns['count']}",
                        "next_action": "次も確認します",
                    },
                }
            ],
        )

    monkeypatch.setattr(ChatRunEngine, "_model_turn", fake_model_turn)

    events = list(
        ChatRunEngine().stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "keep updating progress"},
                "tools": [{"name": "lookup", "description": "lookup"}],
                "params": {},
            },
            {},
        )
    )

    message = _completed_message(events)
    assert message["finish_reason"] == "paused_progress_loop"
    assert message["tool_logs"] == []
    assert message["metadata"]["loop_guard"]["reason"] == "progress_loop"
    progress_events = [event for event in message["events"] if event.get("type") == "assistant_progress"]
    assert len(progress_events) == 2
    ChatStore._instance = None
