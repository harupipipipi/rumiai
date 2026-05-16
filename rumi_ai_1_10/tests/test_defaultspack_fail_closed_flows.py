from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
TOOLS_PACK_ROOT = ROOT / "ecosystem" / "rumi_default_tools_pack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))
sys.path.insert(0, str(TOOLS_PACK_ROOT))


class _NoChatContext:
    pass


class _ChatContext:
    def call_handler(self, name, params):
        assert name == "defaults.chat.send"
        return {
            "status": "ok",
            "data": {
                "conversation_id": params["conversation_id"],
                "message": {
                    "role": "assistant",
                    "raw_text": "1. inspect\n2. implement\n3. verify",
                },
            },
        }

    def get_config(self, name):
        return {"agent_id": "agent-1", "planning_model": "openai/test"}.get(name)


def test_legacy_chat_flows_fail_closed_without_chat_send():
    from flows.agent_chat.handler import run as agent_chat_run
    from flows.planning_agent.handler import run as planning_agent_run
    from flows.simple_chat.handler import run as simple_chat_run

    payload = {"message": {"role": "user", "content": "hello"}}

    for handler in (simple_chat_run, agent_chat_run, planning_agent_run):
        result = handler(payload, _NoChatContext())
        assert result["status"] == "error"
        assert result["error"]["code"] == "CHAT_SEND_UNAVAILABLE"


def test_planning_agent_derives_plan_from_chat_send_response():
    from flows.planning_agent.handler import run as planning_agent_run

    result = planning_agent_run(
        {"conversation_id": "conv-1", "message": {"role": "user", "content": "ship it"}},
        _ChatContext(),
    )

    assert result["status"] == "ok"
    assert result["data"]["planning_model"] == "openai/test"
    assert result["data"]["plan"] == ["1. inspect", "2. implement", "3. verify"]


def test_default_tools_file_reader_reads_workspace_file(tmp_path):
    from functions.file_reader.main import run

    (tmp_path / "notes.txt").write_text("real content", encoding="utf-8")

    result = run({}, {"workspace_root": str(tmp_path), "path": "notes.txt"})

    assert result["is_error"] is False
    assert result["result"] == "real content"


def test_default_tools_file_reader_rejects_path_traversal(tmp_path):
    from functions.file_reader.main import run

    result = run({}, {"workspace_root": str(tmp_path), "path": "../outside.txt"})

    assert result["is_error"] is True
    assert "outside workspace root" in result["result"]
