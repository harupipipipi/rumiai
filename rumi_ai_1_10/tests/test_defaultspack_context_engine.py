from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.context_engine.builder import ContextBuilder  # noqa: E402
from domain.context_engine.compact_packet import build_compact_packet  # noqa: E402
from domain.context_engine.compressor import ContextCompressor  # noqa: E402
from domain.context_engine.overflow import is_context_overflow_error  # noqa: E402
from domain.context_engine.pruning import prune_to_budget  # noqa: E402
from domain.context_engine.replacement_history import build_replacement_history, repair_tool_pairs  # noqa: E402
from domain.context_engine.validation import validate_compact_packet  # noqa: E402
from blocks.context.restore import run as restore_compact_context  # noqa: E402


def test_context_builder_separates_stable_and_ephemeral_layers():
    result = ContextBuilder().build(
        {
            "task": "hello",
            "runtime_profile_json": {"policy": {"max_tool_calls": 1}},
            "execution_json": {"messages": [{"role": "user", "content": "hello"}]},
        },
        {"memory_snapshot": "remember this", "ephemeral_context": ["now"]},
    )

    assert result.messages[0]["role"] == "system"
    assert "memory_snapshot" in result.messages[0]["content"]
    assert result.token_estimate > 0
    assert result.ephemeral_context == ["now"]


def test_compact_packet_has_handoff_fields():
    packet = build_compact_packet(
        run_id="run_1",
        goal="finish",
        summary="done: a",
        changed_files=["app.py"],
        next_steps=["test"],
    )

    assert packet["run_id"] == "run_1"
    assert packet["progress"]["done"] == []
    assert packet["changed_files"] == ["app.py"]
    assert packet["next_steps"] == ["test"]
    assert packet["critical_context"] == []


def test_context_compact_can_include_owned_agent_run_snapshot(tmp_path, monkeypatch):
    from blocks.context.compact import run as compact_context
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    AgentRunStore._instance = None
    store = AgentRunStore()
    store.upsert_run(
        AgentRun(
            run_id="run_compact",
            session_key="agent:test:main",
            conversation_id="conv_owner",
            task="ship fix",
            status="completed",
            execution_json={"files_modified": ["fix.py"]},
            result_json={"next_steps": ["open review"]},
        )
    )

    result = compact_context(
        {
            "run_id": "run_compact",
            "summary": "handoff",
            "include_run_snapshot": True,
        },
        {"session_key": "agent:test:main"},
    )

    assert result["status"] == "ok"
    packet = result["data"]
    assert packet["progress"]["done"] == ["ship fix"]
    assert packet["changed_files"] == ["fix.py"]
    assert packet["next_steps"] == ["open review"]
    assert "run_id: run_compact" in packet["critical_context"]
    assert packet["validation"]["valid"] is True


def test_context_compact_rejects_unowned_agent_run_snapshot(tmp_path, monkeypatch):
    from blocks.context.compact import run as compact_context
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    AgentRunStore._instance = None
    store = AgentRunStore()
    store.upsert_run(
        AgentRun(
            run_id="run_private",
            session_key="agent:owner:main",
            conversation_id="conv_owner",
            task="private task",
            status="completed",
            execution_json={"files_modified": ["private.py"]},
            result_json={"next_steps": ["private next"]},
        )
    )

    for context in ({}, {"session_key": "agent:other:main", "conversation_id": "conv_other"}):
        result = compact_context(
            {
                "run_id": "run_private",
                "conversation_id": "conv_other",
                "summary": "handoff",
                "include_run_snapshot": True,
            },
            context,
        )

        assert result["status"] == "ok"
        packet = result["data"]
        assert packet["progress"] == {"done": [], "in_progress": [], "blocked": []}
        assert packet["changed_files"] == []
        assert packet["next_steps"] == []
        assert packet["critical_context"] == []
        assert "private task" not in str(packet)
        assert "private.py" not in str(packet)
        assert "private next" not in str(packet)


def test_context_compact_can_include_exact_active_run_snapshot(tmp_path, monkeypatch):
    from blocks.context.compact import run as compact_context
    from domain.agent_runtime.models import AgentRun
    from domain.agent_runtime.run_store import AgentRunStore

    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    AgentRunStore._instance = None
    store = AgentRunStore()
    store.upsert_run(
        AgentRun(
            run_id="run_active",
            session_key="agent:owner:main",
            conversation_id="conv_owner",
            task="active task",
            status="completed",
            execution_json={"files_modified": ["active.py"]},
            result_json={"next_steps": ["active next"]},
        )
    )

    result = compact_context(
        {
            "run_id": "run_active",
            "summary": "handoff",
            "include_run_snapshot": True,
        },
        {"active_run_id": "run_active", "session_key": "agent:other:main"},
    )

    assert result["status"] == "ok"
    packet = result["data"]
    assert packet["progress"]["done"] == ["active task"]
    assert packet["changed_files"] == ["active.py"]
    assert packet["next_steps"] == ["active next"]
    assert "run_id: run_active" in packet["critical_context"]


