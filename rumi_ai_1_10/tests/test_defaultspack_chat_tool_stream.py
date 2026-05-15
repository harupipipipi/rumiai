from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_chat_run_engine_streams_tool_call_events_and_final_message(tmp_path, monkeypatch):
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
                yield {"type": "tool_call_start", "id": "call_1", "name": "calculator"}
                yield {"type": "tool_call_delta", "id": "call_1", "name": "calculator", "arguments_chunk": "{\"expression\":\"2+2\"}"}
                yield {"type": "tool_call_end", "id": "call_1", "name": "calculator"}
                yield {"type": "stream_end", "finish_reason": "tool_calls", "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
                return
            yield {"type": "content_delta", "delta": {"type": "text", "text": "4"}}
            yield {"type": "stream_end", "finish_reason": "stop", "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}

        def complete(self, model, messages, tools=None, params=None):
            return {
                "content": [{"type": "text", "text": "4"}],
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

    def fake_execute(self, tool_name, arguments, context):
        return {
            "result": "4",
            "is_error": False,
            "widget": {"type": tool_name, "result": "4"},
        }

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    monkeypatch.setattr(ChatRunEngine, "_provider_supports_stream_tool_calls", staticmethod(lambda _model: True))

    store = ChatStore()
    conversation = store.create_conversation(model="openai/gpt-5.4")
    events = list(
        ChatRunEngine(client=FakeClient()).stream(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "use a tool"},
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "parameters": {"type": "object", "properties": {}, "required": []},
                        },
                    }
                ],
            },
            {},
            stream_mode=True,
        )
    )

    event_types = [event["type"] for event in events]
    streamed_run_ids = {
        event["run_id"]
        for event in events
        if event["type"] in {"content_delta", "tool_call_started", "tool_call_delta", "tool_call_completed", "done"}
    }
    assert "tool_call_started" in event_types
    assert "tool_call_delta" in event_types
    assert "tool_call_completed" in event_types
    assert len(streamed_run_ids) == 1
    final_message = [event["data"]["message"] for event in events if event["type"] == "done"][-1]
    assert final_message["raw_text"] == "4"
    ChatStore._instance = None


def test_stream_with_selected_tools_uses_chat_run_engine_not_legacy_fallback(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine
    from domain.tool.executor import ToolExecutor
    import blocks.chat.stream as stream_module

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
                yield {"type": "tool_call_start", "id": "call_1", "name": "calculator"}
                yield {"type": "tool_call_delta", "id": "call_1", "name": "calculator", "arguments_chunk": "{\"expression\":\"2+2\"}"}
                yield {"type": "tool_call_end", "id": "call_1", "name": "calculator"}
                yield {"type": "stream_end", "finish_reason": "tool_calls", "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
                return
            yield {"type": "content_delta", "delta": {"type": "text", "text": "4"}}
            yield {"type": "stream_end", "finish_reason": "stop", "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}

        def complete(self, model, messages, tools=None, params=None):
            return {
                "content": [{"type": "text", "text": "4"}],
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

    def fake_execute(self, tool_name, arguments, context):
        return {
            "result": "4",
            "is_error": False,
        }

    def fail_legacy_fallback(*_args, **_kwargs):
        raise AssertionError("legacy _fallback_send should not be used for selected tools")

    monkeypatch.setattr(stream_module, "_fallback_send", fail_legacy_fallback)
    monkeypatch.setattr(stream_module, "AIClient", FakeClient)
    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    monkeypatch.setattr(ChatRunEngine, "_provider_supports_stream_tool_calls", staticmethod(lambda _model: True))

    store = ChatStore()
    conversation = store.create_conversation(model="openai/gpt-5.4")
    result = stream_module.run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "use a tool"},
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                }
            ],
        },
        {},
    )

    events = list(result["events"])
    event_types = [event["type"] for event in events]
    assert event_types.count("tool_call_started") == 1
    assert event_types.count("tool_call_delta") == 1
    assert event_types.count("tool_call_completed") == 1
    assert event_types[-2:] == ["message", "done"]
    ChatStore._instance = None


