from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.chat.browser_state import emit_browser_state_events  # noqa: E402


def _coding_file_read_result(text: str) -> dict:
    return {
        "status": "ok",
        "data": {
            "result": text,
            "is_error": False,
            "widget": {
                "path": "/tmp/readme.txt",
                "content": text,
                "size": len(text),
                "encoding": "utf-8",
            },
        },
    }


def test_emit_browser_state_events_ignore_coding_file_read_widget_payload():
    emission = emit_browser_state_events(
        "coding_file_read",
        _coding_file_read_result(
            "Background computer-use is disabled. Only currently visible windows can be operated."
        ),
    )

    assert emission.events == []
    assert emission.state_revision == 0


def test_tool_result_recovery_kind_ignores_visible_window_phrase_in_non_error_file_content():
    import blocks.chat.send as send

    assert (
        send._tool_result_recovery_kind(
            _coding_file_read_result(
                "Background computer-use is disabled. Only currently visible windows can be operated."
            )
        )
        == ""
    )


def test_chat_run_engine_does_not_block_on_coding_file_read_contents(tmp_path, monkeypatch):
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
                yield {"type": "tool_call_start", "id": "call_1", "name": "coding_file_read"}
                yield {
                    "type": "tool_call_delta",
                    "id": "call_1",
                    "name": "coding_file_read",
                    "arguments_chunk": "{\"path\":\"/tmp/readme.txt\"}",
                }
                yield {"type": "tool_call_end", "id": "call_1", "name": "coding_file_read"}
                yield {
                    "type": "stream_end",
                    "finish_reason": "tool_calls",
                    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                }
                return
            yield {"type": "content_delta", "delta": {"type": "text", "text": "review done"}}
            yield {
                "type": "stream_end",
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

        def complete(self, model, messages, tools=None, params=None):
            return {
                "content": [{"type": "text", "text": "review done"}],
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

    def fake_execute(self, tool_name, arguments, context):
        return _coding_file_read_result(
            "Background computer-use is disabled. Only currently visible windows can be operated."
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    monkeypatch.setattr(ChatRunEngine, "_provider_supports_stream_tool_calls", staticmethod(lambda _model: True))

    store = ChatStore()
    conversation = store.create_conversation(model="openai/gpt-5.4")
    events = list(
        ChatRunEngine(client=FakeClient()).stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "read the file"},
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "coding_file_read",
                            "parameters": {"type": "object", "properties": {}, "required": []},
                        },
                    }
                ],
            },
            {},
            stream_mode=True,
        )
    )

    completed = next(event for event in events if event["type"] == "tool_call_completed")
    assert completed["data"]["recovery_kind"] == ""
    assert "browser_screenshot" not in [event["type"] for event in events]
    assert not any(event.get("phase") == "tool_blocked" for event in events)
    final_message = [event["data"]["message"] for event in events if event["type"] == "done"][-1]
    assert final_message["finish_reason"] == "stop"
    assert final_message["metadata"]["executed_tools"] == ["coding_file_read"]
    ChatStore._instance = None
