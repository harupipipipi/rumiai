from __future__ import annotations

import subprocess
import sys
import importlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
OPERATIONS_PACK_ROOT = ROOT / "ecosystem" / "rumi_operations_company_pack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _RouteRegistry:
    def __init__(self):
        self.routes = []

    def register(self, key, value, meta=None):
        if key == "io.http.route":
            self.routes.append(value)

    def get(self, *args, **kwargs):
        return None

    def get_interface(self, key, strategy=None):
        if key == "io.http.route":
            return self.routes
        return None


def _collect_defaultspack_routes():
    registry = _RouteRegistry()
    ecosystem = json.loads((DEFAULTSPACK_ROOT / "ecosystem.json").read_text(encoding="utf-8"))
    for entry in ecosystem["load_order"]:
        _, component_id = entry.split(":", 1)
        component = ecosystem["components"][component_id]
        module_name = component["path"].replace("/", ".") + ".setup"
        try:
            setup = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        setup.run({"interface_registry": registry, "_source_component": entry})
    from ecosystem.rumi_operations_company_pack.blocks.agent import setup as operations_setup

    operations_setup.run(
        {
            "interface_registry": registry,
            "_source_component": "rumi_operations_company_pack:agent:operations_company",
        }
    )
    return registry


def test_capability_catalog_loads_plan_manifest():
    from domain.capability.catalog import CapabilityCatalog

    catalog = CapabilityCatalog(DEFAULTSPACK_ROOT)
    manifest = catalog.manifest()

    assert manifest["local_first"] is True
    assert manifest["core_requires_api_key"] is False
    assert manifest["default_profile"] == "defaultspack.local_agent"
    assert manifest["counts"]["capabilities"] >= 11
    assert manifest["counts"]["profiles"] >= 5
    capability_ids = {item["id"] for item in manifest["capabilities"]}
    assert {"local_file", "terminal", "git", "safety", "artifact", "compact", "research"} <= capability_ids


def test_chat_store_persists_conversations_to_user_data(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None


def test_model_profiles_expose_required_context_and_thinking_metadata():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog

    profiles = list_profile_catalog()
    by_id = {profile["profile_id"]: profile for profile in profiles}

    assert by_id["stub/default"]["max_context"] == -1
    assert isinstance(by_id["openrouter/tencent/hy3-preview:free"]["max_context"], int)
    assert "supports_thinking" in by_id["openrouter/tencent/hy3-preview:free"]
    assert isinstance(by_id["openai/gpt-5.4"]["thinking_levels"], list)


def test_chat_send_attaches_tools_and_persists_activity_events(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello with tools"},
            "params": {"thinking_level": "medium"},
        },
        {},
    )

    assert result["status"] == "ok"
    assistant = result["data"]
    assert assistant["metadata"]["model"] == "stub/default"
    assert assistant["metadata"]["attached_tool_count"] >= 1
    assert assistant["metadata"]["thinking_level"] == "medium"
    assert any(event["phase"] == "tools_attached" for event in assistant["events"])

    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    stored_assistant = persisted["conversations"][conversation["id"]]["messages"][-1]
    assert stored_assistant["metadata"]["attached_tool_count"] == assistant["metadata"]["attached_tool_count"]
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(tags=["persisted"])
    message = store.add_message(
        conversation["id"],
        {"role": "user", "content": [{"type": "text", "text": "hello persistence"}]},
    )

    assert storage_path.is_file()
    payload = json.loads(storage_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert conversation["id"] in payload["conversations"]
    assert payload["conversations"][conversation["id"]]["messages"][0]["id"] == message["id"]

    ChatStore._instance = None
    reloaded = ChatStore()
    assert reloaded.get_conversation(conversation["id"])["messages"][0]["raw_text"] == "hello persistence"
    ChatStore._instance = None


def test_chat_store_links_subagent_conversations(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    parent = store.create_conversation(model="stub/default")
    child = store.create_conversation(
        model="stub/default",
        parent_conversation_id=parent["id"],
        conversation_kind="subagent",
    )

    parent_after = store.get_conversation(parent["id"])
    child_after = store.get_conversation(child["id"])
    assert child_after["parent_conversation_id"] == parent["id"]
    assert child_after["conversation_kind"] == "subagent"
    assert child["id"] in parent_after["child_conversation_ids"]

    store.delete_conversation(child["id"])
    assert child["id"] not in store.get_conversation(parent["id"])["child_conversation_ids"]
    ChatStore._instance = None


def test_todo_tool_persists_in_conversation_workspace(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.todo import TodoController

    workspace = tmp_path / "conversation" / "workspace"
    result = TodoController().run(
        {"action": "add", "title": "ブラウザ確認", "priority": "high"},
        {"conversation_workspace_dir": str(workspace)},
    )

    todo_path = workspace / "todos.json"
    assert result["todos"][0]["title"] == "ブラウザ確認"
    assert todo_path.exists()
    assert json.loads(todo_path.read_text(encoding="utf-8"))["todos"][0]["priority"] == "high"


def test_subagent_tool_creates_child_conversation(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from ecosystem.rumi_default_tools_pack.domain.tool.subagent import SubagentController

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    parent = store.create_conversation(model="stub/default")
    result = SubagentController().run(
        {"task": "hello from subagent", "title": "Subagent check"},
        {"conversation_id": parent["id"], "model": "stub/default"},
    )

    parent_after = store.get_conversation(parent["id"])
    child = store.get_conversation(result["child_conversation_id"])
    assert result["child_conversation_id"] in parent_after["child_conversation_ids"]
    assert child["title"] == "Subagent check"
    assert [message["role"] for message in child["messages"]] == ["user", "assistant"]
    ChatStore._instance = None


def test_integration_secret_store_reads_chat_tokens_without_env_injection(tmp_path, monkeypatch):
    from domain.integrations.secrets import (
        get_integration_secret,
        load_integration_secrets_into_env,
        set_integration_secret,
    )

    secrets_dir = tmp_path / "secrets"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(secrets_dir))
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    result = set_integration_secret("slack", "SLACK_BOT_TOKEN", "xoxb-test")
    assert result["success"] is True
    os.environ.pop("SLACK_BOT_TOKEN", None)

    loaded = load_integration_secrets_into_env()
    assert loaded["slack"] is True
    assert "SLACK_BOT_TOKEN" not in os.environ
    assert get_integration_secret("slack", "SLACK_BOT_TOKEN") == "xoxb-test"


def test_unit_executor_does_not_pass_integration_tokens_to_python_fallback(monkeypatch):
    from core_runtime.unit_executor import UnitExecutor

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "line-token")
    process_env = UnitExecutor._build_subprocess_env()

    assert "LINE_CHANNEL_ACCESS_TOKEN" not in process_env


def test_external_integration_routes_are_registered():
    registry = _collect_defaultspack_routes()
    patterns = {route["pattern"] for route in registry.routes}

    assert "/api/integrations/slack/events" in patterns
    assert "/api/integrations/line/webhook" in patterns
    assert "/api/integrations/discord/interactions" in patterns
    assert "/api/integrations/secrets" in patterns
    assert "/api/chat/conversations/{id}/run-results/{run_id}/browser-screenshots" in patterns
    assert "/v1/conversations/{id}/run-results/{run_id}/browser-screenshots" in patterns


def test_slack_event_creates_external_conversation(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.integrations.slack import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    integration_path = tmp_path / "user_data" / "shared" / "integrations" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_INTEGRATIONS_STORE_PATH", str(integration_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_INTEGRATIONS_ALLOW_UNSIGNED_DEV", "1")
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    ChatStore._instance = None

    result = run(
        {
            "type": "event_callback",
            "team_id": "T1",
            "event_id": "Ev1",
            "event": {
                "type": "message",
                "channel": "C1",
                "user": "U1",
                "ts": "1.0",
                "text": "hello from slack",
            },
            "model": "stub/default",
            "tools": [],
        },
        {},
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["status"] == "ok"
    assert data["reply"]["sent"] is False

    stored = json.loads(storage_path.read_text(encoding="utf-8"))
    conversation = stored["conversations"][data["conversation_id"]]
    assert conversation["conversation_kind"] == "external"
    assert conversation["model"] == "stub/default"
    assert "integration:slack" in conversation["tags"]
    assert conversation["messages"][0]["metadata"]["external"]["provider"] == "slack"
    ChatStore._instance = None


def test_slack_event_fails_closed_without_signing_secret(tmp_path, monkeypatch):
    from blocks.integrations.slack import run

    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("RUMI_DEFAULTSPACK_INTEGRATIONS_ALLOW_UNSIGNED_DEV", raising=False)
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)

    result = run(
        {
            "type": "event_callback",
            "event": {"type": "message", "channel": "C1", "user": "U1", "ts": "1.0", "text": "hello"},
        },
        {},
    )

    assert result["status"] == "error"
    assert result["_http_status"] == 401
    assert result["error"]["code"] == "SIGNATURE_INVALID"


def test_discord_ping_and_agent_engine_queue_multiple_tool_calls(monkeypatch):
    from blocks.integrations.discord import run
    from domain.agent.engine import AgentEngine
    from domain.agent.execution import AgentExecution

    monkeypatch.setenv("RUMI_DEFAULTSPACK_INTEGRATIONS_ALLOW_UNSIGNED_DEV", "1")
    assert run({"type": 1}, {})["type"] == 1

    engine = AgentEngine()
    parsed = engine._parse_ai_response(
        {
            "status": "ok",
            "data": {
                "tool_calls": [
                    {"function": {"name": "calculator", "arguments": "{\"expression\":\"1+1\"}"}},
                    {"function": {"name": "todo", "arguments": "{\"action\":\"list\"}"}},
                ]
            },
        }
    )
    execution = AgentExecution("agent_test", "task", [], "stub/default", "")
    engine._set_pending_tool_call(execution, parsed)

    assert execution.pending_tool_call["tool_name"] == "calculator"
    assert [call["tool_name"] for call in execution.queued_tool_calls] == ["todo"]


def test_chat_stream_uses_provider_stream_and_persists_message(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.stream import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello stream"},
            "tools": [],
        },
        {},
    )

    assert result["_sse"] is True
    events = list(result["events"])
    deltas = [event["delta"] for event in events if event.get("type") == "delta"]
    assert "".join(deltas) == "This is a stub stream response."
    final = [event["message"] for event in events if event.get("type") == "message"][-1]
    assert final["role"] == "assistant"
    assert final["raw_text"] == "This is a stub stream response."

    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    messages = persisted["conversations"][conversation["id"]]["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    ChatStore._instance = None


def test_inline_thought_stream_filter_separates_thinking():
    from blocks.chat.stream import _InlineThoughtFilter

    filter_ = _InlineThoughtFilter()
    visible = [
        filter_.push("<tho"),
        filter_.push("ught>private"),
        filter_.push("</thought>public"),
        filter_.finish(),
    ]

    assert "".join(visible) == "public"
    assert filter_.transcript() == "private"


def test_inline_thought_stream_filter_exposes_incremental_thinking():
    from blocks.chat.stream import _InlineThoughtFilter

    filter_ = _InlineThoughtFilter()
    assert filter_.push("<thought>pri") == ""
    assert filter_.pending_thinking_delta() == "pri"
    assert filter_.push("vate</thought>public") == "public"
    assert filter_.pending_thinking_delta() == "vate"
    assert filter_.transcript() == "private"


def test_chat_stream_recovers_when_provider_returns_only_thinking(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    import blocks.chat.stream as stream_module

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    captured = {}

    class FakeAIClient:
        def supports_stream(self, model):
            return True

        def stream(self, model, messages, tools, params):
            yield {"type": "content_delta", "delta": {"type": "text", "text": "<thought>private plan"}}
            yield {
                "type": "stream_end",
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

        def complete(self, model, messages, tools, params):
            captured["retry_params"] = params
            return {
                "content": [{"type": "text", "text": "Recovered visible answer."}],
                "finish_reason": "stop",
                "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            }

    monkeypatch.setattr(stream_module, "AIClient", FakeAIClient)

    store = ChatStore()
    conversation = store.create_conversation(model="google/gemma-4-31b-it")
    result = stream_module.run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello"},
            "tools": [],
            "params": {"thinking_level": "high", "temperature": 0.2},
        },
        {},
    )

    events = list(result["events"])
    deltas = [event["delta"] for event in events if event.get("type") == "delta"]
    thinking_deltas = [event["delta"] for event in events if event.get("type") == "thinking_delta"]
    final = [event["message"] for event in events if event.get("type") == "message"][-1]

    assert "".join(deltas) == "Recovered visible answer."
    assert "".join(thinking_deltas) == "private plan"
    assert final["raw_text"] == "Recovered visible answer."
    assert final["metadata"]["thinking"]["transcript"] == "private plan"
    assert final["metadata"]["recovered_from_empty_stream"] is True
    assert captured["retry_params"] == {"temperature": 0.2}
    ChatStore._instance = None


def test_chat_stream_recovers_when_provider_returns_empty_text(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    import blocks.chat.stream as stream_module

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    captured = {}

    class FakeAIClient:
        def supports_stream(self, model):
            return True

        def stream(self, model, messages, tools, params):
            yield {
                "type": "stream_end",
                "finish_reason": "malformed_function_call",
                "usage": {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
            }

        def complete(self, model, messages, tools, params):
            captured["retry_params"] = params
            return {
                "content": [{"type": "text", "text": "Recovered after empty stream."}],
                "finish_reason": "stop",
                "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            }

    monkeypatch.setattr(stream_module, "AIClient", FakeAIClient)

    store = ChatStore()
    conversation = store.create_conversation(model="google/gemma-4-31b-it")
    result = stream_module.run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello"},
            "tools": [],
            "params": {"thinking_level": "high", "temperature": 0.2},
        },
        {},
    )

    events = list(result["events"])
    deltas = [event["delta"] for event in events if event.get("type") == "delta"]
    final = [event["message"] for event in events if event.get("type") == "message"][-1]

    assert "".join(deltas) == "Recovered after empty stream."
    assert final["raw_text"] == "Recovered after empty stream."
    assert final["metadata"]["recovered_from_empty_stream"] is True
    assert captured["retry_params"] == {"temperature": 0.2}
    ChatStore._instance = None


def test_chat_stream_infers_computer_tools_before_stream_decision(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    import blocks.chat.stream as stream_module

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    captured = {}

    def fake_fallback_send(input_data, context):
        captured["tools"] = input_data.get("tools")
        captured["user_requested_computer_use"] = context.get("user_requested_computer_use")
        yield {"type": "message", "message": {"role": "assistant", "raw_text": "ok"}}
        yield {"type": "done", "message": {"role": "assistant", "raw_text": "ok"}}

    monkeypatch.setattr(stream_module, "_fallback_send", fake_fallback_send)

    store = ChatStore()
    conversation = store.create_conversation(model="google/gemma-4-31b-it")
    result = stream_module.run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "computer useでchromeを開いて"},
            "tools": [],
        },
        {},
    )

    events = list(result["events"])
    assert events[-1]["type"] == "done"
    assert captured["tools"] == ["computer_use", "browser_computer"]
    assert captured["user_requested_computer_use"] is True
    ChatStore._instance = None


def test_chat_stream_infers_computer_tools_when_tools_are_omitted(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    import blocks.chat.stream as stream_module

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    captured = {}

    def fake_fallback_send(input_data, context):
        captured["tools"] = input_data.get("tools")
        yield {"type": "message", "message": {"role": "assistant", "raw_text": "ok"}}
        yield {"type": "done", "message": {"role": "assistant", "raw_text": "ok"}}

    monkeypatch.setattr(stream_module, "_fallback_send", fake_fallback_send)

    store = ChatStore()
    conversation = store.create_conversation(model="google/gemma-4-31b-it")
    result = stream_module.run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "Google Chromeを操作してChatGPTを開いて"},
        },
        {},
    )

    events = list(result["events"])
    assert events[-1]["type"] == "done"
    assert captured["tools"] == ["computer_use", "browser_computer"]
    ChatStore._instance = None


