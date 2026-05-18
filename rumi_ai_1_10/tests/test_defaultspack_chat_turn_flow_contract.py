from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
FLOW_PATH = DEFAULTSPACK_ROOT / "flows" / "chat_turn.flow.yaml"
STREAM_FLOW_PATH = DEFAULTSPACK_ROOT / "flows" / "chat_stream_turn.flow.yaml"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))
pytestmark = pytest.mark.contract


def _flow():
    return yaml.safe_load(FLOW_PATH.read_text(encoding="utf-8"))


def _stream_flow():
    return yaml.safe_load(STREAM_FLOW_PATH.read_text(encoding="utf-8"))


def test_chat_turn_flow_has_profile_workspace_steps():
    steps = _flow()["steps"]
    ids = [step["id"] for step in steps]
    assert ids[:2] == ["load_active_profile", "load_profile_workspace"]
    functions = {step["id"]: step["function"] for step in steps if step.get("type") == "function"}
    assert functions["load_active_profile"] == "defaults.profile.load_active"
    assert functions["load_profile_workspace"] == "defaults.profile.workspace"


def test_chat_turn_flow_has_permission_filter_before_call_ai():
    ids = [step["id"] for step in _flow()["steps"]]
    assert ids.index("apply_permissions") < ids.index("route_model") < ids.index("call_ai")


def test_chat_turn_flow_has_persist_and_audit_steps():
    ids = [step["id"] for step in _flow()["steps"]]
    assert "persist_turn" in ids
    assert "audit" in ids
    assert "post_turn" in ids
    assert ids.index("persist_turn") < ids.index("audit")
    assert ids.index("audit") < ids.index("post_turn")


def test_chat_turn_flow_is_discoverable_by_flow_engine():
    from ecosystem.defaultspack.domain.flow import FlowEngine

    FlowEngine.reset_instance()
    engine = FlowEngine()
    flow = engine.get_flow("defaultspack.chat_turn")

    assert flow is not None
    assert flow["flow_id"] == "defaultspack.chat_turn"
    assert engine.validate_flow("defaultspack.chat_turn") == []
    discovered = {item["flow_id"]: item for item in engine.list_flows()}
    assert discovered["defaultspack.chat_turn"]["declarative"] is True


def test_chat_stream_turn_flow_is_declared_for_stream_endpoint():
    from ecosystem.defaultspack.domain.flow import FlowEngine

    FlowEngine.reset_instance()
    engine = FlowEngine()
    flow = engine.get_flow("defaultspack.chat_stream_turn")
    route = _stream_flow()["transport"]["http"]["routes"][0]

    assert flow is not None
    assert flow["flow_id"] == "defaultspack.chat_stream_turn"
    assert engine.validate_flow("defaultspack.chat_stream_turn") == []
    assert route["path"] == "/api/chat/conversations/{id}/stream"
    assert route["fallback_block"] == "blocks.chat.stream"
    assert _stream_flow()["steps"][0]["function"] == "defaults.chat.stream"


def test_chat_turn_declarative_runner_executes_function_steps(monkeypatch):
    from ecosystem.defaultspack.domain.flow import FlowEngine

    FlowEngine.reset_instance()
    engine = FlowEngine()
    calls = []

    def fake_invoke(function_name, step_input, flow_context):
        calls.append((function_name, step_input))
        data_by_function = {
            "defaults.profile.load_active": {"profile_id": "profile-1", "policy": {}},
            "defaults.profile.workspace": {"root": "/tmp/work"},
            "defaults.chat.detect_modalities": {"text": True},
            "defaults.prompt.load_effective": "system prompt",
            "defaults.tools.select_relevant": {"tools": ["search"]},
            "defaults.permissions.filter_tools": {"tools": ["search"]},
            "defaults.ai.route_model": {"bridge_required": False, "bridge_plan": {}},
            "defaults.prompt.compact_prompt": {"prompt": "compact prompt"},
            "defaults.ai.build_request": {"messages": []},
            "defaults.ai.complete": {"id": "assistant-1"},
            "defaults.chat.persist_turn": {
                "id": "turn-1",
                "assistant_message": {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                },
            },
            "defaults.audit.record_event": {"id": "audit-1"},
        }
        return {"status": "ok", "data": data_by_function[function_name]}

    monkeypatch.setattr(engine, "_invoke_function_step", fake_invoke)

    result = engine.execute(
        "defaultspack.chat_turn",
        {
            "conversation_id": "conversation-1",
            "profile_id": "profile-1",
            "message": {"content": "hi"},
        },
    )

    assert result.is_success()
    assert result.metadata["runner"] == "declarative_flow_engine"
    assert calls[0] == (
        "defaults.profile.load_active",
        {"profile_id": "profile-1"},
    )
    assert "defaults.vision.describe_images" not in [call[0] for call in calls]
    outputs = result.metadata["outputs"]
    assert outputs["ai_response"] == {"id": "assistant-1"}
    assert outputs["audit_event"] == {"id": "audit-1"}
    assert outputs["selected_tools"] == ["search"]
    assert result.output["data"]["role"] == "assistant"


