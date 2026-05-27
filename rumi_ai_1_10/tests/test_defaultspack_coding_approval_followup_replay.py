"""Regression tests for the coding approval-followup deterministic replay.

When the UI delivers an ``approval_followup`` whose token + tool_name +
request_id resolve to an approved pending tool, the chat engine must replay
that exact pending tool **once** with the stored approved arguments before the
model speaks. This removes the previous reliance on the model deciding to
re-issue the tool call from natural-language hints, which produced the
``executed_tools=[]`` hallucinated commit-success bug where the model
described a successful git commit while the underlying ``git log -1`` still
pointed at the previous commit.

These tests pin the deterministic-replay contract:

* The ``approval_required`` helper must store the original arguments inside
  the approval request so the followup path can replay them later.
* When the engine receives a valid approval-followup it must call the tool
  once with the stored arguments and the approved token, persist the synthetic
  assistant tool_use + tool_result on the active draft, strip provider tools
  for the remainder of the turn, and surface the executed tool name in the
  finalised assistant ``metadata.executed_tools``.
* When the followup is missing/expired/tampered the engine falls through to
  the existing model-driven path so non-followup turns never regress.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _NoToolFakeClient:
    """Fake AI client that returns a text-only response without calling tools."""

    def __init__(self, recorded):
        self._recorded = recorded

    def complete(self, model, messages, tools=None, params=None):
        self._recorded.setdefault("complete_calls", []).append(
            {
                "model": model,
                "tools": list(tools or []),
                "messages": list(messages or []),
            }
        )
        return {
            "content": [{"type": "text", "text": "Commit summary: hash=abc1234."}],
            "finish_reason": "stop",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    def supports_stream(self, model):
        return False

    def stream(self, model, messages, tools=None, params=None):  # pragma: no cover - unused
        if False:
            yield {}


def _coding_git_commit_tool_def():
    return {
        "tool_id": "coding_git_commit",
        "name": "coding_git_commit",
        "risk": "high",
        "requires_approval": True,
        "capability_grants": ["git.write"],
        "execution": {
            "type": "rumi_function",
            "qualified_name": "defaultspack:coding_git_commit",
        },
    }


def test_approval_required_embeds_args_in_details_for_replay():
    """``approval_required`` must persist the original arguments under
    ``details["arguments"]`` so the followup path can recover them later."""
    from blocks.coding._approval import approval_required
    from domain.safety import approval

    approval.reset_approval_state_for_tests()
    args = {"message": "fix typo", "paths": ["a.txt", "b.txt"]}
    payload = approval_required(
        "git.commit",
        "high",
        args=args,
        message=args["message"],
        tool_name="coding_git_commit",
    )
    request = approval.get_approval_request(payload["approval_request_id"])
    assert request is not None
    assert request["details"]["arguments"] == args
    # The args_hash must reflect the stored arguments so replay verification works.
    assert request["args_hash"] == approval.hash_arguments(args)


def test_approval_required_strips_token_and_transport_keys_from_stored_args():
    """``approval_token`` and transport-only keys must not contaminate the
    stored args, otherwise the args_hash baked into the token would never
    match a deterministic replay."""
    from blocks.coding._approval import approval_required
    from domain.safety import approval

    approval.reset_approval_state_for_tests()
    args = {
        "message": "fix typo",
        "approval_token": "tok_should_be_stripped",
        "_headers": {"X-Rumi-Approval": "stale"},
    }
    payload = approval_required("git.commit", "high", args=args, message="fix typo")
    request = approval.get_approval_request(payload["approval_request_id"])
    assert request["details"]["arguments"] == {"message": "fix typo"}


def _make_conversation_with_followup(tmp_path, monkeypatch, *, args, token, request_id, tool_name):
    """Build a chat conversation whose latest user message carries a valid
    approval-followup metadata block targeting ``tool_name``."""
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    return store, conversation


def _approve_pending(args, *, tool_name, operation):
    """Drive ``approval_required`` + ``approve`` to obtain a real signed token
    that targets ``operation`` for ``args``."""
    from blocks.coding._approval import approval_required
    from domain.safety import approval

    payload = approval_required(
        operation,
        "high",
        args=args,
        message=str(args.get("message") or ""),
        tool_name=tool_name,
    )
    request_id = payload["approval_request_id"]
    decision = approval.approve(request_id)
    assert decision["approved"] is True, decision
    return decision["token"], request_id


def test_approval_followup_deterministically_replays_tool_once(tmp_path, monkeypatch):
    """End-to-end: approval-followup must execute the pending tool exactly once
    with the stored args + token, surface ``executed_tools`` on the assistant
    message, strip provider tools so the model only summarises, and keep the
    one-shot token replay-safe afterwards."""
    from blocks.chat.stream import run as stream_run
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    args = {"message": "fix typo", "paths": ["a.txt"]}
    token, request_id = _approve_pending(
        args, tool_name="coding_git_commit", operation="tool.coding_git_commit",
    )
    # Sanity check: the approval request must be visible from the same module
    # instance that the stream engine will import as ``domain.safety.approval``.
    assert approval.get_approval_request(request_id) is not None
    store, conversation = _make_conversation_with_followup(
        tmp_path, monkeypatch,
        args=args, token=token, request_id=request_id, tool_name="coding_git_commit",
    )

    recorded = {}
    import blocks.chat.stream as stream_module
    monkeypatch.setattr(engine_module, "AIClient", lambda: _NoToolFakeClient(recorded))
    monkeypatch.setattr(stream_module, "AIClient", lambda: _NoToolFakeClient(recorded))

    # Make the post-replay summary turn deterministic and provider-independent:
    # patch ``_complete_turn`` so it does not depend on which AI provider /
    # gateway path the engine happens to take after replay. Whatever the model
    # routing resolves to, the summary will always be the same fixed text and
    # the recorded ``tools`` list still surfaces whether provider tools were
    # stripped.
    from domain.chat.stream_engine import ChatRunEngine

    def _fake_complete_turn(self, prepared, messages):
        recorded.setdefault("complete_calls", []).append(
            {
                "model": prepared.model,
                "tools": list(prepared.provider_tools or []),
                "messages": list(messages or []),
            }
        )
        return {
            "content": [{"type": "text", "text": "Commit summary: hash=abc1234."}],
            "finish_reason": "stop",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(ChatRunEngine, "_complete_turn", _fake_complete_turn)

    invoked = []

    def _fake_execute(self, tool_name, arguments, context):
        invoked.append({"tool_name": tool_name, "arguments": dict(arguments)})
        # Mimic the real ``coding_git_commit`` tool: consuming the approval
        # token so the one-shot replay contract (token is single-use) is
        # exercised end-to-end without depending on the real tool body.
        token = str((arguments or {}).get("approval_token") or "").strip()
        if token:
            try:
                from domain.safety import approval as _approval_mod
                replay_args = {k: v for k, v in arguments.items() if k != "approval_token"}
                _approval_mod.verify_execution_token(
                    token,
                    "tool.coding_git_commit",
                    _approval_mod.hash_arguments(replay_args),
                    consume=True,
                )
            except Exception:
                pass
        return {
            "result": "Commit created",
            "is_error": False,
            "widget": None,
            "data": {"commit_hash": "abc1234"},
        }

    with patch.object(ToolExecutor, "execute", _fake_execute):
        result = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": {
                    "role": "user",
                    "content": "ユーザーが許可しました。承認済みの操作を続行してください。",
                    "metadata": {
                        "approval_followup": {
                            "approval_token": token,
                            "operation": "tool.coding_git_commit",
                            "request_id": request_id,
                            "tool_name": "coding_git_commit",
                            "action": "git.commit",
                        },
                    },
                },
                "tools": [],
            },
            {},
        )
        # Drain the SSE generator while the executor patch is active so the
        # replay-stage tool invocation is captured by ``invoked``.
        events = list(result["events"])

    assert result.get("_sse") is True, result
    # Tool must have been replayed exactly once with the stored args + token.
    assert len(invoked) == 1, invoked
    assert invoked[0]["tool_name"] == "coding_git_commit"
    assert invoked[0]["arguments"]["message"] == args["message"]
    assert invoked[0]["arguments"]["paths"] == args["paths"]
    assert invoked[0]["arguments"]["approval_token"] == token

    started = [event for event in events if event.get("type") == "tool_call_started"]
    completed = [event for event in events if event.get("type") == "tool_call_completed"]
    assert len(started) == 1
    assert started[0].get("approval_replay") is True
    assert started[0].get("tool_name") == "coding_git_commit"
    assert len(completed) == 1
    assert completed[0].get("approval_replay") is True

    # The model turn must have run with provider_tools stripped, otherwise
    # the model could re-call the pending tool from the same followup turn.
    assert recorded.get("complete_calls"), "model was never invoked for the summary"
    assert recorded["complete_calls"][0]["tools"] == []

    # The finalised assistant message must surface the deterministically
    # executed tool, which is the user-visible signal that ``executed_tools=[]``
    # hallucination is fixed.
    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events, events
    final_message = done_events[-1]["message"]
    assert final_message["metadata"]["executed_tools"] == ["coding_git_commit"]
    assert final_message["raw_text"] == "Commit summary: hash=abc1234."

    # Token is now consumed; replaying the same followup must not run the tool
    # a second time.
    args_hash = approval.hash_arguments(args)
    verification = approval.verify_execution_token(
        token, "tool.coding_git_commit", args_hash, consume=False,
    )
    assert verification.valid is False
    ChatStore._instance = None


def test_approval_followup_without_token_falls_through_to_model(tmp_path, monkeypatch):
    """Without an ``approval_followup`` block the engine must keep the existing
    model-driven path: no synthetic replay, provider_tools untouched."""
    from blocks.chat.stream import run as stream_run
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.tool.executor import ToolExecutor

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    recorded = {}
    import blocks.chat.stream as stream_module
    monkeypatch.setattr(engine_module, "AIClient", lambda: _NoToolFakeClient(recorded))
    monkeypatch.setattr(stream_module, "AIClient", lambda: _NoToolFakeClient(recorded))

    invoked = []

    def _fake_execute(self, tool_name, arguments, context):  # pragma: no cover - shouldn't run
        invoked.append({"tool_name": tool_name, "arguments": dict(arguments)})
        return {"result": "noop", "is_error": False, "widget": None}

    with patch.object(ToolExecutor, "execute", _fake_execute):
        result = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": {"role": "user", "content": "hello"},
                "tools": [],
            },
            {},
        )
        events = list(result["events"])

    assert result.get("_sse") is True
    # No replay must happen when followup metadata is absent.
    assert invoked == []
    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events
    final_message = done_events[-1]["message"]
    assert final_message["metadata"]["executed_tools"] == []
    ChatStore._instance = None


def test_approval_followup_with_invalid_token_falls_through(tmp_path, monkeypatch):
    """A tampered or unknown approval token must not trigger the replay path
    so we never execute a tool the user did not approve."""
    from blocks.chat.stream import run as stream_run
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    approval.reset_approval_state_for_tests()
    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    recorded = {}
    import blocks.chat.stream as stream_module
    monkeypatch.setattr(engine_module, "AIClient", lambda: _NoToolFakeClient(recorded))
    monkeypatch.setattr(stream_module, "AIClient", lambda: _NoToolFakeClient(recorded))

    invoked = []

    def _fake_execute(self, tool_name, arguments, context):  # pragma: no cover - must not run
        invoked.append(tool_name)
        return {"result": "noop", "is_error": False, "widget": None}

    with patch.object(ToolExecutor, "execute", _fake_execute):
        result = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": {
                    "role": "user",
                    "content": "ユーザーが許可しました。",
                    "metadata": {
                        "approval_followup": {
                            "approval_token": "garbage.token",
                            "operation": "tool.coding_git_commit",
                            "request_id": "apr_unknown",
                            "tool_name": "coding_git_commit",
                        },
                    },
                },
                "tools": [],
            },
            {},
        )
        events = list(result["events"])

    assert result.get("_sse") is True
    # Invalid token must fall through to the model path: no synthetic replay.
    assert invoked == []
    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events
    final_message = done_events[-1]["message"]
    assert final_message["metadata"]["executed_tools"] == []
    ChatStore._instance = None


def test_approval_followup_tool_name_mismatch_falls_through(tmp_path, monkeypatch):
    """When the original approval request stored ``tool_name`` but the
    followup metadata targets a different tool, the engine must NOT replay
    the stored tool. Otherwise an attacker (or a stale UI) could reuse a
    valid token approved for tool A to invoke tool B with the same args.

    The engine must fall through to the regular model-driven path: no
    synthetic execution, no synthetic tool_use/tool_result on the chain,
    and ``executed_tools`` empty on the finalised assistant message.
    """
    from blocks.chat.stream import run as stream_run
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    args = {"message": "fix typo", "paths": ["a.txt"]}
    # Approval request explicitly records ``tool_name="coding_git_commit"``.
    token, request_id = _approve_pending(
        args, tool_name="coding_git_commit", operation="tool.coding_git_commit",
    )
    assert approval.get_approval_request(request_id) is not None

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    recorded = {}
    import blocks.chat.stream as stream_module
    monkeypatch.setattr(engine_module, "AIClient", lambda: _NoToolFakeClient(recorded))
    monkeypatch.setattr(stream_module, "AIClient", lambda: _NoToolFakeClient(recorded))

    invoked = []

    def _fake_execute(self, tool_name, arguments, context):  # pragma: no cover - must not run
        invoked.append(tool_name)
        return {"result": "noop", "is_error": False, "widget": None}

    with patch.object(ToolExecutor, "execute", _fake_execute):
        result = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": {
                    "role": "user",
                    "content": "ユーザーが許可しました。",
                    "metadata": {
                        "approval_followup": {
                            "approval_token": token,
                            "operation": "tool.coding_git_commit",
                            "request_id": request_id,
                            # Mismatch: original request stored
                            # ``coding_git_commit`` but the followup targets
                            # a different tool.
                            "tool_name": "coding_git_push",
                        },
                    },
                },
                "tools": [],
            },
            {},
        )
        events = list(result["events"])

    assert result.get("_sse") is True
    # Tool-name mismatch must abort replay before any synthetic execution.
    assert invoked == []
    started = [event for event in events if event.get("type") == "tool_call_started"]
    assert started == [], "no synthetic tool_call_started must be emitted on mismatch"
    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events
    final_message = done_events[-1]["message"]
    assert final_message["metadata"]["executed_tools"] == []
    # The token must remain unconsumed - mismatch should not burn it.
    args_hash = approval.hash_arguments(args)
    verification = approval.verify_execution_token(
        token, "tool.coding_git_commit", args_hash, consume=False,
    )
    assert verification.valid is True
    ChatStore._instance = None


def test_approval_followup_replay_with_nested_approval_required_short_circuits(tmp_path, monkeypatch):
    """If the replayed tool result itself reports ``approval_required`` (a
    chained / nested approval), the engine must surface the approval path
    directly and NOT advance to the natural-language summary turn. Letting
    the model speak in that state would produce the exact same hallucinated
    success the deterministic replay was introduced to prevent.

    Pinned behaviour:

    * an ``approval_requested`` event is emitted immediately after the
      synthetic ``tool_call_completed`` event;
    * the AI client is never called for a summary turn (the model loop is
      short-circuited);
    * the finalised assistant message carries ``finish_reason=approval_required``
      so the UI keeps the approval gate visible.
    """
    from blocks.chat.stream import run as stream_run
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    args = {"message": "fix typo", "paths": ["a.txt"]}
    token, request_id = _approve_pending(
        args, tool_name="coding_git_commit", operation="tool.coding_git_commit",
    )

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    recorded = {}
    import blocks.chat.stream as stream_module
    monkeypatch.setattr(engine_module, "AIClient", lambda: _NoToolFakeClient(recorded))
    monkeypatch.setattr(stream_module, "AIClient", lambda: _NoToolFakeClient(recorded))

    # Patch ``_complete_turn`` to fail loudly if the model is ever asked to
    # speak: the short-circuit must keep us out of the summary turn.
    from domain.chat.stream_engine import ChatRunEngine

    summary_calls: list[dict] = []

    def _fail_complete_turn(self, prepared, messages):  # pragma: no cover - must not run
        summary_calls.append({"model": prepared.model})
        raise AssertionError(
            "model summary turn must not run when replay surfaces approval_required"
        )

    monkeypatch.setattr(ChatRunEngine, "_complete_turn", _fail_complete_turn)

    invoked: list[dict] = []

    def _fake_execute(self, tool_name, arguments, context):
        invoked.append({"tool_name": tool_name, "arguments": dict(arguments)})
        # Simulate a chained / nested approval: the tool consumed its own
        # one-shot token but its result still reports another approval is
        # required (e.g. the underlying capability layer rejected the
        # current scope and raised a fresh approval gate).
        return {
            "result": "secondary approval required",
            "is_error": False,
            "widget": None,
            "requires_approval": True,
            "approval_required": True,
            "approval_request_id": "apr_nested_demo",
            "risk_level": "high",
            "action": "git.commit",
            "payload": dict(arguments),
            "message": "secondary approval required",
        }

    with patch.object(ToolExecutor, "execute", _fake_execute):
        result = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": {
                    "role": "user",
                    "content": "ユーザーが許可しました。続行してください。",
                    "metadata": {
                        "approval_followup": {
                            "approval_token": token,
                            "operation": "tool.coding_git_commit",
                            "request_id": request_id,
                            "tool_name": "coding_git_commit",
                        },
                    },
                },
                "tools": [],
            },
            {},
        )
        events = list(result["events"])

    assert result.get("_sse") is True
    # Replay still ran exactly once, but the summary turn never started.
    assert len(invoked) == 1
    assert summary_calls == []

    started = [event for event in events if event.get("type") == "tool_call_started"]
    completed = [event for event in events if event.get("type") == "tool_call_completed"]
    approval_events = [event for event in events if event.get("type") == "approval_requested"]
    assert len(started) == 1 and started[0].get("approval_replay") is True
    assert len(completed) == 1 and completed[0].get("approval_replay") is True
    # The approval_requested event must follow the tool_call_completed event,
    # not be swallowed by the summary turn.
    assert approval_events, events
    assert approval_events[0].get("tool_name") == "coding_git_commit"

    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events
    final_message = done_events[-1]["message"]
    # The replayed tool *was* executed deterministically (single shot), so it
    # must still surface in executed_tools, but the assistant must remain in
    # the approval-waiting state instead of summarising success.
    assert final_message["metadata"]["executed_tools"] == ["coding_git_commit"]
    assert final_message.get("finish_reason") == "approval_required"
    ChatStore._instance = None


def test_approval_followup_replay_with_tool_blocked_recovery_short_circuits(tmp_path, monkeypatch):
    """If the replayed tool reports a recovery kind that blocks further
    automation (``visible_window_required`` / ``focus_required``), the
    engine must emit the same ``tool_blocked`` status the model-driven path
    emits and short-circuit the model loop. Otherwise the model would
    speak as if the operation succeeded while the underlying tool never
    reached the host.
    """
    from blocks.chat.stream import run as stream_run
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.safety import approval
    from domain.tool.executor import ToolExecutor

    approval.reset_approval_state_for_tests()
    args = {"message": "focus me", "paths": ["a.txt"]}
    token, request_id = _approve_pending(
        args, tool_name="coding_git_commit", operation="tool.coding_git_commit",
    )

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None
    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    recorded = {}
    import blocks.chat.stream as stream_module
    monkeypatch.setattr(engine_module, "AIClient", lambda: _NoToolFakeClient(recorded))
    monkeypatch.setattr(stream_module, "AIClient", lambda: _NoToolFakeClient(recorded))

    from domain.chat.stream_engine import ChatRunEngine

    summary_calls: list[dict] = []

    def _fail_complete_turn(self, prepared, messages):  # pragma: no cover - must not run
        summary_calls.append({"model": prepared.model})
        raise AssertionError(
            "model summary turn must not run when replay surfaces tool_blocked"
        )

    monkeypatch.setattr(ChatRunEngine, "_complete_turn", _fail_complete_turn)

    invoked: list[dict] = []

    def _fake_execute(self, tool_name, arguments, context):
        invoked.append({"tool_name": tool_name, "arguments": dict(arguments)})
        return {
            "result": "target window not visible",
            "is_error": True,
            "widget": None,
            "recovery": {"kind": "visible_window_required"},
        }

    with patch.object(ToolExecutor, "execute", _fake_execute):
        result = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": {
                    "role": "user",
                    "content": "ユーザーが許可しました。続行してください。",
                    "metadata": {
                        "approval_followup": {
                            "approval_token": token,
                            "operation": "tool.coding_git_commit",
                            "request_id": request_id,
                            "tool_name": "coding_git_commit",
                        },
                    },
                },
                "tools": [],
            },
            {},
        )
        events = list(result["events"])

    assert result.get("_sse") is True
    assert len(invoked) == 1
    assert summary_calls == []

    started = [event for event in events if event.get("type") == "tool_call_started"]
    completed = [event for event in events if event.get("type") == "tool_call_completed"]
    blocked_status = [
        event for event in events
        if event.get("type") == "status"
        and (
            event.get("recovery_kind") == "visible_window_required"
            or event.get("phase") == "tool_blocked"
        )
    ]
    assert len(started) == 1 and started[0].get("approval_replay") is True
    assert len(completed) == 1 and completed[0].get("approval_replay") is True
    assert blocked_status, events

    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events
    final_message = done_events[-1]["message"]
    # Replay ran once, so the executed tool surfaces, but the assistant must
    # remain in the blocked-recovery state instead of summarising success.
    assert final_message["metadata"]["executed_tools"] == ["coding_git_commit"]
    assert final_message.get("finish_reason") in {"tool_blocked", "stop"}, final_message
    ChatStore._instance = None
