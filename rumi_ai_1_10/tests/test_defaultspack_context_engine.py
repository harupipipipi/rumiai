from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.context_engine.builder import ContextBuilder  # noqa: E402
from domain.context_engine.compact_packet import build_compact_packet  # noqa: E402
from domain.context_engine.overflow import is_context_overflow_error  # noqa: E402
from domain.context_engine.replacement_history import build_replacement_history  # noqa: E402


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


def test_context_overflow_detection():
    assert is_context_overflow_error("context length exceeded")
    assert not is_context_overflow_error("permission denied")