def test_chat_stream_fallback_yields_realtime_tool_progress(monkeypatch):
    import blocks.chat.send as send_module
    import blocks.chat.stream as stream_module

    def fake_send_run(input_data, context):
        context["stream_event_callback"](
            {
                "type": "tool_call_started",
                "tool_name": "browser_computer",
                "tool_call_id": "call_1",
                "message": "browser_computer を使用中",
            }
        )
        assert context["is_cancelled"]() is False
        return {
            "status": "ok",
            "data": {
                "id": "m1",
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
                "raw_text": "done",
            },
        }

    monkeypatch.setattr(send_module, "run", fake_send_run)

    events = list(stream_module._fallback_send({"conversation_id": "c1"}, {}))

    assert events[0]["type"] == "tool_call_started"
    assert events[0]["tool_name"] == "browser_computer"
    assert events[-2]["type"] == "message"
    assert events[-1]["type"] == "done"


def test_chat_send_retries_empty_thinking_response_without_thinking(monkeypatch):
    import blocks.chat.send as send_module

    calls = []

    def fake_direct_complete(model, messages, tools=None, params=None):
        calls.append(dict(params or {}))
        if len(calls) == 1:
            return {
                "content": [{"type": "text", "text": ""}],
                "finish_reason": "malformed_function_call",
                "usage": {},
            }, None
        return {
            "content": [{"type": "text", "text": "Recovered send response."}],
            "finish_reason": "stop",
            "usage": {},
        }, None

    monkeypatch.setattr(send_module, "_ai_direct_complete", fake_direct_complete)

    response = send_module._complete_with_tools(
        "google/gemma-4-31b-it",
        [{"role": "user", "content": "hello"}],
        [],
        {},
        None,
        {"thinking_level": "high", "temperature": 0.1},
    )

    assert response["content"][0]["text"] == "Recovered send response."
    assert response["metadata"]["recovered_from_empty_response"] is True
    assert calls == [
        {"thinking_level": "high", "temperature": 0.1},
        {"temperature": 0.1},
    ]


def test_browser_computer_pack_not_approved_falls_back_to_local(monkeypatch):
    from domain.tool.executor import ToolExecutor

    captured = {}

    def fake_execute_local(self, tool_name, arguments, context):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        captured["context"] = context
        return {
            "result": "browser_computer computer.click completed",
            "is_error": False,
            "widget": {"type": "browser_computer", "action": "computer.click"},
        }

    class FakeResponse:
        success = False
        error_type = "pack_not_approved"

    monkeypatch.setattr(ToolExecutor, "_execute_local", fake_execute_local)

    result = ToolExecutor._fallback_function_call_if_first_party_unapproved(
        {"name": "browser_computer"},
        {
            "type": "function.call",
            "qualified_name": "rumi_default_tools_pack:browser_computer",
            "args": {"action": "computer.click", "payload": {"x": 10, "y": 20}},
        },
        {"user_requested_computer_use": True},
        FakeResponse(),
    )

    assert result["is_error"] is False
    assert captured["tool_name"] == "browser_computer"
    assert captured["arguments"]["action"] == "computer.click"
    assert captured["context"]["user_requested_computer_use"] is True