def test_context_compact_rejects_invalid_packet_sections():
    from blocks.context.compact import run as compact_context

    result = compact_context({"summary": "bad", "decisions": "not-a-list"}, {})

    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_CONTEXT_PACKET"


def test_compact_packet_validation_reports_section_budgets():
    packet = build_compact_packet(summary="ok", changed_files=[f"file_{index}.py" for index in range(205)])

    validation = validate_compact_packet(packet)

    assert validation.valid is True
    assert validation.sections["changed_files"]["items"] == 205
    assert any("changed_files" in warning for warning in validation.warnings)


def test_context_compressor_preserves_handoff_metadata():
    result = ContextCompressor().compact(
        [{"role": "user", "content": "hello"}],
        {
            "run_id": "run_1",
            "progress": {"done": ["a"], "in_progress": ["b"], "blocked": []},
            "constraints": ["stay offline"],
            "user_preferences": ["concise"],
            "changed_files": ["app.py"],
            "tool_results": [{"tool": "search", "status": "ok"}],
            "terminal_results": [{"command": "pytest", "exit_code": 0}],
            "pinned_context": ["keep"],
            "dropped_context": ["old log"],
            "memory_flush_refs": ["memory://a"],
            "next_steps": ["ship"],
            "critical_context": ["do not lose"],
        },
    )

    packet = result["packet"]
    assert packet["progress"]["done"] == ["a"]
    assert packet["constraints"] == ["stay offline"]
    assert packet["user_preferences"] == ["concise"]
    assert packet["changed_files"] == ["app.py"]
    assert packet["tool_results"][0]["tool"] == "search"
    assert packet["terminal_results"][0]["command"] == "pytest"
    assert packet["pinned_context"] == ["keep"]
    assert packet["dropped_context_log"] == ["old log"]
    assert packet["memory_flush_refs"] == ["memory://a"]
    assert packet["next_steps"] == ["ship"]
    assert packet["critical_context"] == ["do not lose"]


def test_replacement_history_preserves_tool_call_result_pair():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1"}]},
        {"role": "tool", "content": "result"},
        {"role": "assistant", "content": "new"},
    ]
    replacement = build_replacement_history(messages, {"compact_id": "compact_1"}, keep_recent_tokens=1000)

    roles = [message["role"] for message in replacement]
    assert roles == ["system", "user", "user", "assistant", "tool", "assistant"]


def test_replacement_history_preserves_content_block_tool_pair_under_tight_budget():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "old context"},
        {
            "role": "assistant",
            "content": [{"type": "tool_call", "id": "call_1", "name": "lookup"}],
        },
        {
            "role": "tool",
            "content": [{"type": "tool_result", "tool_call_id": "call_1", "content": "ok"}],
        },
    ]

    replacement = build_replacement_history(messages, {"compact_id": "compact_1"}, keep_recent_tokens=1)

    assert replacement[-2]["content"][0]["type"] == "tool_call"
    assert replacement[-1]["content"][0]["type"] == "tool_result"


def test_repair_tool_pairs_fills_missing_result_with_call_id():
    repaired = repair_tool_pairs(
        [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1"}]},
            {"role": "assistant", "content": "next"},
        ]
    )

    assert repaired[1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "[tool result omitted during compaction]",
    }
    assert repaired[2]["content"] == "next"


def test_prune_to_budget_keeps_content_block_tool_pair_together():
    messages = [
        {"role": "user", "content": "old context"},
        {
            "role": "assistant",
            "content": [{"type": "tool_call", "id": "call_1", "name": "lookup"}],
        },
        {
            "role": "tool",
            "content": [{"type": "tool_result", "tool_call_id": "call_1", "content": "ok"}],
        },
    ]

    pruned = prune_to_budget(messages, 1)

    assert [message["role"] for message in pruned] == ["assistant", "tool"]


def test_context_overflow_detection():
    assert is_context_overflow_error("context length exceeded")
    assert not is_context_overflow_error("permission denied")


def test_context_restore_rejects_path_traversal_compact_id():
    result = restore_compact_context({"compact_id": "../secret"}, {})

    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_INPUT"
