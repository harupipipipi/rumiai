from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_canonical_signature_masks_volatile_ids_and_timestamps():
    from domain.chat.loop_guard import tool_action_signature

    first = tool_action_signature(
        "web_search",
        {
            "query": "loop guard design",
            "request_id": "req_a",
            "tool_call_id": "call_a",
            "timestamp": "2026-06-21T12:00:00Z",
            "api_key": "sk-test-secret-value-1234567890",
        },
    )
    second = tool_action_signature(
        "web_search",
        {
            "query": "loop guard design",
            "request_id": "req_b",
            "tool_call_id": "call_b",
            "timestamp": "2026-06-21T12:00:10Z",
            "api_key": "sk-test-secret-value-1234567890",
        },
    )

    assert first == second


def test_pagination_cursor_is_meaningful():
    from domain.chat.loop_guard import tool_action_signature

    first = tool_action_signature("web_search", {"query": "rumi", "cursor": "page-1"})
    second = tool_action_signature("web_search", {"query": "rumi", "cursor": "page-2"})

    assert first != second


def test_exact_no_progress_loop_recovers_once_then_pauses():
    from domain.chat.loop_guard import LoopGuard, build_loop_observation

    guard = LoopGuard(run_id="run_1", conversation_id="chat_1")
    observation = build_loop_observation(
        tool_uses=[{"name": "coding_file_read", "input": {"path": "src/app.ts"}}],
        tool_logs=[{"tool_name": "coding_file_read", "result": {"status": "ok", "data": "same"}}],
    )

    decisions = [guard.observe_cycle(observation) for _ in range(4)]
    assert decisions[-1].kind == "recover"

    decisions = [guard.observe_cycle(observation) for _ in range(4)]
    assert decisions[-1].kind == "pause"
    assert decisions[-1].recovery_cluster_id


def test_meaningful_progress_prevents_loop_detection():
    from domain.chat.loop_guard import LoopGuard, build_loop_observation

    guard = LoopGuard(run_id="run_1", conversation_id="chat_1")
    observation = build_loop_observation(
        tool_uses=[{"name": "coding_file_write", "input": {"path": "src/app.ts", "content": "x"}}],
        tool_logs=[
            {
                "tool_name": "coding_file_write",
                "result": {"status": "ok", "changed_files": ["src/app.ts"], "diff": "+x"},
            }
        ],
    )

    decisions = [guard.observe_cycle(observation) for _ in range(6)]
    assert all(decision.kind == "continue" for decision in decisions)


def test_period_two_loop_is_detected():
    from domain.chat.loop_guard import LoopGuard, build_loop_observation

    guard = LoopGuard(run_id="run_1", conversation_id="chat_1")
    read_a = build_loop_observation(
        tool_uses=[{"name": "coding_file_read", "input": {"path": "a.ts"}}],
        tool_logs=[{"tool_name": "coding_file_read", "result": {"status": "ok", "data": "a"}}],
    )
    read_b = build_loop_observation(
        tool_uses=[{"name": "coding_file_read", "input": {"path": "b.ts"}}],
        tool_logs=[{"tool_name": "coding_file_read", "result": {"status": "ok", "data": "b"}}],
    )

    decisions = [guard.observe_cycle(item) for item in [read_a, read_b, read_a, read_b, read_a, read_b]]
    assert decisions[-1].kind == "recover"
    assert decisions[-1].motif_period == 2


def test_waiting_approval_is_not_counted_as_loop():
    from domain.chat.loop_guard import LoopGuard, build_loop_observation

    guard = LoopGuard(run_id="run_1", conversation_id="chat_1")
    observation = build_loop_observation(
        tool_uses=[{"name": "computer_use", "input": {"action": "click", "x": 1, "y": 1}}],
        tool_logs=[{"tool_name": "computer_use", "result": {"status": "ok", "data": {"requires_approval": True}}}],
    )

    decisions = [guard.observe_cycle(observation) for _ in range(6)]
    assert all(decision.kind == "continue" for decision in decisions)


def test_explicit_param_max_tool_calls_is_opt_in():
    from domain.chat.loop_guard import explicit_param_max_tool_calls

    assert explicit_param_max_tool_calls({}) is None
    assert explicit_param_max_tool_calls({"max_tool_calls": None}) is None
    assert explicit_param_max_tool_calls({"max_tool_calls": 3}) == 3