def test_browser_computer_click_uses_virtual_cursor_by_default(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    monkeypatch.setattr(controller, "_capture_action_result_screenshot", lambda payload, marker: {"click_marker": marker})
    monkeypatch.setattr(controller, "_window_at_point", lambda x, y: None)
    monkeypatch.setattr(
        controller,
        "_darwin_click",
        lambda payload: (_ for _ in ()).throw(AssertionError("physical click should not run")),
    )

    result = controller.run("computer.click", {"x": 10, "y": 20}, yolo_mode=True)

    assert result["executed"] is True
    assert result["virtual_cursor"] is True
    assert result["target"] == {"x": 10, "y": 20}
    assert result["click_marker"]["screen_x"] == 10
    assert result["click_marker"]["screen_y"] == 20


def test_browser_computer_key_clears_chrome_background(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")

    captured = {}

    def fake_run(cmd, check=False, capture_output=False, text=False, **kwargs):
        captured["cmd"] = cmd

        class Completed:
            stdout = "cleared\n"

        return Completed()

    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    result = controller.run(
        "computer.key",
        {"key": "backspace", "app": "Google Chrome", "background": True},
        yolo_mode=True,
    )

    assert result["background"] is True
    assert result["target_app"] == "Google Chrome"
    assert captured["cmd"][0] == "osascript"


def test_browser_computer_click_sets_target_window_for_background_keys(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    monkeypatch.setattr(controller, "_capture_action_result_screenshot", lambda payload, marker: {})
    monkeypatch.setattr(
        controller,
        "_window_at_point",
        lambda x, y: {
            "app": "Google Chrome",
            "title": "ChatGPT - Google Chrome",
            "x": 20,
            "y": 40,
            "width": 1200,
            "height": 800,
            "active": False,
        },
    )

    controller.run("computer.click", {"x": 120, "y": 140}, yolo_mode=True)

    state = controller._computer_state()
    assert state["target_window"]["app"] == "Google Chrome"
    assert controller._should_type_in_chrome_background({}) is False
    assert controller._should_type_in_chrome_background({"app": "Google Chrome", "background": True}) is True


def test_browser_computer_background_type_failure_does_not_fall_back_to_physical(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_computer_state(
        {
            "target_window": {
                "app": "Google Chrome",
                "title": "ChatGPT - Google Chrome",
                "x": 20,
                "y": 40,
                "width": 1200,
                "height": 800,
                "active": False,
            }
        }
    )
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(controller, "_darwin_type_in_chrome_background", lambda text, payload: False)
    monkeypatch.setattr(
        controller,
        "_apple_script",
        lambda action, payload: (_ for _ in ()).throw(AssertionError("physical typing should not run")),
    )

    result = controller.run("computer.type", {"text": "hello", "background": True}, yolo_mode=True)

    assert result["is_error"] is True
    assert result["executed"] is False
    assert result["background"] is True
    assert "Chrome background text entry failed" in result["reason"]


def test_browser_computer_background_type_can_fall_back_to_foreground_when_allowed(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_sessions(
        {
            "chrome_target": {
                "app": "Google Chrome",
                "url": "https://chatgpt.com/",
                "window_index": 2,
                "tab_index": 5,
            }
        }
    )
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(controller, "_darwin_type_in_chrome_background", lambda text, payload: False)
    monkeypatch.setattr(controller, "_list_windows", lambda: [])
    monkeypatch.setattr(controller, "_activate_chrome_target", lambda payload: True)

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    result = controller.run(
        "computer.type",
        {
            "text": "hello",
            "app": "Google Chrome",
            "background": True,
            "allow_foreground_fallback": True,
        },
        yolo_mode=True,
    )

    assert result["executed"] is True
    assert result["foreground_fallback"] is True
    assert result["background_attempted"] is True
    assert result["driver_sequence"] == ["chrome_background_dom", "foreground_input"]
    assert result["background_failure"]["recovery"]["kind"] == "chrome_setting"
    assert calls[-1][:2] == ["osascript", "-e"]
    assert "keystroke" in calls[-1][2]


def test_browser_computer_select_window_respects_app_filter(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._list_windows = lambda: [
        {"app": "Codex", "title": "", "x": 0, "y": 0, "width": 1470, "height": 37, "active": True},
        {"app": "Google Chrome", "title": "", "x": 0, "y": 0, "width": 1470, "height": 37, "active": True},
        {"app": "Google Chrome", "title": "ChatGPT - Google Chrome", "x": 50, "y": 80, "width": 1200, "height": 800, "active": False},
    ]
    controller._active_window = lambda: {"app": "Codex", "title": "", "x": 0, "y": 0, "width": 1470, "height": 37, "active": True}

    result = controller.run("computer.select_window", {"app": "Google Chrome", "focus": False}, yolo_mode=True)

    assert result["selected"] is True
    assert result["target_window"]["app"] == "Google Chrome"
    assert controller._computer_state()["target_window"]["title"] == "ChatGPT - Google Chrome"


def test_browser_computer_select_window_failure_clears_stale_target(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_computer_state(
        {
            "target_window": {
                "app": "Codex",
                "title": "",
                "x": 0,
                "y": 0,
                "width": 1470,
                "height": 37,
                "active": True,
            }
        }
    )
    controller._list_windows = lambda: [
        {"app": "Codex", "title": "", "x": 0, "y": 0, "width": 1470, "height": 37, "active": True},
    ]
    controller._chrome_tabs = lambda: []

    result = controller.run("computer.select_window", {"app": "Google Chrome", "focus": False}, yolo_mode=True)

    assert result["selected"] is False
    assert "target_window" not in controller._computer_state()


def test_browser_computer_select_window_can_store_hidden_chrome_tab_target(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._list_windows = lambda: [
        {"app": "Codex", "title": "", "x": 0, "y": 0, "width": 1470, "height": 37, "active": True},
    ]
    controller._chrome_tabs = lambda: [
        {
            "app": "Google Chrome",
            "window_index": 2,
            "tab_index": 5,
            "active": True,
            "title": "ChatGPT",
            "url": "https://chatgpt.com/",
        }
    ]

    result = controller.run("computer.select_window", {"app": "Google Chrome", "title": "ChatGPT", "focus": False}, yolo_mode=True)

    assert result["selected"] is True
    assert result["background_target_only"] is True
    assert result["chrome_target"]["window_index"] == 2
    assert controller._read_sessions()["chrome_target"]["tab_index"] == 5
    assert "target_window" not in controller._computer_state()


def test_browser_computer_context_exposes_ai_cursor_and_selected_window(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_computer_state(
        {
            "ai_cursor": {"x": 10, "y": 20, "origin": "top_left"},
            "target_window": {
                "app": "Google Chrome",
                "title": "ChatGPT - Google Chrome",
                "x": 50,
                "y": 80,
                "width": 1200,
                "height": 800,
            },
        }
    )
    controller._active_window = lambda: {"app": "Codex", "title": "", "x": 0, "y": 0, "width": 1470, "height": 900}
    controller._list_windows = lambda: []
    controller._chrome_tabs = lambda: []
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: {"x": 1, "y": 2, "origin": "top_left"}))

    result = controller.run("computer.context", {"include_windows": False}, yolo_mode=True)

    assert result["ai_cursor"]["x"] == 10
    assert result["selected_window"]["app"] == "Google Chrome"
    assert result["active_window"]["app"] == "Codex"
    assert "windows" not in result


def test_browser_computer_context_reports_chrome_background_blocker(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._active_window = lambda: {"app": "Codex", "title": "", "x": 0, "y": 0, "width": 1470, "height": 900}
    controller._chrome_tabs = lambda: [
        {
            "app": "Google Chrome",
            "window_index": 1,
            "tab_index": 3,
            "title": "ChatGPT",
            "url": "https://chatgpt.com/",
        }
    ]
    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")

    def fake_execute(js, payload):
        controller._last_background_error = "Executing JavaScript through AppleScript is turned off. Apple Events denied."
        raise RuntimeError("blocked")

    controller._darwin_execute_chrome_background_js = fake_execute

    result = controller.run("computer.context", {"include_windows": False}, yolo_mode=True)

    assert result["chrome_background_control"]["available"] is False
    assert result["chrome_background_control"]["recovery"]["kind"] == "chrome_setting"
    assert "Allow JavaScript from Apple Events" in result["chrome_background_control"]["reason"]


def test_browser_computer_context_clears_tiny_stale_selected_window(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_computer_state(
        {
            "target_window": {
                "app": "Google Chrome",
                "title": "",
                "x": 0,
                "y": 0,
                "width": 1470,
                "height": 37,
                "active": True,
            }
        }
    )
    controller._active_window = lambda: {"app": "Codex", "title": "", "x": 0, "y": 0, "width": 1470, "height": 900}
    controller._chrome_tabs = lambda: []

    result = controller.run("computer.context", {"include_windows": False}, yolo_mode=True)

    assert result["selected_window"] is None
    assert "target_window" not in controller._computer_state()


def test_chat_send_persists_user_attachment_metadata(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {
                "role": "user",
                "content": "hello",
                "attachments": [
                    {"name": "notes.md", "content": "hello from attachment", "size": 21, "type": "text/markdown"},
                    {"name": "photo.png", "size": 128, "type": "image/png"},
                ],
                "metadata": {"selected_tools": ["local_file"]},
            },
            "tools": ["local_file"],
            "params": {"tool_policy": {"selected_tools": ["local_file"]}},
        },
        {},
    )

    assert result["status"] == "ok"
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    stored_user = persisted["conversations"][conversation["id"]]["messages"][0]
    assert stored_user["metadata"]["attachments"][0]["name"] == "notes.md"
    assert stored_user["metadata"]["attachments"][1]["name"] == "photo.png"
    assert stored_user["metadata"]["selected_tools"] == ["local_file"]
    history_path = storage_path.parent / "conversations" / conversation["id"] / "history.json"
    workspace_path = storage_path.parent / "conversations" / conversation["id"] / "workspace"
    assert history_path.exists()
    assert (workspace_path / "attachments" / "notes.md").read_text(encoding="utf-8") == "hello from attachment"
    assert stored_user["metadata"]["workspace_attachments"][0]["workspace_path"] == "workspace/attachments/notes.md"
    user_text = "\n".join(block.get("text", "") for block in stored_user["content"])
    assert "添付ファイル: notes.md" in user_text
    assert "hello from attachment" in user_text
    assert "photo.png" not in user_text
    ChatStore._instance = None


def test_chat_send_accepts_attachment_only_message(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {
                "role": "user",
                "content": "",
                "attachments": [{"name": "notes.md", "content": "hello", "size": 5, "type": "text/markdown"}],
            },
        },
        {},
    )

    assert result["status"] == "ok"
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    stored_user = persisted["conversations"][conversation["id"]]["messages"][0]
    user_text = "\n".join(block.get("text", "") for block in stored_user["content"])
    assert "添付ファイルを確認してください。" in user_text
    assert "添付ファイル: notes.md" in user_text
    assert "hello" in user_text
    assert stored_user["metadata"]["attachments"][0]["name"] == "notes.md"
    ChatStore._instance = None


def test_chat_send_includes_workspace_attachment_content(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {
                "role": "user",
                "content": "このファイル見て",
                "attachments": [
                    {
                        "name": "README.md",
                        "content": "# Workspace Notes",
                        "size": 17,
                        "type": "text/plain",
                        "source": "workspace",
                        "sourcePath": "README.md",
                    }
                ],
            },
        },
        {},
    )

    assert result["status"] == "ok"
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    stored_user = persisted["conversations"][conversation["id"]]["messages"][0]
    user_text = "\n".join(block.get("text", "") for block in stored_user["content"])
    assert "添付ファイル: README.md" in user_text
    assert "# Workspace Notes" in user_text
    ChatStore._instance = None


def test_chat_send_resolves_selected_tool_ids_before_provider_adaptation(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.tool.registry import ToolRegistry
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    ToolRegistry._instance = None

    captured = {}

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            captured["tools"] = payload["tools"]
            return {"status": "ok", "data": {"content": [{"type": "text", "text": "ok"}], "finish_reason": "stop"}}
        raise AssertionError(name)

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "read"},
            "tools": ["coding_file_read"],
        },
        {"call_handler": call_handler},
    )

    assert result["status"] == "ok"
    assert captured["tools"][0]["type"] == "function"
    assert captured["tools"][0]["function"]["name"] == "coding_file_read"
    assert result["data"]["metadata"]["attached_tools"] == ["coding_file_read"]
    ChatStore._instance = None
    ToolRegistry._instance = None


def test_chat_send_drops_unknown_selected_tool_ids(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from domain.tool.registry import ToolRegistry
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    ToolRegistry._instance = None

    captured = {}

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            captured["tools"] = payload["tools"]
            return {"status": "ok", "data": {"content": [{"type": "text", "text": "ok"}], "finish_reason": "stop"}}
        raise AssertionError(name)

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "read"},
            "tools": ["coding_file_read", "missing_tool"],
        },
        {"call_handler": call_handler},
    )

    assert result["status"] == "ok"
    assert "missing_tool" not in captured["tools"]
    assert [tool["function"]["name"] for tool in captured["tools"]] == ["coding_file_read"]
    ChatStore._instance = None
    ToolRegistry._instance = None


def test_chat_send_preserves_dict_tool_definitions(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    captured = {}
    tool_def = {
        "type": "function",
        "function": {
            "name": "custom_lookup",
            "description": "Look up custom data.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            captured["tools"] = payload["tools"]
            return {"status": "ok", "data": {"content": [{"type": "text", "text": "ok"}], "finish_reason": "stop"}}
        raise AssertionError(name)

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "lookup"},
            "tools": [tool_def],
        },
        {"call_handler": call_handler},
    )

    assert result["status"] == "ok"
    assert captured["tools"] == [tool_def]
    ChatStore._instance = None


def test_coding_context_and_branch_blocks(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    from blocks.coding.context import run as context_run
    from blocks.coding.git_branch import run as branch_run
    from domain.safety.approval import approve, reset_approval_state_for_tests

    reset_approval_state_for_tests()

    context_result = context_run({"workspace_root": str(tmp_path)}, {})
    assert context_result["status"] == "ok"
    data = context_result["data"]
    assert data["branch"] in {"main", "master"}
    assert data["root_folder"] == str(tmp_path)
    assert data["files"] == ["README.md"]
    assert all(isinstance(item, str) for item in data["files"])
    assert any(item["name"] == "README.md" for item in data["entries"])
    assert data["git"]["branch"] == data["branch"]

    nested_context_result = context_run({"workspace_root": str(tmp_path), "directory": "src"}, {})
    assert nested_context_result["status"] == "ok"
    assert nested_context_result["data"]["directory"] == "src"
    assert nested_context_result["data"]["files"] == ["src/app.py"]

    branch_result = branch_run({"workspace_root": str(tmp_path)}, {})
    assert branch_result["status"] == "ok"
    assert branch_result["data"]["branch"] in {"main", "master"}
    assert branch_result["data"]["branches"]

    switched_result = branch_run(
        {"workspace_root": str(tmp_path), "action": "switch", "branch": "feature/footer", "create": True},
        {},
    )
    assert switched_result["status"] == "ok"
    assert switched_result["data"]["approval_required"] is True

    approval = approve(switched_result["data"]["approval_request_id"])
    switched_result = branch_run(
        {
            "workspace_root": str(tmp_path),
            "action": "switch",
            "branch": "feature/footer",
            "create": True,
            "approval_token": approval["token"],
        },
        {},
    )
    assert switched_result["status"] == "ok"
    assert switched_result["data"]["branch"] == "feature/footer"
    assert switched_result["data"]["switched"] is True
    assert switched_result["data"]["created"] is True

    list_result = branch_run({"workspace_root": str(tmp_path), "action": "list"}, {})
    assert list_result["status"] == "ok"
    assert "feature/footer" in list_result["data"]["branches"]


def test_direct_chat_completion_forwards_tools_and_tool_context(monkeypatch):
    import blocks.chat.send as send

    captured = {}

    class DummyClient:
        def resolve_provider(self, model):
            return object(), model

        def complete(self, model, messages, tools=None, params=None):
            captured["model"] = model
            captured["messages"] = messages
            captured["tools"] = tools
            captured["params"] = params
            return {
                "content": [{"type": "text", "text": "ok"}],
                "finish_reason": "stop",
                "usage": {},
            }

    monkeypatch.setattr(send, "AIClient", DummyClient)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Evaluate arithmetic.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    response = send._complete_with_tools(
        "openrouter/test-model",
        [{"role": "user", "content": "2+2"}],
        tools,
        {},
        None,
        {"temperature": 0},
    )

    assert captured["tools"] == tools
    assert captured["params"]["temperature"] == 0
    assert "calculator" in captured["messages"][0]["content"]
    assert response["metadata"]["attached_tools"] == ["calculator"]


def test_chat_tool_loop_replays_openai_tool_call_messages():
    import blocks.chat.send as send

    seen_messages = []

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            seen_messages.append(payload["messages"])
            if len(seen_messages) == 1:
                return {
                    "status": "ok",
                    "data": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "calculator",
                                "input": "{\"expression\":\"2+2\"}",
                            }
                        ],
                        "finish_reason": "tool_calls",
                    },
                }
            return {
                "status": "ok",
                "data": {
                    "content": [{"type": "text", "text": "tool result used"}],
                    "finish_reason": "stop",
                },
            }
        if name == "defaults.tool.invoke":
            return {"status": "ok", "data": {"result": "4"}}
        raise AssertionError(name)

    response = send._complete_with_tools(
        "openrouter/test-model",
        [{"role": "user", "content": "2+2"}],
        [{"type": "function", "function": {"name": "calculator", "parameters": {"type": "object"}}}],
        {},
        call_handler,
        {"max_tool_calls": 3},
    )

    assert response["content"][0]["text"] == "tool result used"
    assert seen_messages[1][-2]["role"] == "assistant"
    assert seen_messages[1][-2]["tool_calls"][0]["function"]["name"] == "calculator"
    assert seen_messages[1][-1]["role"] == "tool"
    assert seen_messages[1][-1]["tool_call_id"] == "call_1"