def test_chat_run_engine_streams_browser_state_events_with_timestamped_tool_result(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.chat.stream_engine import ChatRunEngine
    from domain.tool.executor import ToolExecutor

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    png_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aKkAAAAASUVORK5CYII="
    )

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def supports_stream(self, model):
            return True

        def stream(self, model, messages, tools=None, params=None):
            self.calls += 1
            if self.calls == 1:
                yield {"type": "tool_call_start", "id": "call_browser_1", "name": "browser_computer"}
                yield {
                    "type": "tool_call_delta",
                    "id": "call_browser_1",
                    "name": "browser_computer",
                    "arguments_chunk": "{\"action\":\"computer.click\"}",
                }
                yield {"type": "tool_call_end", "id": "call_browser_1", "name": "browser_computer"}
                yield {"type": "stream_end", "finish_reason": "tool_calls"}
                return
            yield {"type": "content_delta", "delta": {"type": "text", "text": "clicked"}}
            yield {"type": "stream_end", "finish_reason": "stop"}

        def complete(self, model, messages, tools=None, params=None):
            return {
                "content": [{"type": "text", "text": "clicked"}],
                "finish_reason": "stop",
            }

    def fake_execute(self, tool_name, arguments, context):
        return {
            "result": "browser_computer computer.click completed",
            "is_error": False,
            "widget": {
                "type": "browser_computer",
                "action": "computer.click",
                "executed": True,
                "visual_feedback": {
                    "type": "post_click_screenshot",
                    "screenshot_path": "/tmp/post-click.png",
                    "model_image_path": "/tmp/post-click-model.png",
                    "data_url": png_data_url,
                },
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
                "message": {"role": "user", "content": "click"},
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
            {},
            stream_mode=True,
        )
    )

    event_types = [event["type"] for event in events]
    assert "task_failed" not in event_types
    assert "browser_state_invalidated" in event_types
    assert "browser_screenshot" in event_types
    screenshot_event = next(event for event in events if event["type"] == "browser_screenshot")
    assert screenshot_event["data"]["timestamp"]
    assert screenshot_event["data"]["screenshot"]["model_image_path"] == "/tmp/post-click-model.png"
    assert events[-1]["type"] == "done"
    ChatStore._instance = None


def test_chat_run_engine_stops_for_permission_required_tool_result(tmp_path, monkeypatch):
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
            if self.calls > 1:
                raise AssertionError("model should not continue after approval_required tool result")
            yield {"type": "tool_call_start", "id": "call_browser_approval", "name": "browser_computer"}
            yield {
                "type": "tool_call_delta",
                "id": "call_browser_approval",
                "name": "browser_computer",
                "arguments_chunk": "{\"action\":\"computer.click\",\"x\":1,\"y\":2}",
            }
            yield {"type": "tool_call_end", "id": "call_browser_approval", "name": "browser_computer"}
            yield {"type": "stream_end", "finish_reason": "tool_calls"}

        def complete(self, model, messages, tools=None, params=None):
            raise AssertionError("complete should not be called")

    def fake_execute(self, tool_name, arguments, context):
        return {
            "status": "ok",
            "data": {
                "result": "approval required",
                "is_error": False,
                "widget": {
                    "type": "browser_computer",
                    "action": "computer.click",
                    "requires_approval": True,
                    "approval_token": "approval-token-1",
                    "payload": {"x": 1, "y": 2},
                },
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
                "message": {"role": "user", "content": "click"},
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
            {},
            stream_mode=True,
        )
    )

    event_types = [event["type"] for event in events]
    assert "approval_requested" in event_types
    approval_event = next(event for event in events if event["type"] == "approval_requested")
    assert approval_event["data"]["approval_token"] == "approval-token-1"
    assert approval_event["data"]["payload"] == {"x": 1, "y": 2}
    final_message = [event["data"]["message"] for event in events if event["type"] == "done"][-1]
    assert final_message["raw_text"] == "許可が必要なため、ユーザーが承認するまで待機します。承認後に続行します。"
    assert final_message["metadata"]["pending_approval"]["approval_token"] == "approval-token-1"
    ChatStore._instance = None
