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
    # Defensive scrub: the chained-approval simulation above returns
    # ``payload=dict(arguments)`` which includes the outer (now spent)
    # one-shot ``approval_token``. The bubbled-up approval payload must
    # NOT carry that token forward, otherwise UIs / downstream loggers
    # would see the spent credential and a malicious component could
    # attempt to replay it. The chained approval must mint its own
    # token, never recycle ours.
    nested_payload = approval_events[0].get("payload") or {}
    assert isinstance(nested_payload, dict)
    assert "approval_token" not in nested_payload, approval_events[0]
    assert approval_events[0].get("approval_token") != token, approval_events[0]

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


def test_approval_followup_token_cannot_replay_twice(tmp_path, monkeypatch):
    """The one-shot approval token must be replay-safe across separate
    chat runs: once the first ``approval_followup`` has executed the
    pending tool (which consumes the token via ``verify_execution_token``
    and flips the request status to ``consumed``), a *second* chat run
    that carries the same ``approval_token`` + ``request_id`` must NOT
    execute the tool a second time. The replay path falls through to the
    regular model-driven turn instead so the user / model can never
    silently double-spend an approval.
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

    from domain.chat.stream_engine import ChatRunEngine

    def _fake_complete_turn(self, prepared, messages):
        recorded.setdefault("complete_calls", []).append(
            {
                "model": prepared.model,
                "tools": list(prepared.provider_tools or []),
            }
        )
        return {
            "content": [{"type": "text", "text": "ok"}],
            "finish_reason": "stop",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(ChatRunEngine, "_complete_turn", _fake_complete_turn)

    invoked: list[dict] = []

    def _fake_execute(self, tool_name, arguments, context):
        invoked.append({"tool_name": tool_name, "arguments": dict(arguments)})
        # Real coding tools consume the one-shot token via
        # ``verify_execution_token(consume=True)``; mirror that here so the
        # approval store transitions to ``consumed`` exactly the way the
        # production tool body does, exercising the replay-safety contract
        # end-to-end without depending on the real tool implementation.
        tok = str((arguments or {}).get("approval_token") or "").strip()
        if tok:
            try:
                from domain.safety import approval as _approval_mod

                replay_args = {k: v for k, v in arguments.items() if k != "approval_token"}
                _approval_mod.verify_execution_token(
                    tok,
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

    followup_message = {
        "role": "user",
        "content": "ユーザーが許可しました。承認済みの操作を続行してください。",
        "metadata": {
            "approval_followup": {
                "approval_token": token,
                "operation": "tool.coding_git_commit",
                "request_id": request_id,
                "tool_name": "coding_git_commit",
            },
        },
    }

    with patch.object(ToolExecutor, "execute", _fake_execute):
        first = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": dict(followup_message),
                "tools": [],
            },
            {},
        )
        first_events = list(first["events"])

        # The approval store must now report the request as consumed and
        # ``verify_execution_token`` must reject the same token, before the
        # second chat run is even attempted.
        request_after_first = approval.get_approval_request(request_id)
        assert request_after_first is not None
        assert request_after_first["status"] == "consumed"
        verification_after_first = approval.verify_execution_token(
            token,
            "tool.coding_git_commit",
            approval.hash_arguments(args),
            consume=False,
        )
        assert verification_after_first.valid is False

        second = stream_run(
            {
                "conversation_id": conversation["id"],
                "message": dict(followup_message),
                "tools": [],
            },
            {},
        )
        second_events = list(second["events"])

    # First run replayed the tool exactly once.
    assert first.get("_sse") is True
    started_first = [event for event in first_events if event.get("type") == "tool_call_started"]
    assert len(started_first) == 1
    assert started_first[0].get("approval_replay") is True

    # Second run: the same token must not produce a synthetic replay event,
    # and the tool must not be invoked a second time.
    assert second.get("_sse") is True
    started_second = [event for event in second_events if event.get("type") == "tool_call_started"]
    replay_second = [event for event in started_second if event.get("approval_replay") is True]
    assert replay_second == [], second_events
    assert len(invoked) == 1, invoked

    # The second assistant message must reflect the fall-through path: no
    # synthetic execution surfaces in ``executed_tools``.
    done_second = [event for event in second_events if event.get("type") == "done"]
    assert done_second
    final_second = done_second[-1]["message"]
    assert final_second["metadata"]["executed_tools"] == []
    ChatStore._instance = None


def test_approval_followup_replay_keeps_attached_tools_metadata_truthful(tmp_path, monkeypatch):
    """The replay path suppresses ``provider_tools`` for the *summary turn
    only* so the model cannot re-issue another tool call from the same
    followup. The finalised assistant ``metadata.attached_tools`` and
    ``metadata.attached_tool_count`` must still reflect the truthful set
    of tools the conversation was started with - otherwise auditors and
    UI surfaces would see ``attached_tools=[]`` for a turn that was
    actually attached to coding tools, masking tool-policy bugs.
    """
    from blocks.chat.stream import run as stream_run
    import domain.chat.stream_engine as engine_module
    from domain.chat.store import ChatStore
    from domain.chat.run_request import prepare_chat_run as _real_prepare_chat_run
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

    # Inject a non-empty ``provider_tools`` list on the prepared run so the
    # suppression in the replay path is observable AND the metadata
    # snapshot path is exercised. Going through ``prepare_chat_run``
    # naturally would require a full tool-policy + eligibility setup that
    # is not the subject of this regression.
    fake_tool_def = {
        "type": "function",
        "function": {
            "name": "coding_git_commit",
            "description": "Stage + commit changes",
            "parameters": {"type": "object", "properties": {}},
        },
    }

    def _wrapped_prepare(input_data, context):
        prepared = _real_prepare_chat_run(input_data, context)
        prepared.provider_tools = [fake_tool_def]
        seen = {name for name in prepared.tools_called or []}
        if "coding_git_commit" not in seen:
            prepared.tools_called = list(prepared.tools_called or []) + ["coding_git_commit"]
        return prepared

    monkeypatch.setattr(engine_module, "prepare_chat_run", _wrapped_prepare)

    recorded = {}
    import blocks.chat.stream as stream_module
    monkeypatch.setattr(engine_module, "AIClient", lambda: _NoToolFakeClient(recorded))
    monkeypatch.setattr(stream_module, "AIClient", lambda: _NoToolFakeClient(recorded))

    from domain.chat.stream_engine import ChatRunEngine

    def _fake_complete_turn(self, prepared, messages):
        recorded.setdefault("complete_calls", []).append(
            {
                "model": prepared.model,
                "tools": list(prepared.provider_tools or []),
                "messages": messages,
            }
        )
        return {
            "content": [{"type": "text", "text": "Commit summary: hash=abc1234."}],
            "finish_reason": "stop",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(ChatRunEngine, "_complete_turn", _fake_complete_turn)

    invoked: list[dict] = []

    def _fake_execute(self, tool_name, arguments, context):
        invoked.append({"tool_name": tool_name, "arguments": dict(arguments)})
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
    # Replay must have run once and the summary turn must have run with
    # provider_tools suppressed (so the model cannot re-issue another tool
    # call from the same followup turn).
    assert len(invoked) == 1
    assert recorded.get("complete_calls"), "summary turn never ran"
    assert recorded["complete_calls"][0]["tools"] == []

    done_events = [event for event in events if event.get("type") == "done"]
    assert done_events
    final_message = done_events[-1]["message"]
    metadata = final_message["metadata"]
    # Despite the transient suppression, the truthful attached-tool set
    # must remain on the finalised metadata.
    assert "coding_git_commit" in metadata["attached_tools"]
    assert metadata["attached_tool_count"] == 1
    assert "coding_git_commit" in metadata["attached_provider_tools"]
    assert metadata["executed_tools"] == ["coding_git_commit"]
    # The synthetic tool_use block fed to the summary turn must NOT carry
    # the approval token: the model context view of the turn would
    # otherwise expose the one-shot signed token to any downstream
    # serialiser, log, or provider trace. We walk both shapes the chat
    # backend can emit - Anthropic-style ``content``-list-of-blocks and
    # OpenAI-style ``tool_calls[*].function.arguments`` (JSON) - so the
    # leak check is non-vacuous even when ``_append_assistant_tool_use_message``
    # routes through the OpenAI-style ``tool_calls`` field.
    summary_messages = recorded["complete_calls"][0].get("messages")
    assert isinstance(summary_messages, list), recorded["complete_calls"][0]
    assert summary_messages, "summary turn must run with a non-empty message chain"
    saw_synthetic_tool_call = False
    for msg in summary_messages:
        if not isinstance(msg, dict):
            continue
        # Anthropic-style content blocks (``[{"type": "tool_use", "input": {...}}, ...]``).
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") in {"tool_use", "tool_call"}:
                    block_input = block.get("input") or block.get("arguments") or {}
                    if isinstance(block_input, dict):
                        assert "approval_token" not in block_input, block
                        saw_synthetic_tool_call = True
        # OpenAI-style ``tool_calls`` field with JSON-encoded arguments.
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                raw_arguments = fn.get("arguments") if "arguments" in fn else call.get("arguments")
                if isinstance(raw_arguments, str):
                    try:
                        decoded = __import__("json").loads(raw_arguments)
                    except Exception:
                        decoded = {}
                else:
                    decoded = raw_arguments if isinstance(raw_arguments, dict) else {}
                if isinstance(decoded, dict):
                    assert "approval_token" not in decoded, call
                    saw_synthetic_tool_call = True
                # The serialised JSON must not carry the literal token even
                # when the assertion above is bypassed by an exotic shape.
                if isinstance(raw_arguments, str):
                    assert token not in raw_arguments, call
        # Tool-result messages must not echo the token in their content
        # text either - downstream serialisers / loggers would otherwise
        # see the spent token in the model context view.
        if msg.get("role") == "tool":
            tool_content = msg.get("content")
            if isinstance(tool_content, str):
                assert token not in tool_content, msg
    assert saw_synthetic_tool_call, summary_messages
    ChatStore._instance = None