def test_chat_turn_runs_optional_post_turn_subflow(monkeypatch):
    from ecosystem.defaultspack.domain.flow import FlowEngine

    FlowEngine.reset_instance()
    engine = FlowEngine()
    engine._flows["test.post_turn"] = {
        "flow_id": "test.post_turn",
        "_declarative": True,
        "inputs": {"conversation_id": "string"},
        "outputs": {"forwarded": "object"},
        "steps": [
            {
                "id": "forward",
                "type": "function",
                "function": "test.webhook.forward",
                "input": {
                    "conversation_id": "{{input.conversation_id}}",
                    "assistant": "{{input.persisted_turn.assistant_message}}",
                },
                "output": "forwarded",
            }
        ],
    }
    calls = []

    def fake_invoke(function_name, step_input, flow_context):
        calls.append((function_name, step_input))
        if function_name == "test.webhook.forward":
            return {"status": "ok", "data": {"sent": True, "to": "line"}}
        data_by_function = {
            "defaults.profile.load_active": {"profile_id": "profile-1", "policy": {}},
            "defaults.profile.workspace": {"root": "/tmp/work"},
            "defaults.chat.detect_modalities": {"text": True},
            "defaults.prompt.load_effective": "system prompt",
            "defaults.tools.select_relevant": {"tools": []},
            "defaults.permissions.filter_tools": {"tools": []},
            "defaults.ai.route_model": {"bridge_required": False, "bridge_plan": {}},
            "defaults.prompt.compact_prompt": {"prompt": "system prompt"},
            "defaults.ai.build_request": {"messages": []},
            "defaults.ai.complete": {"content": [{"type": "text", "text": "hello"}]},
            "defaults.chat.persist_turn": {
                "assistant_message": {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                }
            },
            "defaults.audit.record_event": {"id": "audit-1"},
        }
        return {"status": "ok", "data": data_by_function[function_name]}

    monkeypatch.setattr(engine, "_invoke_function_step", fake_invoke)

    result = engine.execute(
        "defaultspack.chat_turn",
        {
            "conversation_id": "conversation-1",
            "profile_id": "profile-1",
            "message": {"content": "hi"},
            "post_turn_flow": "test.post_turn",
        },
    )

    assert result.is_success()
    assert calls[-1][0] == "test.webhook.forward"
    assert calls[-1][1]["assistant"]["id"] == "assistant-1"
    assert result.metadata["step_outputs"]["post_turn"]["forwarded"] == {"sent": True, "to": "line"}


def test_declarative_flow_rejects_legacy_persist_step_type():
    from ecosystem.defaultspack.domain.flow import FlowEngine

    FlowEngine.reset_instance()
    engine = FlowEngine()
    engine._flows["test.bad_persist"] = {
        "flow_id": "test.bad_persist",
        "_declarative": True,
        "steps": [{"id": "persist", "type": "persist"}],
    }

    errors = engine.validate_flow("test.bad_persist")

    assert any("unsupported type 'persist'" in item for item in errors)


def test_declarative_flow_executes_branch_and_parallel_steps(monkeypatch):
    from ecosystem.defaultspack.domain.flow import FlowEngine

    FlowEngine.reset_instance()
    engine = FlowEngine()
    engine._flows["test.branch_parallel"] = {
        "flow_id": "test.branch_parallel",
        "_declarative": True,
        "steps": [
            {
                "id": "choose",
                "type": "branch",
                "branches": [
                    {
                        "when": "{{input.enabled}}",
                        "steps": [
                            {
                                "id": "branch_fn",
                                "type": "function",
                                "function": "test.branch",
                                "input": {"value": "{{input.value}}"},
                                "output": "branch_value",
                            }
                        ],
                    }
                ],
                "output": "branch_result",
            },
            {
                "id": "fanout",
                "type": "parallel",
                "steps": [
                    {
                        "id": "left",
                        "type": "function",
                        "function": "test.left",
                        "input": {"value": "{{input.value}}"},
                        "output": "left_value",
                    },
                    {
                        "id": "right",
                        "type": "function",
                        "function": "test.right",
                        "input": {"value": "{{input.value}}"},
                        "output": "right_value",
                    },
                ],
                "output": "parallel_result",
            },
        ],
    }

    def fake_invoke(function_name, step_input, flow_context):
        return {"status": "ok", "data": {"function": function_name, "input": step_input}}

    monkeypatch.setattr(engine, "_invoke_function_step", fake_invoke)

    assert engine.validate_flow("test.branch_parallel") == []
    result = engine.execute(
        "test.branch_parallel",
        {"enabled": True, "value": "ok"},
    )

    assert result.is_success()
    outputs = result.output["data"]["outputs"]
    assert outputs["branch_result"]["outputs"]["branch_value"]["function"] == "test.branch"
    assert outputs["parallel_result"]["left"]["left_value"]["function"] == "test.left"
    assert outputs["parallel_result"]["right"]["right_value"]["function"] == "test.right"


def test_persist_turn_writes_canonical_chat_store_messages(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_CHAT_STORE_PATH",
        str(tmp_path / "chat" / "conversations.json"),
    )
    from ecosystem.defaultspack.blocks.chat.persist_turn import run
    from domain.chat.store import ChatStore

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello"},
            "ai_response": {
                "content": [{"type": "text", "text": "hi back"}],
                "finish_reason": "stop",
                "usage": {"total_tokens": 3},
            },
            "route_model": {"selected_model": "stub/default"},
            "workspace": {"user_data_dir": str(tmp_path / "audit")},
        },
        {},
    )

    assert result["status"] == "ok"
    persisted = result["data"]
    assert persisted["user_message"]["role"] == "user"
    assert persisted["assistant_message"]["role"] == "assistant"
    assert persisted["assistant_message"]["raw_text"] == "hi back"
    stored = ChatStore().get_conversation(conversation["id"])
    assert [message["role"] for message in stored["messages"]] == ["user", "assistant"]
    assert (tmp_path / "audit" / "chat_turns.jsonl").is_file()
