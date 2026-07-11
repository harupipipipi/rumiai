from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.chat.idempotency import (  # noqa: E402
    ChatIdempotencyStore,
    IdempotencyConflictError,
    operation_key,
    operation_scope,
    payload_hash,
    reserve_chat_operation,
)
from domain.chat.stream_engine import ChatRunEngine  # noqa: E402


def _input(key: str = "operation-123") -> dict:
    return {
        "conversation_id": "conversation-1",
        "idempotency_key": key,
        "message": {"role": "user", "content": "hello"},
        "params": {"workspace_id": "workspace-1"},
    }


def test_operation_key_validation_and_hash_contract() -> None:
    request = _input()
    assert operation_key(request) == "operation-123"
    assert payload_hash(request) == payload_hash(
        {**request, "idempotency_key": "another-key"}
    )
    with pytest.raises(ValueError, match="idempotency_key"):
        operation_key(_input("short"))


def test_scope_isolates_principal_workspace_session_and_conversation() -> None:
    request = _input()
    base = operation_scope(request, {"principal_id": "alice", "session_id": "s1"})
    assert base != operation_scope(request, {"principal_id": "bob", "session_id": "s1"})
    assert base != operation_scope(
        request, {"principal_id": "alice", "session_id": "s2"}
    )
    assert base != operation_scope(
        {**request, "conversation_id": "conversation-2"},
        {"principal_id": "alice", "session_id": "s1"},
    )


def test_store_claims_once_replays_and_rejects_conflicts(tmp_path: Path) -> None:
    store = ChatIdempotencyStore(tmp_path / "operations.sqlite3")
    first = store.claim("scope", "operation-123", "hash-a")
    assert first.state == "claimed"
    in_flight = store.claim("scope", "operation-123", "hash-a")
    assert (in_flight.state, in_flight.status) == ("replay", "in_progress")
    events = [{"type": "done", "data": {"message": {"id": "assistant-1"}}}]
    store.finish("scope", "operation-123", "hash-a", "completed", events)
    completed = store.claim("scope", "operation-123", "hash-a")
    assert completed.status == "completed"
    assert completed.events == events
    with pytest.raises(IdempotencyConflictError):
        store.claim("scope", "operation-123", "hash-b")


def test_concurrent_claim_has_one_owner(tmp_path: Path) -> None:
    store = ChatIdempotencyStore(tmp_path / "operations.sqlite3")

    def claim(_: int) -> str:
        return store.claim("scope", "operation-123", "hash-a").state

    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(claim, range(16)))
    assert states.count("claimed") == 1
    assert states.count("replay") == 15


def test_engine_completed_retry_replays_without_second_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_CHAT_IDEMPOTENCY_DB", str(tmp_path / "operations.sqlite3"))
    executions = 0

    def stream_once(self, input_data, context=None, *, stream_mode=True):
        nonlocal executions
        executions += 1
        yield {"type": "user_message_committed", "data": {"message": {"id": "user-1"}}}
        yield {"type": "done", "data": {"message": {"id": "assistant-1"}}}

    monkeypatch.setattr(ChatRunEngine, "_stream_once", stream_once)
    first = list(ChatRunEngine().stream(_input()))
    replay = list(ChatRunEngine().stream(_input()))

    assert executions == 1
    assert replay == first


def test_http_reservation_is_consumed_by_engine_without_self_deduping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_CHAT_IDEMPOTENCY_DB", str(tmp_path / "operations.sqlite3"))
    executions = 0

    def stream_once(self, input_data, context=None, *, stream_mode=True):
        nonlocal executions
        executions += 1
        yield {"type": "done", "data": {"message": {"id": "assistant-1"}}}

    monkeypatch.setattr(ChatRunEngine, "_stream_once", stream_once)
    context = reserve_chat_operation(_input(), {"principal_id": "alice"})

    events = list(ChatRunEngine().stream(_input(), context))

    assert executions == 1
    assert events[-1]["type"] == "done"


def test_engine_rejects_same_key_with_different_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUMI_CHAT_IDEMPOTENCY_DB", str(tmp_path / "operations.sqlite3"))

    def stream_once(self, input_data, context=None, *, stream_mode=True):
        yield {"type": "done", "data": {"message": {"id": "assistant-1"}}}

    monkeypatch.setattr(ChatRunEngine, "_stream_once", stream_once)
    list(ChatRunEngine().stream(_input()))
    changed = _input()
    changed["message"] = {"role": "user", "content": "different"}
    conflict = list(ChatRunEngine().stream(changed))

    assert conflict[0]["data"]["error"]["code"] == "IDEMPOTENCY_CONFLICT"