def test_chat_tool_loop_emits_realtime_tool_events():
    import blocks.chat.send as send

    calls = {"ai": 0}
    emitted = []

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            calls["ai"] += 1
            if calls["ai"] == 1:
                return {
                    "status": "ok",
                    "data": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "calculator",
                                "input": "{\"expression\":\"2+2\"}",
                            }
                        ],
                        "finish_reason": "tool_calls",
                    },
                }
            return {
                "status": "ok",
                "data": {
                    "content": [{"type": "text", "text": "4"}],
                    "finish_reason": "stop",
                },
            }
        if name == "defaults.tool.invoke":
            return {"status": "ok", "data": {"result": "4"}}
        raise AssertionError(name)

    response = send._complete_with_tools(
        "openrouter/test-model",
        [{"role": "user", "content": "2+2"}],
        [{"type": "function", "function": {"name": "calculator", "parameters": {"type": "object"}}}],
        {"stream_event_callback": emitted.append},
        call_handler,
        {"max_tool_calls": 3},
    )

    assert response["content"][0]["text"] == "4"
    assert [event["type"] for event in emitted] == [
        "status",
        "status",
        "tool_call_started",
        "tool_call_completed",
    ]
    assert emitted[2]["tool_name"] == "calculator"


def test_chat_tool_loop_marks_nested_tool_errors_in_events():
    import blocks.chat.send as send

    calls = {"ai": 0}
    emitted = []

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            calls["ai"] += 1
            if calls["ai"] == 1:
                return {
                    "status": "ok",
                    "data": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "computer_use",
                                "input": "{\"action\":\"type\",\"text\":\"hello\"}",
                            }
                        ],
                        "finish_reason": "tool_calls",
                    },
                }
            return {
                "status": "ok",
                "data": {"content": [{"type": "text", "text": "handled"}], "finish_reason": "stop"},
            }
        if name == "defaults.tool.invoke":
            return {
                "status": "ok",
                "data": {
                    "result": "type failed",
                    "is_error": True,
                    "widget": {"is_error": True},
                },
            }
        raise AssertionError(name)

    response = send._complete_with_tools(
        "openrouter/test-model",
        [{"role": "user", "content": "type hello"}],
        [{"type": "function", "function": {"name": "computer_use", "parameters": {"type": "object"}}}],
        {"stream_event_callback": emitted.append},
        call_handler,
        {"max_tool_calls": 3},
    )

    completed = [event for event in response["events"] if event["type"] == "tool_call_completed"][0]
    streamed_completed = [event for event in emitted if event["type"] == "tool_call_completed"][0]
    assert completed["is_error"] is True
    assert streamed_completed["is_error"] is True


def test_chat_tool_loop_stops_on_chrome_setting_recovery():
    import blocks.chat.send as send

    calls = {"ai": 0, "tool": 0}
    emitted = []

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            calls["ai"] += 1
            return {
                "status": "ok",
                "data": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_chrome",
                            "name": "computer_use",
                            "input": "{\"action\":\"type\",\"text\":\"hello\",\"app\":\"Google Chrome\"}",
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
            }
        if name == "defaults.tool.invoke":
            calls["tool"] += 1
            return {
                "status": "ok",
                "data": {
                    "result": "Chrome background text entry failed.",
                    "is_error": True,
                    "recovery": {
                        "kind": "chrome_setting",
                        "setting": "Allow JavaScript from Apple Events",
                        "path": "View > Developer > Allow JavaScript from Apple Events",
                    },
                },
            }
        raise AssertionError(name)

    response = send._complete_with_tools(
        "google/gemma-4-31b-it",
        [{"role": "user", "content": "send hello in existing Chrome"}],
        [{"type": "function", "function": {"name": "computer_use", "parameters": {"type": "object"}}}],
        {"stream_event_callback": emitted.append},
        call_handler,
        {"max_tool_calls": 12},
    )

    assert calls == {"ai": 1, "tool": 1}
    assert response["finish_reason"] == "tool_blocked"
    assert response["metadata"]["tool_blocked"] is True
    assert response["metadata"]["tool_blocked_kind"] == "chrome_setting"
    assert "Allow JavaScript from Apple Events" in response["content"][0]["text"]
    assert [event["phase"] for event in emitted if event["type"] == "status"][-1] == "tool_blocked"


def test_chat_tool_loop_does_not_stop_when_context_reports_chrome_dom_probe_failure():
    import blocks.chat.send as send

    calls = {"ai": 0, "tool": 0}

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            calls["ai"] += 1
            if calls["ai"] > 1:
                return {
                    "status": "ok",
                    "data": {"content": [{"type": "text", "text": "context noted"}], "finish_reason": "stop"},
                }
            return {
                "status": "ok",
                "data": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_context",
                            "name": "computer_use",
                            "input": "{\"action\":\"context\"}",
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
            }
        if name == "defaults.tool.invoke":
            calls["tool"] += 1
            return {
                "status": "ok",
                "data": {
                    "result": "context",
                    "is_error": False,
                    "widget": {
                        "action": "computer.context",
                        "chrome_background_control": {
                            "available": False,
                            "reason": "Chrome background entry failed because Chrome has disabled JavaScript from Apple Events.",
                            "recovery": {
                                "kind": "chrome_setting",
                                "setting": "Allow JavaScript from Apple Events",
                                "path": "View > Developer > Allow JavaScript from Apple Events",
                            },
                        },
                    },
                },
            }
        raise AssertionError(name)

    response = send._complete_with_tools(
        "google/gemma-4-31b-it",
        [{"role": "user", "content": "画面を切り替えず既存のGoogle ChromeのChatGPTにhelloを送って"}],
        [{"type": "function", "function": {"name": "computer_use", "parameters": {"type": "object"}}}],
        {},
        call_handler,
        {"max_tool_calls": 12},
    )

    assert calls == {"ai": 2, "tool": 1}
    assert response["finish_reason"] == "stop"
    assert response["content"][0]["text"] == "context noted"


def test_chat_tool_loop_does_not_stop_after_successful_foreground_fallback():
    import blocks.chat.send as send

    calls = {"ai": 0, "tool": 0}

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            calls["ai"] += 1
            if calls["ai"] > 1:
                return {
                    "status": "ok",
                    "data": {"content": [{"type": "text", "text": "sent with fallback"}], "finish_reason": "stop"},
                }
            return {
                "status": "ok",
                "data": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_type",
                            "name": "computer_use",
                            "input": "{\"action\":\"type\",\"text\":\"hello\",\"app\":\"Google Chrome\",\"background\":true,\"allow_foreground_fallback\":true}",
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
            }
        if name == "defaults.tool.invoke":
            calls["tool"] += 1
            return {
                "status": "ok",
                "data": {
                    "result": "computer_use computer.type completed",
                    "is_error": False,
                    "widget": {
                        "action": "computer.type",
                        "executed": True,
                        "foreground_fallback": True,
                        "background_failure": {
                            "recovery": {
                                "kind": "chrome_setting",
                                "setting": "Allow JavaScript from Apple Events",
                            }
                        },
                    },
                },
            }
        raise AssertionError(name)

    response = send._complete_with_tools(
        "google/gemma-4-31b-it",
        [{"role": "user", "content": "background first, fallback ok"}],
        [{"type": "function", "function": {"name": "computer_use", "parameters": {"type": "object"}}}],
        {},
        call_handler,
        {"max_tool_calls": 12},
    )

    assert calls == {"ai": 2, "tool": 1}
    assert response["finish_reason"] == "stop"
    assert response["content"][0]["text"] == "sent with fallback"


def test_tool_result_recovery_kind_infers_legacy_chrome_setting_error():
    import blocks.chat.send as send

    assert (
        send._tool_result_recovery_kind(
            {
                "status": "ok",
                "data": {
                    "result": (
                        "Chrome background text entry failed. "
                        "Enable Chrome's 'Allow JavaScript from Apple Events' setting."
                    ),
                    "is_error": True,
                },
            }
        )
        == "chrome_setting"
    )


def test_chat_tool_loop_honors_stream_cancel_before_tool_execution():
    import blocks.chat.send as send

    cancelled = {"value": False}

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            cancelled["value"] = True
            return {
                "status": "ok",
                "data": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "calculator",
                            "input": "{\"expression\":\"2+2\"}",
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
            }
        if name == "defaults.tool.invoke":
            raise AssertionError("tool should not run after cancellation")
        raise AssertionError(name)

    try:
        send._complete_with_tools(
            "openrouter/test-model",
            [{"role": "user", "content": "2+2"}],
            [{"type": "function", "function": {"name": "calculator", "parameters": {"type": "object"}}}],
            {"is_cancelled": lambda: cancelled["value"]},
            call_handler,
            {"max_tool_calls": 3},
        )
    except send._ChatCancelled:
        pass
    else:
        raise AssertionError("expected chat cancellation")


