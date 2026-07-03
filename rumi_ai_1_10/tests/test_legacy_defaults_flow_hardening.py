from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LEGACY_DEFAULTS_ROOT = ROOT / "ecosystem" / "defaults"


class _NoChatContext:
    pass


class _RaisingChatContext:
    def call_handler(self, name, params):
        raise RuntimeError("chat backend down")


class _UnavailableStubContext:
    def call_handler(self, name, params):
        assert name == "defaults.chat.send"
        return {"status": "ok", "data": None, "_stub": True}


class _StubProviderChatContext:
    def call_handler(self, name, params):
        assert name == "defaults.chat.send"
        return {
            "status": "ok",
            "data": {
                "conversation_id": params["conversation_id"],
                "message": {
                    "role": "assistant",
                    "content": "1. inspect legacy flow\n2. ship the fix",
                },
            },
            "_stub": True,
        }

    def get_config(self, name):
        return {"agent_id": "agent-1", "planning_model": "stub/default"}.get(name)


def _load_legacy_handler(flow_name):
    original_sys_path = list(sys.path)
    for module_name in list(sys.modules):
        if module_name == "blocks" or module_name.startswith("blocks."):
            sys.modules.pop(module_name)
    try:
        sys.path.insert(0, str(LEGACY_DEFAULTS_ROOT))
        path = LEGACY_DEFAULTS_ROOT / "flows" / flow_name / "handler.py"
        spec = importlib.util.spec_from_file_location(
            f"_legacy_defaults_{flow_name}_handler",
            path,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original_sys_path
        for module_name in list(sys.modules):
            if module_name == "blocks" or module_name.startswith("blocks."):
                sys.modules.pop(module_name)


def test_agent_chat_fails_closed_without_chat_send():
    handler = _load_legacy_handler("agent_chat")

    result = handler.run(
        {"conversation_id": "conv-1", "message": {"role": "user", "content": "hello"}},
        _NoChatContext(),
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "CHAT_SEND_UNAVAILABLE"


def test_agent_chat_fails_closed_when_chat_send_raises():
    handler = _load_legacy_handler("agent_chat")

    result = handler.run(
        {"conversation_id": "conv-1", "message": {"role": "user", "content": "hello"}},
        _RaisingChatContext(),
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "CHAT_SEND_FAILED"
    assert "chat backend down" in result["error"]["message"]


def test_legacy_flows_treat_empty_stub_response_as_unavailable():
    payload = {
        "conversation_id": "conv-1",
        "message": {"role": "user", "content": "hello"},
    }

    for flow_name in ("agent_chat", "planning_agent"):
        handler = _load_legacy_handler(flow_name)
        result = handler.run(payload, _UnavailableStubContext())

        assert result["status"] == "error"
        assert result["error"]["code"] == "CHAT_SEND_UNAVAILABLE"


def test_agent_chat_preserves_actual_stub_provider_response():
    handler = _load_legacy_handler("agent_chat")

    result = handler.run(
        {"conversation_id": "conv-1", "message": {"role": "user", "content": "hello"}},
        _StubProviderChatContext(),
    )

    assert result["status"] == "ok"
    assert result["data"]["result"]["_stub"] is True
    assert result["data"]["result"]["data"]["message"]["content"] == (
        "1. inspect legacy flow\n2. ship the fix"
    )


def test_planning_agent_derives_plan_from_chat_send_response():
    handler = _load_legacy_handler("planning_agent")

    result = handler.run(
        {
            "conversation_id": "conv-1",
            "message": {"role": "user", "content": "make a plan"},
        },
        _StubProviderChatContext(),
    )

    assert result["status"] == "ok"
    assert result["data"]["planning_model"] == "stub/default"
    assert result["data"]["plan"] == ["1. inspect legacy flow", "2. ship the fix"]
    assert not any(step.startswith("Step 1: Analyze") for step in result["data"]["plan"])


def test_planning_agent_fails_closed_without_chat_send():
    handler = _load_legacy_handler("planning_agent")

    result = handler.run(
        {"conversation_id": "conv-1", "message": {"role": "user", "content": "hello"}},
        _NoChatContext(),
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "CHAT_SEND_UNAVAILABLE"
