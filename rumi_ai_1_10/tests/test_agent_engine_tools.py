from __future__ import annotations

import sys
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.agent.engine import AgentEngine


def _tool(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "test tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _text_response(content: str = "done") -> dict:
    return {"status": "ok", "data": {"content": content}}


def _tool_call_response(name: str, arguments: str = '{"q": "rumi"}') -> dict:
    return {
        "status": "ok",
        "data": {
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": name, "arguments": arguments},
                }
            ]
        },
    }


def test_agent_execute_passes_tools_to_ai_completion() -> None:
    engine = AgentEngine()
    tools = [_tool("search")]
    seen = {}

    def fake_ai(messages, model, context, tools=None):
        seen["tools"] = tools
        return _text_response()

    engine._ai_complete = fake_ai

    result = engine.execute("find docs", tools, "stub/model", None, {})

    assert result["status"] == "completed"
    assert seen["tools"] == tools


def test_agent_rejects_unconnected_tool_call() -> None:
    engine = AgentEngine()

    def fake_ai(messages, model, context, tools=None):
        return _tool_call_response("not_connected")

    engine._ai_complete = fake_ai

    result = engine.execute("find docs", [_tool("search")], "stub/model", None, {})

    assert result["status"] == "error"
    assert "not connected" in result["result"]["error"]
    assert result["result"]["pending_tool_call"] is None


def test_agent_approve_preserves_tools_for_followup_completion() -> None:
    engine = AgentEngine()
    tools = [_tool("search")]
    seen_followup_tools = []

    def fake_ai(messages, model, context, tools=None):
        seen_followup_tools.append(tools)
        if len(seen_followup_tools) == 1:
            return _tool_call_response("search")
        return _text_response("used tool")

    executed = {}

    def fake_execute_tool(tool_name, tool_args, context):
        executed["tool_name"] = tool_name
        executed["tool_args"] = tool_args
        return {"status": "ok", "data": {"result": "found"}}

    engine._ai_complete = fake_ai
    engine._execute_tool = fake_execute_tool

    started = engine.execute("find docs", tools, "stub/model", None, {"principal": "test"})
    approved = engine.approve(started["execution_id"])

    assert started["status"] == "waiting_approval"
    assert approved["status"] == "completed"
    assert seen_followup_tools == [tools, tools]
    assert executed == {"tool_name": "search", "tool_args": {"q": "rumi"}}


def test_agent_reject_preserves_tools_for_followup_completion() -> None:
    engine = AgentEngine()
    tools = ["search"]
    seen_followup_tools = []

    def fake_ai(messages, model, context, tools=None):
        seen_followup_tools.append(tools)
        if len(seen_followup_tools) == 1:
            return _tool_call_response("search")
        return _text_response("alternate answer")

    engine._ai_complete = fake_ai

    started = engine.execute("find docs", tools, "stub/model", None, {"principal": "test"})
    rejected = engine.reject(started["execution_id"], "not now")

    assert started["status"] == "waiting_approval"
    assert rejected["status"] == "completed"
    assert seen_followup_tools == [tools, tools]