def test_chat_tool_loop_returns_text_when_tool_limit_reached():
    import blocks.chat.send as send

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            return {
                "status": "ok",
                "data": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_limit",
                            "name": "calculator",
                            "input": "{\"expression\":\"2+2\"}",
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
            }
        if name == "defaults.tool.invoke":
            return {"status": "ok", "data": {"result": "4"}}
        raise AssertionError(name)

    response = send._complete_with_tools(
        "openrouter/test-model",
        [{"role": "user", "content": "keep using tools"}],
        [{"type": "function", "function": {"name": "calculator", "parameters": {"type": "object"}}}],
        {},
        call_handler,
        {"max_tool_calls": 1},
    )

    assert response["content"][0]["type"] == "text"
    assert "tool call の上限" in response["content"][0]["text"]
    assert response["metadata"]["max_tool_calls_reached"] is True
    assert response["metadata"]["pending_tool_uses"][0]["name"] == "calculator"


def test_chat_tool_loop_passes_execution_context_to_tool_invoke():
    import blocks.chat.send as send

    calls = {"ai": 0}
    captured_tool_payload = {}

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            calls["ai"] += 1
            if calls["ai"] == 1:
                return {
                    "status": "ok",
                    "data": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "browser_use",
                                "input": "{\"action\":\"screenshot\"}",
                            }
                        ],
                        "finish_reason": "tool_calls",
                    },
                }
            return {
                "status": "ok",
                "data": {
                    "content": [{"type": "text", "text": "done"}],
                    "finish_reason": "stop",
                },
            }
        if name == "defaults.tool.invoke":
            captured_tool_payload.update(payload)
            return {"status": "ok", "data": {"result": "screenshot ready"}}
        raise AssertionError(name)

    send._complete_with_tools(
        "google/gemma-4-31b-it",
        [{"role": "user", "content": "look at the screen"}],
        [{"type": "function", "function": {"name": "browser_use", "parameters": {"type": "object"}}}],
        {
            "conversation_id": "c1",
            "conversation_workspace_dir": "/tmp/rumi-c1",
            "profile_policy": {"selected_tools": ["browser_use"]},
        },
        call_handler,
        {"max_tool_calls": 2},
    )

    assert captured_tool_payload["tool_name"] == "browser_use"
    assert captured_tool_payload["context"]["conversation_id"] == "c1"
    assert captured_tool_payload["context"]["conversation_workspace_dir"] == "/tmp/rumi-c1"
    assert captured_tool_payload["context"]["capability_graph"]["tool_name"] == "browser_use"


def test_tool_invoke_merges_payload_context(monkeypatch):
    import blocks.tool.invoke as invoke

    captured = {}

    class DummyChecker:
        def decide(self, tool_name, context=None, arguments=None, tool_def=None):
            captured["permission_context"] = context
            return {"allowed": True, "action": "allow", "matched_by": "test"}

    class DummyExecutor:
        def execute(self, tool_name, arguments, context):
            captured["executor_context"] = context
            return {"result": "ok", "is_error": False, "widget": None}

    monkeypatch.setattr(invoke, "PermissionChecker", lambda registry=None: DummyChecker())
    monkeypatch.setattr(invoke, "ToolExecutor", lambda: DummyExecutor())

    result = invoke.run(
        {
            "tool_name": "calculator",
            "arguments": {"expression": "2+2"},
            "context": {
                "conversation_id": "c1",
                "conversation_workspace_dir": "/tmp/rumi-c1",
            },
        },
        {"request_id": "outer"},
    )

    assert result["status"] == "ok"
    assert captured["permission_context"]["conversation_id"] == "c1"
    assert captured["permission_context"]["request_id"] == "outer"
    assert captured["executor_context"]["conversation_workspace_dir"] == "/tmp/rumi-c1"


def test_browser_screenshot_tool_result_adds_image_for_vision_models():
    import blocks.chat.send as send

    messages = []
    send._append_tool_result_message(
        messages,
        "browser_computer",
        {
            "status": "ok",
            "data": {
                "result": "screenshot",
                "action": "computer.screenshot",
                "data_url": "data:image/png;base64,aGVsbG8=",
                "image_size": {"width": 1440, "height": 900},
                "action_coordinate_system": {"width": 720, "height": 450, "x_range": [0, 719], "y_range": [0, 449]},
                "model_image_size": {"width": 640, "height": 400},
                "model_to_screen_scale": {"x": 2.25, "y": 2.25},
                "model_to_action_scale": {"x": 1.125, "y": 1.125},
            },
        },
        "call_1",
        model="google/gemma-4-31b-it",
    )

    assert messages[0]["role"] == "tool"
    assert messages[1]["role"] == "user"
    assert "action=move" in messages[1]["content"][0]["text"]
    assert "width=1440 height=900" in messages[1]["content"][0]["text"]
    assert "width=720 height=450" in messages[1]["content"][0]["text"]
    assert "scale x=1.1250, y=1.1250" in messages[1]["content"][0]["text"]
    assert messages[1]["content"][1]["image_url"]["url"] == "data:image/png;base64,aGVsbG8="


def test_browser_screenshot_tool_result_respects_provider_attachment_opt_out(monkeypatch):
    import blocks.chat.send as send

    class FakeClient:
        def _runtime_model_matches(self, model):
            return [
                {
                    "capabilities": ["vision"],
                    "metadata": {"supports_attachments": False},
                }
            ]

    monkeypatch.setattr(send, "AIClient", FakeClient)
    messages = []
    send._append_tool_result_message(
        messages,
        "browser_computer",
        {
            "status": "ok",
            "data": {
                "result": "screenshot",
                "data_url": "data:image/png;base64,aGVsbG8=",
            },
        },
        "call_1",
        model="provider/no-attachments",
    )

    assert len(messages) == 1
    assert messages[0]["role"] == "tool"


def test_attachment_image_blocks_validate_actual_data_url_bytes():
    import blocks.chat.send as send

    tiny_png = "data:image/png;base64,aGVsbG8="
    too_large_encoded = "A" * (((send.MAX_ATTACHMENT_IMAGE_BYTES + 1 + 2) // 3) * 4)
    too_large = "data:image/png;base64," + too_large_encoded

    blocks = send._attachment_image_blocks(
        [
            {"type": "image/png", "size": 1, "dataUrl": tiny_png},
            {"type": "image/png", "size": 1, "dataUrl": "data:image/png;base64,not valid"},
            {"type": "image/png", "size": 1, "dataUrl": too_large},
        ]
    )

    assert len(blocks) == 1
    assert blocks[0]["image_url"]["url"] == tiny_png


def test_browser_screenshot_tool_log_compacts_inline_image_data():
    import blocks.chat.send as send

    compact = send._compact_tool_log_value(
        {
            "status": "ok",
            "data": {
                "widget": {
                    "data_url": "data:image/jpeg;base64,abc123",
                    "model_image_path": "/tmp/screenshot-model.jpg",
                }
            },
        }
    )

    assert compact["data"]["widget"]["data_url"] == "[image data saved as artifact]"
    assert compact["data"]["widget"]["model_image_path"] == "/tmp/screenshot-model.jpg"
    assert send._compact_tool_log_value("see data:image/png;base64,abc123 now") == "see [image data saved as artifact] now"


def test_browser_computer_screenshot_result_includes_coordinate_metadata(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    screenshot = tmp_path / "screen.png"
    model_image = tmp_path / "screen-model.png"
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
    screenshot.write_bytes(png_header + b"\x00\x00\x05\xa0\x00\x00\x03\x84")
    model_image.write_bytes(png_header + b"\x00\x00\x02\x80\x00\x00\x01\x90")
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: {"x": 12, "y": 34, "origin": "top_left"}))
    monkeypatch.setattr(
        BrowserComputerController,
        "_action_coordinate_system",
        staticmethod(
            lambda system, image_size: {
                "origin": "top_left",
                "unit": "display_coordinate",
                "screen": "primary",
                "x": 0,
                "y": 0,
                "width": 720,
                "height": 450,
                "x_range": [0, 719],
                "y_range": [0, 449],
            }
        ),
    )

    result = BrowserComputerController()._screenshot_result(screenshot, model_image, "Darwin")

    assert result["image_size"] == {"width": 1440, "height": 900}
    assert result["model_image_size"] == {"width": 640, "height": 400}
    assert result["coordinate_system"]["origin"] == "top_left"
    assert result["coordinate_system"]["x_range"] == [0, 1439]
    assert result["action_coordinate_system"]["width"] == 720
    assert result["model_to_screen_scale"] == {"x": 2.25, "y": 2.25}
    assert result["model_to_action_scale"] == {"x": 1.125, "y": 1.125}
    assert result["screenshot_to_action_scale"] == {"x": 0.5, "y": 0.5}
    assert result["cursor"] == {"x": 12, "y": 34, "origin": "top_left"}
    assert result["cursor_move_contract"]["action"] == "move"


def test_tool_activity_events_and_logs_redact_secret_values():
    import blocks.chat.send as send

    calls = {"ai": 0}

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            calls["ai"] += 1
            if calls["ai"] == 1:
                return {
                    "status": "ok",
                    "data": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_secret",
                                "name": "secret_echo",
                                "input": "{\"api_key\":\"sk-live\",\"query\":\"ok\"}",
                            }
                        ],
                        "finish_reason": "tool_calls",
                    },
                }
            return {
                "status": "ok",
                "data": {"content": [{"type": "text", "text": "done"}], "finish_reason": "stop"},
            }
        if name == "defaults.tool.invoke":
            return {"status": "ok", "data": {"token": "secret-token", "result": "safe"}}
        raise AssertionError(name)

    response = send._complete_with_tools(
        "stub/default",
        [{"role": "user", "content": "use tool"}],
        [{"type": "function", "function": {"name": "secret_echo", "parameters": {"type": "object"}}}],
        {},
        call_handler,
        {"max_tool_calls": 2},
    )
    started = [event for event in response["events"] if event["type"] == "tool_call_started"][0]
    completed = [event for event in response["events"] if event["type"] == "tool_call_completed"][0]
    log = response["tool_logs"][0]

    assert started["tool_call_id"] == "call_secret"
    assert completed["tool_call_id"] == "call_secret"
    assert started["arguments"]["api_key"] == "[redacted]"
    assert log["arguments"]["api_key"] == "[redacted]"
    assert log["result"]["data"]["token"] == "[redacted]"


def test_browser_screenshots_endpoint_is_conversation_and_owner_scoped(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.browser_screenshots import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    screenshot_path = store.conversation_workspace_dir("placeholder").parent / "placeholder.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_bytes(b"image-bytes")

    conversation = store.create_conversation(
        model="stub/default",
        metadata={"owner_user_id": "user-1"},
    )
    other = store.create_conversation(model="stub/default", metadata={"owner_user_id": "user-1"})
    screenshot_path = store.conversation_workspace_dir(conversation["id"]) / "tools" / "screen.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_bytes(b"image-bytes")
    assistant = store.add_message(
        conversation["id"],
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "done"}],
            "tool_logs": [
                {
                    "tool_name": "browser_computer",
                    "tool_call_id": "call_1",
                    "result": {
                        "data": {
                            "path": str(screenshot_path),
                            "action": "computer.click",
                            "click_marker": {"x": 10, "y": 20},
                            "image_size": {"width": 100, "height": 80},
                        }
                    },
                }
            ],
        },
    )

    ok_result = run(
        {
            "conversation_id": conversation["id"],
            "run_id": assistant["id"],
            "_headers": {"X-Rumi-User-Id": "user-1"},
        },
        {},
    )
    wrong_conversation = run(
        {
            "conversation_id": other["id"],
            "run_id": assistant["id"],
            "_headers": {"X-Rumi-User-Id": "user-1"},
        },
        {},
    )
    wrong_owner = run(
        {
            "conversation_id": conversation["id"],
            "run_id": assistant["id"],
            "_headers": {"X-Rumi-User-Id": "user-2"},
        },
        {},
    )

    assert ok_result["status"] == "ok"
    assert ok_result["data"]["screenshots"][0]["data_url"].startswith("data:image/png;base64,")
    assert ok_result["data"]["screenshots"][0]["click_marker"] == {"x": 10, "y": 20}
    assert ok_result["data"]["screenshots"][0]["image_size"] == {"width": 100, "height": 80}
    assert wrong_conversation["status"] == "error"
    assert wrong_conversation["error"]["code"] == "NOT_FOUND"
    assert wrong_owner["status"] == "error"
    assert wrong_owner["error"]["code"] == "FORBIDDEN"
    ChatStore._instance = None


