from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.agent.engine import AgentEngine  # noqa: E402
from domain.agent_runtime.run_store import AgentRunStore  # noqa: E402
from domain.agent_runtime.transcript import TranscriptStore  # noqa: E402


def _tool(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "test tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_agent_execution_persists_run_and_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_TRANSCRIPT_DIR", str(tmp_path / "transcripts"))
    AgentRunStore._instance = None

    engine = AgentEngine()
    engine._ai_complete = lambda messages, model, context, tools=None: {
        "status": "ok",
        "data": {"content": "durable hello"},
    }

    result = engine.execute("say hi", [], "stub/model", None, {"agent_id": "agent"})

    assert result["status"] == "completed"
    stored = AgentRunStore().get_run(result["execution_id"])
    assert stored["task"] == "say hi"
    assert stored["status"] == "completed"
    transcript_id = stored["current_transcript_id"]
    assert TranscriptStore().read_tail(transcript_id, 10)


def test_agent_approval_can_resume_from_store(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_TRANSCRIPT_DIR", str(tmp_path / "transcripts"))
    AgentRunStore._instance = None

    calls = {"ai": 0}

    def fake_ai(self, messages, model, context, tools=None):
        calls["ai"] += 1
        if calls["ai"] == 1:
            return {
                "status": "ok",
                "data": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "search", "arguments": "{\"q\":\"rumi\"}"},
                        }
                    ]
                },
            }
        return {"status": "ok", "data": {"content": "used durable tool"}}

    def fake_execute_tool(self, tool_name, tool_args, context):
        return {"status": "ok", "data": {"result": "found"}}

    monkeypatch.setattr(AgentEngine, "_ai_complete", fake_ai)
    monkeypatch.setattr(AgentEngine, "_execute_tool", fake_execute_tool)

    engine = AgentEngine()
    started = engine.execute("find docs", [_tool("search")], "stub/model", None, {"agent_id": "agent"})
    assert started["status"] == "waiting_approval"

    import blocks.agent._state as state

    state._engines.clear()
    resumed_engine = state.get_engine(started["execution_id"])
    approved = resumed_engine.approve(started["execution_id"])

    assert approved["status"] == "completed"
    assert approved["result"]["result"] == "used durable tool"
    assert AgentRunStore().get_run(started["execution_id"])["status"] == "completed"