def test_chat_store_splits_loaded_inline_thoughts(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    conversation_id = "conv-1"
    storage_path.parent.mkdir(parents=True)
    storage_path.write_text(
        json.dumps(
            {
                "conversations": {
                    conversation_id: {
                        "id": conversation_id,
                        "title": "New Conversation",
                        "created_at": 1,
                        "updated_at": 1,
                        "messages": [
                            {
                                "id": "msg-1",
                                "role": "assistant",
                                "content": [{"type": "text", "text": "<thought>hidden</thought>shown"}],
                                "raw_text": "<thought>hidden</thought>shown",
                            }
                        ],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.get_conversation(conversation_id)
    message = conversation["messages"][0]
    assert message["content"][0]["text"] == "shown"
    assert message["metadata"]["thinking"]["transcript"] == "hidden"
    ChatStore._instance = None


def test_builtin_calculator_returns_real_arithmetic_result():
    from domain.tool.executor import ToolExecutor

    result = ToolExecutor().execute("calculator", {"expression": "2 + 2 * 3"}, {})

    assert result["is_error"] is False
    assert result["result"] == "Calculated: 2 + 2 * 3 = 8"


def test_coding_tools_are_exposed_through_tool_registry():
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    registry = ToolRegistry()
    names = {tool["tool_id"] for tool in registry.list_tools()}

    assert {
        "coding_file_read",
        "coding_file_write",
        "coding_file_patch",
        "coding_terminal_exec",
        "coding_git_status",
        "todo",
        "subagent",
        "browser_use",
        "computer_use",
    } <= names


def test_tool_executor_dispatches_coding_handler_with_yolo_policy(tmp_path, monkeypatch):
    from domain.tool.executor import ToolExecutor
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    monkeypatch.chdir(tmp_path)
    result = ToolExecutor().execute(
        "coding_file_create",
        {"path": "created.txt", "content": "hello"},
        {"profile_policy": {"yolo_mode": True}},
    )

    assert result["is_error"] is False
    assert json.loads(result["result"])["created"] is True
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "hello"

    ToolRegistry._instance = None
    approval = ToolExecutor().execute(
        "coding_file_write",
        {"path": "needs-approval.txt", "content": "blocked"},
        {},
    )

    assert approval["is_error"] is False
    assert approval["widget"]["approval_required"] is True
    assert not (tmp_path / "needs-approval.txt").exists()


def test_coding_handlers_do_not_trust_body_approved_flag(tmp_path, monkeypatch):
    from blocks.coding.file_write import run as file_write_run
    from blocks.coding.terminal_exec import run as terminal_exec_run

    monkeypatch.chdir(tmp_path)

    write = file_write_run({"path": "pwned.txt", "content": "blocked", "approved": True}, {})
    assert write["status"] == "ok"
    assert write["data"]["approval_required"] is True
    assert not (tmp_path / "pwned.txt").exists()

    command = "python3 -c 'open(\"terminal-pwned.txt\", \"w\").write(\"blocked\")'"
    terminal = terminal_exec_run({"command": command, "approved": True}, {})
    assert terminal["status"] == "ok"
    assert terminal["data"]["approval_required"] is True
    assert terminal["data"]["exit_code"] is None
    assert not (tmp_path / "terminal-pwned.txt").exists()


def test_coding_handlers_accept_only_server_approval_context(tmp_path, monkeypatch):
    from blocks.coding.file_write import run as file_write_run

    monkeypatch.chdir(tmp_path)

    result = file_write_run(
        {"path": "approved.txt", "content": "ok"},
        {"_tool_server_approved": True},
    )

    assert result["status"] == "ok"
    assert result["data"]["written"] is True
    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "ok"


def test_direct_coding_route_cannot_execute_with_forged_approved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = _collect_defaultspack_routes()
    route = next(
        item
        for item in registry.routes
        if item["method"] == "POST" and item["pattern"] == "/api/coding/files/write"
    )

    result = route["handler"](
        {"path": "direct-pwned.txt", "content": "blocked", "approved": True},
        {"flow_id": "transport_direct"},
    )

    assert result["status"] == "ok"
    assert result["data"]["approval_required"] is True
    assert not (tmp_path / "direct-pwned.txt").exists()


def test_sensitive_routes_do_not_use_wildcard_cors():
    from ecosystem.defaultspack.transport.http import _is_sensitive_http_path

    assert _is_sensitive_http_path("/api/coding/terminal/exec") is True
    assert _is_sensitive_http_path("/api/coding/files/write") is True
    assert _is_sensitive_http_path("/api/integrations/secrets") is True
    assert _is_sensitive_http_path("/v1/conversations/c1/run-results/r1/browser-screenshots") is True
    assert _is_sensitive_http_path("/api/chat/conversations/c1/run-results/r1/browser-screenshots") is False
    assert _is_sensitive_http_path("/api/coding/files/read") is False


def test_fallback_routes_expose_agent_service_and_coding_surfaces():
    from ecosystem.defaultspack.transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

    routes = {(spec.method, spec.pattern, spec.block_module) for spec in _FALLBACK_HTTP_ROUTE_SPECS}

    assert ("GET", "/api/capabilities", "blocks.capability.list") in routes
    assert ("GET", "/api/agent-service/manifest", "blocks.capability.manifest") in routes
    assert ("GET", "/api/coding/context", "blocks.coding.context") in routes
    assert ("GET", "/api/coding/files", "blocks.coding.file_list") in routes
    assert ("GET", "/api/coding/git/branch", "blocks.coding.git_branch") in routes
    assert ("POST", "/api/coding/git/branch", "blocks.coding.git_branch") in routes
    assert ("POST", "/api/coding/files/diff", "blocks.coding.file_diff") in routes
    assert ("POST", "/api/coding/terminal/exec", "blocks.coding.terminal_exec") in routes
    assert ("POST", "/api/context/compact", "blocks.context.compact") in routes
    assert ("POST", "/api/artifacts", "blocks.artifact.create") in routes
    assert ("POST", "/api/research/local-search", "blocks.research.local_search") in routes
    assert ("POST", "/api/research/web-search", "blocks.research.web_search") in routes
    assert ("POST", "/api/research/reddit-search", "blocks.research.reddit_search") in routes
    assert ("POST", "/api/tools/browser-computer", "blocks.tool.browser_computer") in routes
    assert ("GET", "/api/ai/profiles", "blocks.ai.profiles") in routes
    assert ("POST", "/api/ui/clipboard", "blocks.ui.clipboard") in routes
    assert ("GET", "/api/agent/schedules", "blocks.agent.scheduler.list") in routes
    assert ("GET", "/api/agent/company/manifest", "ecosystem.rumi_operations_company_pack.blocks.agent.company.manifest") in routes
    assert ("GET", "/api/agent/company/status", "ecosystem.rumi_operations_company_pack.blocks.agent.company.status") in routes
    assert ("POST", "/api/agent/company/bootstrap", "ecosystem.rumi_operations_company_pack.blocks.agent.company.bootstrap") in routes
    assert ("GET", "/api/agent/org/roles", "blocks.agent.org.list_roles") in routes
    assert ("GET", "/api/chat/channels", "blocks.chat.channel.list") in routes
    assert ("POST", "/api/share", "blocks.share.create") in routes


def test_fallback_operations_company_routes_precede_generic_agent_status():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    captured = {}

    def fake_invoke(block_module, request_data, path_params, inject=None):
        captured["block_module"] = block_module
        captured["path_params"] = path_params
        return {"status": "ok"}

    server._invoke_fallback_block = fake_invoke
    handler, params, _, path_inject = server._match_route("GET", "/api/agent/company/status")

    assert params == {}
    assert path_inject == {}
    assert handler is not None
    assert handler({}, params) == {"status": "ok"}
    assert captured == {
        "block_module": "ecosystem.rumi_operations_company_pack.blocks.agent.company.status",
        "path_params": {},
    }


def test_ui_clipboard_write_uses_local_clipboard(monkeypatch):
    from blocks.ui import clipboard

    written = []
    monkeypatch.setattr(clipboard, "write_clipboard", lambda content: written.append(content) or True)

    result = clipboard.run(
        {"content": "hello", "_headers": {"Origin": "http://127.0.0.1:8767"}},
        {},
    )
    denied = clipboard.run(
        {"content": "nope", "_headers": {"Origin": "https://example.com"}},
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["written"] is True
    assert written == ["hello"]
    assert denied["status"] == "error"
    assert denied["_http_status"] == 403


def test_transport_direct_routes_json_has_interface_registry_parity():
    ecosystem_routes = []
    for routes_path in (DEFAULTSPACK_ROOT / "routes.json", OPERATIONS_PACK_ROOT / "routes.json"):
        ecosystem_routes.extend(json.loads(routes_path.read_text(encoding="utf-8"))["routes"])
    contract_routes = {
        (route["method"], route["path"])
        for route in ecosystem_routes
        if route.get("flow_id") == "transport_direct"
    }
    registry = _collect_defaultspack_routes()
    registered_routes = {(route["method"], route["pattern"]) for route in registry.routes}

    assert contract_routes <= registered_routes


def test_frontend_sidebar_api_routes_match_in_registry_mode():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    registry = _collect_defaultspack_routes()

    class Facade:
        def get_interface(self, key, strategy=None):
            return registry.get_interface(key, strategy=strategy)

    server = DefaultsHttpServer(Facade())
    expected = [
        ("GET", "/api/artifacts"),
        ("POST", "/api/share"),
        ("POST", "/api/tools/browser-computer"),
        ("POST", "/api/research/web-search"),
        ("POST", "/api/research/reddit-search"),
        ("GET", "/api/coding/context"),
        ("GET", "/api/coding/files"),
        ("GET", "/api/coding/git/branch"),
        ("GET", "/api/ai/profiles"),
        ("GET", "/api/agent/schedules"),
        ("GET", "/api/agent/company/status"),
        ("POST", "/api/agent/company/bootstrap"),
        ("GET", "/api/chat/channels"),
        ("GET", "/api/capabilities/local_file"),
    ]

    for method, path in expected:
        handler, _, source, _ = server._match_route(method, path)
        assert handler is not None, (method, path)
        assert source == "registry"


def test_research_providers_use_shared_source_schema():
    from domain.research.providers import ExternalWebProvider, RedditProvider

    html = '<html><title>Example</title><a class="result__a" href="https://example.test">Example</a><div class="result__snippet">Snippet</div></html>'
    web = ExternalWebProvider(fetcher=lambda url, timeout: html)
    web_result = web.search("example", allow_network=True)

    assert web_result.sources[0]["type"] == "external_web"
    assert web_result.sources[0]["provider"] == "external_web"
    assert web.search("example", allow_network=False).network_enabled is False

    reddit_payload = '{"data":{"children":[{"data":{"id":"abc","title":"Hello","permalink":"/r/test/comments/abc/hello","subreddit":"test","score":3,"num_comments":2,"selftext":"Body"}}]}}'
    reddit = RedditProvider(fetcher=lambda url, timeout: reddit_payload)
    reddit_result = reddit.search("hello", subreddit="test")

    assert reddit_result.sources[0]["type"] == "reddit_post"
    assert reddit_result.sources[0]["provider"] == "reddit"
    assert reddit.search("hello", allow_network=False).network_enabled is False


def test_external_web_provider_rejects_private_network_urls():
    from domain.research.providers import ExternalWebProvider

    result = ExternalWebProvider().search("http://127.0.0.1:8766/private", allow_network=True)

    assert result.sources == []
    assert "non-public" in result.summary


def test_browser_computer_controller_gates_desktop_actions():
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController()

    assert controller.run("browser.session")["action"] == "browser.session"
    assert controller.run("browser.session")["capabilities"]["cursor_move"] in {True, False}
    assert controller.run("browser.open_url", {"url": "https://example.test", "dry_run": True})["dry_run"] is True
    assert controller.run("computer.screenshot", {"dry_run": True})["requires_approval"] is False
    assert controller.run("computer.move", {"x": 1, "y": 2, "dry_run": True})["requires_approval"] is False
    approval = controller.run("computer.click", {"x": 1, "y": 2})
    assert approval["requires_approval"] is True
    assert approval["approval_token"]
    assert controller.run("computer.click", {"x": 1, "y": 2, "approved": True})["requires_approval"] is True


def test_browser_computer_screenshot_is_read_only_without_approval(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
    png_body = png_header + b"\x00\x00\x02\x80\x00\x00\x01\x90"

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(png_body)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)
    monkeypatch.setattr(BrowserComputerController, "_model_screenshot_copy", lambda self, path: path)
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: None))

    result = BrowserComputerController(artifact_root=tmp_path).run("computer.screenshot")

    assert result["action"] == "computer.screenshot"
    assert result.get("requires_approval") is not True
    assert result["data_url"].startswith("data:image/png;base64,")
    assert Path(result["path"]).exists()


def test_browser_computer_screenshot_uses_window_id_for_selected_macos_window(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
    png_body = png_header + b"\x00\x00\x02\x80\x00\x00\x01\x90"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "screencapture":
            Path(command[-1]).write_bytes(png_body)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)
    monkeypatch.setattr(BrowserComputerController, "_model_screenshot_copy", lambda self, path: path)
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: None))

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_computer_state(
        {
            "target_window": {
                "app": "Google Chrome",
                "title": "ChatGPT - Google Chrome",
                "x": 50,
                "y": 80,
                "width": 1200,
                "height": 800,
                "window_id": 12345,
            }
        }
    )
    controller._active_window = lambda: None
    controller._chrome_tabs = lambda: []

    result = controller.run("computer.screenshot")

    assert result["action"] == "computer.screenshot"
    assert calls[0][:4] == ["screencapture", "-x", "-l", "12345"]
    assert result["target_window"]["window_id"] == 12345


def test_browser_computer_screenshot_resolves_app_filter_without_prior_select(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
    png_body = png_header + b"\x00\x00\x02\x80\x00\x00\x01\x90"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "screencapture":
            Path(command[-1]).write_bytes(png_body)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)
    monkeypatch.setattr(BrowserComputerController, "_model_screenshot_copy", lambda self, path: path)
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: None))

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._list_windows = lambda: [
        {"app": "Codex", "title": "RumiDP", "x": 0, "y": 0, "width": 1470, "height": 900, "active": True, "window_id": 111},
        {"app": "Google Chrome", "title": "LINE Chat", "x": 40, "y": 70, "width": 1200, "height": 780, "active": False, "window_id": 222},
    ]
    controller._active_window = lambda: {"app": "Codex", "title": "RumiDP", "x": 0, "y": 0, "width": 1470, "height": 900}
    controller._chrome_tabs = lambda: []

    result = controller.run("computer.screenshot", {"app": "Google Chrome", "title": "LINE"}, yolo_mode=True)

    assert result["action"] == "computer.screenshot"
    assert calls[0][:4] == ["screencapture", "-x", "-l", "222"]
    assert result["target_window"]["app"] == "Google Chrome"
    assert result["target_window"]["title"] == "LINE Chat"
    assert controller._computer_state()["target_window"]["window_id"] == 222


def test_browser_computer_screenshot_missing_app_filter_refuses_front_desktop(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._list_windows = lambda: [
        {"app": "Codex", "title": "RumiDP", "x": 0, "y": 0, "width": 1470, "height": 900, "active": True, "window_id": 111},
    ]

    result = controller.run("computer.screenshot", {"app": "Google Chrome", "title": "LINE"}, yolo_mode=True)

    assert result["supported"] is False
    assert "No visible window matched" in result["reason"]
    assert result["target_filter"] == {"app": "Google Chrome", "title": "LINE"}
    assert not [command for command in calls if command and command[0] == "screencapture"]


def test_browser_computer_screenshot_activates_hidden_chrome_tab_when_fallback_allowed(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
    png_body = png_header + b"\x00\x00\x02\x80\x00\x00\x01\x90"
    calls = []
    window_calls = {"count": 0}

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "screencapture":
            Path(command[-1]).write_bytes(png_body)
        return subprocess.CompletedProcess(command, 0)

    def fake_windows():
        window_calls["count"] += 1
        if window_calls["count"] == 1:
            return [{"app": "Codex", "title": "RumiDP", "x": 0, "y": 0, "width": 1470, "height": 900, "active": True}]
        return [
            {"app": "Google Chrome", "title": "LINE Chat", "x": 40, "y": 70, "width": 1200, "height": 780, "active": True, "window_id": 333},
        ]

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)
    monkeypatch.setattr(BrowserComputerController, "_model_screenshot_copy", lambda self, path: path)
    monkeypatch.setattr(BrowserComputerController, "_cursor_position", staticmethod(lambda: None))

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._list_windows = fake_windows
    controller._chrome_tabs = lambda: [
        {"app": "Google Chrome", "window_index": 1, "tab_index": 2, "active": True, "title": "LINE Chat", "url": "https://chat.line.biz/chat"}
    ]
    controller._activate_chrome_target = lambda payload: True
    controller._active_window = lambda: None

    result = controller.run(
        "computer.screenshot",
        {"app": "Google Chrome", "title": "LINE", "allow_foreground_fallback": True},
        yolo_mode=True,
    )

    assert result["action"] == "computer.screenshot"
    assert calls[0][:4] == ["screencapture", "-x", "-l", "333"]
    assert result["target_window"]["title"] == "LINE Chat"


def test_browser_computer_screenshot_hidden_chrome_tab_reports_fallback_needed(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._list_windows = lambda: [
        {"app": "Codex", "title": "RumiDP", "x": 0, "y": 0, "width": 1470, "height": 900, "active": True},
    ]
    controller._chrome_tabs = lambda: [
        {"app": "Google Chrome", "window_index": 1, "tab_index": 2, "active": True, "title": "LINE Chat", "url": "https://chat.line.biz/chat"}
    ]

    result = controller.run("computer.screenshot", {"app": "Google Chrome", "title": "LINE"}, yolo_mode=True)

    assert result["supported"] is False
    assert result["background_target_only"] is True
    assert result["chrome_target"]["tab_index"] == 2
    assert result["recovery"]["kind"] == "foreground_fallback"


def test_browser_use_maps_cursor_move_to_browser_computer_payload():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "browser_use",
        {"action": "move", "x": 120, "y": 240, "dry_run": True},
    )

    assert action == "computer.move"
    assert payload == {"x": 120, "y": 240, "dry_run": True}


def test_computer_use_payload_preserves_window_targeting_fields():
    from domain.tool.executor import _browser_computer_action_payload

    action, payload = _browser_computer_action_payload(
        "computer_use",
        {
            "action": "type",
            "text": "hello\n",
            "app": "Google Chrome",
            "title": "ChatGPT",
            "focus": False,
            "physical": False,
            "background": True,
            "method": "chrome_background",
            "driver": "auto",
            "allow_foreground_fallback": True,
            "allow_user_input_overlap": True,
            "modifier": "meta",
        },
    )

    assert action == "computer.type"
    assert payload == {
        "text": "hello\n",
        "app": "Google Chrome",
        "title": "ChatGPT",
        "focus": False,
        "physical": False,
        "background": True,
        "method": "chrome_background",
        "driver": "auto",
        "allow_foreground_fallback": True,
        "allow_user_input_overlap": True,
        "modifier": "meta",
    }


def test_computer_use_context_defaults_enable_background_then_foreground_fallback():
    from domain.tool.executor import _computer_use_payload_with_context_defaults

    payload = _computer_use_payload_with_context_defaults(
        "computer.type",
        {"text": "hello", "app": "Google Chrome"},
        {
            "computer_use_background_preferred": True,
            "computer_use_allow_foreground_fallback": True,
        },
    )

    assert payload["background"] is True
    assert payload["driver"] == "auto"
    assert payload["allow_foreground_fallback"] is True
    assert payload["allow_user_input_overlap"] is True


def test_computer_use_context_defaults_add_target_and_physical_click():
    from domain.tool.executor import _computer_use_payload_with_context_defaults

    payload = _computer_use_payload_with_context_defaults(
        "computer.click",
        {"x": 20, "y": 30},
        {
            "user_requested_computer_use": True,
            "computer_use_target_app": "Google Chrome",
            "computer_use_target_title": "LINE",
        },
    )

    assert payload["app"] == "Google Chrome"
    assert payload["title"] == "LINE"
    assert payload["physical"] is True


def test_chat_text_sets_computer_use_foreground_fallback_preferences():
    import blocks.chat.send as send

    prefs = send._computer_use_preferences_from_text(
        "バックグラウンドでChrome操作。無理な場合はユーザー入力と被ってもいいのでOK。"
    )

    assert prefs["computer_use_background_preferred"] is True
    assert prefs["computer_use_allow_foreground_fallback"] is True
    assert prefs["computer_use_background_required"] is False


def test_chat_text_sets_computer_use_chrome_line_target_preferences():
    import blocks.chat.send as send

    prefs = send._computer_use_preferences_from_text(
        "google chromeでLINEのチャット画面を開いてるのでメッセージを送って"
    )

    assert prefs["computer_use_target_app"] == "Google Chrome"
    assert prefs["computer_use_target_title"] == "LINE"


def test_user_requested_computer_use_preapproves_interactive_actions(monkeypatch):
    from domain.tool.executor import ToolExecutor
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    captured = {}

    def fake_run(self, action, payload=None, *, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = payload
        captured["yolo_mode"] = yolo_mode
        return {"action": action, "executed": True}

    monkeypatch.setattr(BrowserComputerController, "run", fake_run)

    result = ToolExecutor().execute(
        "browser_computer",
        {"action": "browser.open_url", "payload": {"url": "https://chatgpt.com"}},
        {"user_requested_computer_use": True},
    )

    assert result["is_error"] is False
    assert captured == {
        "action": "browser.open_url",
        "payload": {"url": "https://chatgpt.com", "persistent": False},
        "yolo_mode": True,
    }


def test_browser_computer_executor_propagates_controller_errors(monkeypatch):
    from domain.tool.executor import ToolExecutor
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    def fake_run(self, action, payload=None, *, yolo_mode=False):
        return {
            "action": action,
            "executed": False,
            "is_error": True,
            "reason": "Chrome background text entry failed.",
            "recovery": {"kind": "chrome_setting"},
        }

    monkeypatch.setattr(BrowserComputerController, "run", fake_run)

    result = ToolExecutor().execute(
        "computer_use",
        {"action": "type", "text": "hello", "app": "Google Chrome"},
        {"user_requested_computer_use": True},
    )

    assert result["is_error"] is True
    assert "failed" in result["result"]
    assert result["widget"]["recovery"]["kind"] == "chrome_setting"


def test_browser_open_url_uses_existing_chrome_without_stealing_focus(monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="window_index=2\ttab_index=5\n")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    controller = BrowserComputerController()
    result = controller.run(
        "browser.open_url",
        {"url": "https://chatgpt.com", "persistent": False},
        yolo_mode=True,
    )

    assert result["opened"] is True
    assert result["managed_profile"] is False
    assert result["launch"]["mode"] == "default_browser"
    assert result["chrome_target"]["window_index"] == 2
    assert result["chrome_target"]["tab_index"] == 5
    assert calls[0][0][:2] == ["osascript", "-e"]
    assert "previousFrontApp" in calls[0][0][2]
    assert "Google Chrome" in calls[0][0][2]


def test_computer_type_can_target_background_chrome(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="typed\n")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_sessions({"last_opened_background": True, "last_url": "https://chatgpt.com"})

    result = controller.run("computer.type", {"text": "hello", "background": True}, yolo_mode=True)

    assert result["executed"] is True
    assert result["background"] is True
    assert calls[0][0][:2] == ["osascript", "-e"]
    assert "#prompt-textarea" in calls[0][0][2]
    assert "chatgpt.com" in calls[0][0][2]


def test_computer_type_targets_last_opened_existing_chrome_tab(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="typed\n")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._write_sessions(
        {
            "last_opened_background": True,
            "last_url": "https://chatgpt.com/",
            "chrome_target": {"app": "Google Chrome", "url": "https://chatgpt.com/", "window_index": 2, "tab_index": 5},
        }
    )

    result = controller.run("computer.type", {"text": "hello", "background": True}, yolo_mode=True)

    assert result["executed"] is True
    assert result["chrome_target"]["window_index"] == 2
    assert result["chrome_target"]["tab_index"] == 5
    script = calls[0][0][2]
    assert "set targetWindowIndex to 2" in script
    assert "set targetTabIndex to 5" in script


def test_computer_move_uses_cliclick_on_macos(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.shutil, "which", lambda name: "/opt/homebrew/bin/cliclick" if name == "cliclick" else None)
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)

    controller = BrowserComputerController()
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"

    result = controller.run("computer.move", {"x": 120, "y": 240, "physical": True}, yolo_mode=True)

    assert result["executed"] is True
    assert result["target"] == {"x": 120, "y": 240}
    assert calls[0][0] == ["/opt/homebrew/bin/cliclick", "m:120,240"]


def test_computer_move_defaults_to_virtual_ai_cursor(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
    import ecosystem.rumi_default_tools_pack.domain.tool.browser_computer as browser_computer

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(browser_computer.subprocess, "run", fake_run)
    controller = BrowserComputerController(artifact_root=tmp_path)
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"

    result = controller.run("computer.move", {"x": 120, "y": 240}, yolo_mode=True)

    assert result["executed"] is True
    assert result["virtual_cursor"] is True
    assert result["target"] == {"x": 120, "y": 240}
    assert calls == []


def test_browser_computer_manages_persistent_profiles_and_cookie_jars(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController()
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._approval_path = tmp_path / "shared" / "browser_computer_approvals.json"
    controller._browser_root = tmp_path / "shared" / "browser"
    controller._profile_root = controller._browser_root / "profiles"

    created = controller.run("browser.profile.create", {"profile_id": "Work Login", "label": "Work Login"})
    assert created["profile"]["id"] == "work-login"
    assert created["active_profile_id"] == "work-login"
    assert Path(created["profile"]["profile_dir"]).exists()
    assert Path(created["profile"]["cache_dir"]).exists()

    imported = controller.run(
        "browser.cookies.import",
        {
            "profile_id": "work-login",
            "cookies": [
                {"name": "sid", "value": "secret-token", "domain": "example.test", "path": "/"},
            ],
        },
    )
    assert imported["count"] == 1

    listed = controller.run("browser.cookies.list", {"profile_id": "work-login"})
    assert listed["count"] == 1
    assert listed["cookies"][0]["value"] == "***"
    assert listed["cookies"][0]["value_redacted"] is True

    revealed = controller.run("browser.cookies.list", {"profile_id": "work-login", "include_values": True})
    assert revealed["cookies"][0]["value"] == "secret-token"

    dry_delete = controller.run("browser.cookies.delete", {"profile_id": "work-login", "name": "sid", "dry_run": True})
    assert dry_delete["matches"] == 1
    approval = controller.run("browser.cookies.delete", {"profile_id": "work-login", "name": "sid"})
    assert approval["requires_approval"] is True
    deleted = controller.run(
        "browser.cookies.delete",
        {"profile_id": "work-login", "name": "sid", "approval_token": approval["approval_token"]},
    )
    assert deleted["deleted"] == 1


def test_browser_open_url_uses_managed_profile_launch_plan(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController()
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._approval_path = tmp_path / "shared" / "browser_computer_approvals.json"
    controller._browser_root = tmp_path / "shared" / "browser"
    controller._profile_root = controller._browser_root / "profiles"
    fake_browser = tmp_path / "chrome"
    fake_browser.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_browser.chmod(0o755)
    controller._find_browser_executable = lambda: fake_browser

    result = controller.run(
        "browser.open_url",
        {"url": "https://example.test", "profile_id": "research", "dry_run": True},
    )

    assert result["requires_approval"] is False
    assert result["launch"]["mode"] == "managed_profile"
    assert result["launch"]["command"][0] == str(fake_browser)
    assert "--user-data-dir=" in result["launch"]["command"][1]
    assert "--disk-cache-dir=" in result["launch"]["command"][2]
    assert result["launch"]["command"][-1] == "https://example.test"


def test_browser_profile_cache_and_cookie_clear_are_approval_gated(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController()
    controller._session_path = tmp_path / "shared" / "browser_sessions.json"
    controller._approval_path = tmp_path / "shared" / "browser_computer_approvals.json"
    controller._browser_root = tmp_path / "shared" / "browser"
    controller._profile_root = controller._browser_root / "profiles"
    controller.run("browser.profile.create", {"profile_id": "managed"})
    cache_file = controller._profile_path("managed") / "cache" / "entry.bin"
    cache_file.write_bytes(b"cached")
    cookie_file = controller._profile_path("managed") / "managed_cookies.json"
    cookie_file.write_text('{"version":1,"cookies":[]}', encoding="utf-8")

    dry_cache = controller.run("browser.profile.clear_cache", {"profile_id": "managed", "dry_run": True})
    assert dry_cache["size_bytes"] == 6
    assert cache_file.exists()

    approval = controller.run("browser.profile.clear_cache", {"profile_id": "managed"})
    assert approval["requires_approval"] is True
    cleared = controller.run(
        "browser.profile.clear_cache",
        {"profile_id": "managed", "approval_token": approval["approval_token"]},
    )
    assert cleared["removed"]
    assert not cache_file.exists()

    cookie_approval = controller.run("browser.profile.clear_cookies", {"profile_id": "managed"})
    assert cookie_approval["requires_approval"] is True
    cleared_cookies = controller.run(
        "browser.profile.clear_cookies",
        {
            "profile_id": "managed",
            "include_managed": True,
            "approval_token": cookie_approval["approval_token"],
        },
    )
    assert str(cookie_file) in cleared_cookies["removed"]
    assert not cookie_file.exists()


def test_capability_detail_endpoint_returns_one_manifest_and_404_for_unknown():
    from blocks.capability.manifest import run

    result = run({"capability_id": "local_file"})
    assert result["status"] == "ok"
    assert result["data"]["id"] == "local_file"

    missing = run({"capability_id": "missing-capability"})
    assert missing["status"] == "error"
    assert missing["error"]["code"] == "NOT_FOUND"
    assert missing["_http_status"] == 404


def test_share_store_creates_lists_and_revokes_local_links(tmp_path):
    from domain.share.store import ShareStore

    store = ShareStore(tmp_path)
    record = store.create({"target_type": "conversation", "target_id": "c1", "content": "hello"})

    assert record["share_url"].startswith("/api/share/")
    assert store.get(record["token"])["content"] == "hello"
    assert len(store.list()) == 1
    assert store.revoke(record["token"]) is True
    assert store.get(record["token"]) is None


def test_file_ops_diff_patch_snapshot_restore(tmp_path):
    from domain.coding.file_ops import FileOps

    ops = FileOps(tmp_path)
    ops.create_file("notes/example.txt", "hello world\n")

    diff = ops.diff_text("notes/example.txt", "hello rumi\n")
    assert "hello world" in diff
    assert "hello rumi" in diff

    patch = ops.apply_patch_text("notes/example.txt", "world", "rumi")
    assert patch["patched"] is True
    assert ops.read_file("notes/example.txt") == "hello rumi\n"

    snapshot = ops.snapshot(["notes/example.txt"])
    ops.write_file("notes/example.txt", "changed\n")
    restored = ops.restore_snapshot(snapshot["snapshot_id"], ["notes/example.txt"])
    assert restored["restored"] == ["notes/example.txt"]
    assert ops.read_file("notes/example.txt") == "hello rumi\n"


def test_terminal_exec_requires_approval_for_medium_risk_and_runs_read_only(tmp_path):
    from domain.coding.terminal import Terminal

    terminal = Terminal(tmp_path)

    read_only = terminal.execute("pwd", approved=False)
    assert read_only["exit_code"] == 0
    assert read_only["risk"]["risk_level"] == "low"

    medium = terminal.execute("python3 -c 'print(42)'", approved=False)
    assert medium["approval_required"] is True
    assert medium["exit_code"] is None

    approved = terminal.execute("python3 -c 'print(42)'", approved=True)
    assert approved["exit_code"] == 0
    assert approved["stdout"].strip() == "42"


def test_git_ops_returns_real_status_and_diff(tmp_path):
    from domain.coding.git_ops import GitOps

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    (tmp_path / "file.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "file.txt").write_text("two\n", encoding="utf-8")

    git = GitOps(tmp_path)
    status = git.status()
    diff = git.diff()

    assert status["clean"] is False
    assert "file.txt" in status["modified"]
    assert "-one" in diff["diff"]
    assert "+two" in diff["diff"]


def test_artifact_store_is_local_and_versioned(tmp_path):
    from domain.artifact.store import ArtifactStore

    pack_root = tmp_path / "defaultspack"
    store = ArtifactStore(pack_root)
    artifact = store.create("markdown", "Plan", "# Plan\n", path="plans/plan.md", source_task="test")

    assert artifact["version"] == 1
    assert artifact["content_ref"] == "user_data/artifacts/plans/plan.md"
    assert store.list()[0]["artifact_id"] == artifact["artifact_id"]
    assert store.get(artifact["artifact_id"])["content"] == "# Plan\n"

    try:
        store.create("markdown", "Escape", "nope", path="../escape.md")
    except ValueError as exc:
        assert "escapes artifact root" in str(exc)
    else:
        raise AssertionError("artifact store allowed path traversal")
