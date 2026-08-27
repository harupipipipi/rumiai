from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.contract


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.agent_runtime.completion_gate import (  # noqa: E402
    CompletionGateContractError,
    CompletionGateCoordinator,
    CompletionGateRegistry,
    get_completion_gate_registry,
)


def _execution(
    *,
    gates: list[str] | None = None,
    policy: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        execution_id="run_fixture",
        context={
            "completion_gates": gates or [],
            "completion_gate_policy": policy or {},
            "principal": {"type": "agent", "id": "fixture-agent"},
        },
        steps=[],
        model="stub/model",
    )


def _evaluate(
    coordinator: CompletionGateCoordinator,
    execution: SimpleNamespace,
    candidate: Any,
    *,
    cancelled: Any = False,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    checker = cancelled if callable(cancelled) else lambda: bool(cancelled)
    outcome = coordinator.evaluate(
        execution,
        candidate,
        record_event=lambda event, payload: events.append((event, payload)),
        is_cancelled=checker,
    )
    return outcome, events


def test_registry_rejects_duplicate_gate_ids() -> None:
    registry = CompletionGateRegistry()
    registry.register("fixture", lambda request: {"verdict": "pass"})

    with pytest.raises(CompletionGateContractError):
        registry.register("fixture", lambda request: {"verdict": "pass"})


def test_multiple_gates_run_in_declared_order_and_duplicate_evaluation_is_idempotent() -> None:
    registry = CompletionGateRegistry()
    calls: list[tuple[str, str]] = []

    def handler(gate_id: str):
        def run(request: dict[str, Any]) -> dict[str, Any]:
            calls.append((gate_id, request["idempotency_key"]))
            return {
                "verdict": "pass",
                "summary": gate_id,
                "evidence": [{"gate": gate_id}],
                "resolved_model": "reviewer/model",
            }

        return run

    registry.register("first", handler("first"))
    registry.register("second", handler("second"))
    coordinator = CompletionGateCoordinator(registry)
    execution = _execution(gates=["first", "second"])

    first, events = _evaluate(coordinator, execution, "candidate")
    duplicate, _ = _evaluate(coordinator, execution, "candidate")

    assert first["action"] == "pass"
    assert duplicate["action"] == "pass"
    assert [item[0] for item in calls] == ["first", "second"]
    verdicts = [payload for event, payload in events if event == "completion_gate_verdict"]
    assert [item["gate_id"] for item in verdicts] == ["first", "second"]
    assert verdicts[0]["resolved_model"] == "reviewer/model"
    assert verdicts[0]["evidence"] == [{"gate": "first"}]


def test_revision_restarts_chain_and_stagnation_is_bounded() -> None:
    registry = CompletionGateRegistry()
    registry.register(
        "review",
        lambda request: {
            "verdict": "revise",
            "summary": "needs work",
            "instruction": "add the missing test",
        },
    )
    coordinator = CompletionGateCoordinator(registry)
    execution = _execution(
        gates=["review"],
        policy={"max_iterations": 5, "stagnation_limit": 2},
    )

    first, _ = _evaluate(coordinator, execution, "draft one")
    second, _ = _evaluate(coordinator, execution, "draft two")

    assert first["action"] == "revise"
    assert first["instruction"] == "add the missing test"
    assert second["action"] == "blocked"
    assert second["terminal_reason"] == "stagnation_budget"


@pytest.mark.parametrize(
    ("handler", "terminal_reason"),
    [
        (lambda request: {"verdict": "maybe"}, "malformed_verdict"),
        (lambda request: "pass", "malformed_verdict"),
    ],
)
def test_malformed_gate_output_never_becomes_implicit_pass(
    handler: Any,
    terminal_reason: str,
) -> None:
    registry = CompletionGateRegistry()
    registry.register("bad", handler)

    outcome, _ = _evaluate(
        CompletionGateCoordinator(registry), _execution(gates=["bad"]), "candidate"
    )

    assert outcome["action"] == "blocked"
    assert outcome["terminal_reason"] == terminal_reason


def test_unknown_disabled_and_cycle_fail_closed() -> None:
    registry = CompletionGateRegistry()
    registry.register("disabled", lambda request: {"verdict": "pass"}, enabled=False)
    coordinator = CompletionGateCoordinator(registry)

    unknown, _ = _evaluate(coordinator, _execution(gates=["missing"]), "candidate")
    disabled, _ = _evaluate(coordinator, _execution(gates=["disabled"]), "candidate")
    cycle, _ = _evaluate(coordinator, _execution(gates=["disabled", "disabled"]), "candidate")

    assert unknown["terminal_reason"] == "gate_unavailable"
    assert disabled["terminal_reason"] == "gate_unavailable"
    assert cycle["terminal_reason"] == "gate_cycle"


def test_explicit_failed_policy_returns_failed_for_provider_exhaustion() -> None:
    registry = CompletionGateRegistry()
    calls = 0

    def fail(request: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider unavailable")

    registry.register("provider", fail)
    execution = _execution(
        gates=["provider"],
        policy={"failure_mode": "failed", "max_attempts_per_gate": 2},
    )

    outcome, events = _evaluate(CompletionGateCoordinator(registry), execution, "candidate")

    assert outcome["action"] == "failed"
    assert outcome["terminal_reason"] == "provider_failure"
    assert calls == 2
    failures = [event for event, _ in events if event == "completion_gate_delivery_failed"]
    assert len(failures) == 2


def test_timeout_is_bounded_and_fails_closed() -> None:
    registry = CompletionGateRegistry()

    def slow(request: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.05)
        return {"verdict": "pass"}

    registry.register("slow", slow)
    execution = _execution(
        gates=["slow"],
        policy={"timeout_seconds": 0.01, "max_attempts_per_gate": 1},
    )

    started = time.monotonic()
    outcome, _ = _evaluate(CompletionGateCoordinator(registry), execution, "candidate")

    assert time.monotonic() - started < 0.04
    assert outcome["action"] == "blocked"
    assert outcome["terminal_reason"] == "timeout"


def test_cancel_wins_race_against_delivered_pass() -> None:
    registry = CompletionGateRegistry()
    state = {"cancelled": False}

    def pass_then_cancel(request: dict[str, Any]) -> dict[str, Any]:
        state["cancelled"] = True
        return {"verdict": "pass"}

    registry.register("race", pass_then_cancel)
    outcome, events = _evaluate(
        CompletionGateCoordinator(registry),
        _execution(gates=["race"]),
        "candidate",
        cancelled=lambda: state["cancelled"],
    )

    assert outcome["action"] == "cancelled"
    assert any(event == "completion_gate_cancelled" for event, _ in events)


def test_blocked_gate_preserves_requirement_and_candidate() -> None:
    registry = CompletionGateRegistry()
    registry.register(
        "authority-review",
        lambda request: {
            "verdict": "blocked",
            "summary": "operator approval required",
            "required_user_action": {
                "type": "authority_approval",
                "request_id": "approval-1",
            },
            "evidence": [{"receipt": "candidate-reviewed"}],
        },
    )

    execution = _execution(gates=["authority-review"])
    outcome, _ = _evaluate(
        CompletionGateCoordinator(registry),
        execution,
        {"answer": 42},
    )

    assert outcome["action"] == "blocked"
    assert outcome["candidate"] == {"answer": 42}
    assert outcome["required_user_action"]["type"] == "authority_approval"
    assert (
        execution.context["completion_gate_state"]["verdicts"][-1]["resolved_model"] == "stub/model"
    )


def test_transformed_result_requires_explicit_registration_capability() -> None:
    def transform(request: dict[str, Any]) -> dict[str, Any]:
        return {"verdict": "pass", "transformed_result": "replacement"}

    denied_registry = CompletionGateRegistry()
    denied_registry.register("transform", transform)
    denied, _ = _evaluate(
        CompletionGateCoordinator(denied_registry),
        _execution(gates=["transform"]),
        "original",
    )

    allowed_registry = CompletionGateRegistry()
    allowed_registry.register("transform", transform, allow_transformed_result=True)
    allowed, _ = _evaluate(
        CompletionGateCoordinator(allowed_registry),
        _execution(gates=["transform"]),
        "original",
    )

    assert denied["action"] == "blocked"
    assert denied["terminal_reason"] == "malformed_verdict"
    assert allowed["action"] == "pass"
    assert allowed["candidate"] == "replacement"


@pytest.mark.skipif(sys.platform == "win32", reason="soon imports fcntl in frontend settings")
def test_agent_engine_passes_candidate_and_writes_durable_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, store = _isolated_engine(tmp_path, monkeypatch)
    registry = get_completion_gate_registry()
    registry.register(
        "fixture.pass",
        lambda request: {
            "verdict": "pass",
            "summary": "quality checks passed",
            "evidence": [{"test": "ok"}],
            "resolved_model": "fixture/reviewer",
        },
    )
    engine._ai_complete = lambda messages, model, context, tools=None: {
        "status": "ok",
        "data": {"content": "candidate answer"},
    }

    result = engine.execute(
        "answer",
        [],
        "stub/model",
        None,
        {"agent_id": "fixture", "completion_gates": ["fixture.pass"]},
    )

    assert result["status"] == "completed"
    assert result["result"]["result"] == "candidate answer"
    events = store.events(result["execution_id"], 100)
    event_types = [event["event_type"] for event in events]
    assert "candidate_complete" in event_types
    assert "completion_gate_attempt_started" in event_types
    assert "completion_gate_verdict" in event_types
    verdict = next(
        event["payload_json"]
        for event in events
        if event["event_type"] == "completion_gate_verdict"
    )
    assert verdict["gate_id"] == "fixture.pass"
    assert verdict["attempt"] == 1
    assert verdict["evidence"] == [{"test": "ok"}]
    assert verdict["resolved_model"] == "fixture/reviewer"


@pytest.mark.skipif(sys.platform == "win32", reason="soon imports fcntl in frontend settings")
def test_agent_engine_revises_same_run_then_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = _isolated_engine(tmp_path, monkeypatch)
    registry = get_completion_gate_registry()

    def review(request: dict[str, Any]) -> dict[str, Any]:
        if request["candidate"] == "draft":
            return {
                "verdict": "revise",
                "summary": "missing proof",
                "instruction": "include proof",
            }
        return {"verdict": "pass", "summary": "proof present"}

    registry.register("fixture.review", review)
    answers = iter(["draft", "final with proof"])
    engine._ai_complete = lambda messages, model, context, tools=None: {
        "status": "ok",
        "data": {"content": next(answers)},
    }

    result = engine.execute(
        "answer",
        [],
        "stub/model",
        None,
        {"completion_gates": ["fixture.review"]},
    )

    assert result["status"] == "completed"
    assert result["result"]["result"] == "final with proof"
    assert any(
        step["step_type"] == "completion_gate_revision" for step in result["result"]["steps"]
    )
    assert result["result"]["execution_id"] == result["execution_id"]


@pytest.mark.skipif(sys.platform == "win32", reason="soon imports fcntl in frontend settings")
def test_agent_engine_restart_resumes_blocked_gate_with_same_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = _isolated_engine(tmp_path, monkeypatch)
    registry = get_completion_gate_registry()
    approved = {"value": False}
    idempotency_keys: list[str] = []

    def authority_gate(request: dict[str, Any]) -> dict[str, Any]:
        idempotency_keys.append(request["idempotency_key"])
        if not approved["value"]:
            return {
                "verdict": "blocked",
                "summary": "approval required",
                "required_user_action": {
                    "type": "authority_approval",
                    "request_id": "approval-1",
                },
            }
        assert request["resume_evidence"] == [{"approval_id": "approval-1"}]
        return {"verdict": "pass", "summary": "approved"}

    registry.register("fixture.authority", authority_gate)
    engine._ai_complete = lambda messages, model, context, tools=None: {
        "status": "ok",
        "data": {"content": "preserved candidate"},
    }
    started = engine.execute(
        "answer",
        [],
        "stub/model",
        None,
        {"completion_gates": ["fixture.authority"]},
    )
    assert started["status"] == "blocked"
    blocked_status = engine.status(started["execution_id"])
    assert blocked_status["result"] == "preserved candidate"
    assert blocked_status["completion_gate"]["phase"] == "blocked"
    assert blocked_status["completion_gate"]["pending_requirement"]["type"] == "authority_approval"
    approved["value"] = True

    from domain.agent.engine import AgentEngine

    restarted = AgentEngine()
    resumed = restarted.resume_completion_gate(
        started["execution_id"], {"approval_id": "approval-1"}
    )

    assert resumed["status"] == "completed"
    assert resumed["result"]["result"] == "preserved candidate"
    assert len(idempotency_keys) == 2
    assert idempotency_keys[0] != idempotency_keys[1]


@pytest.mark.skipif(sys.platform == "win32", reason="soon imports fcntl in frontend settings")
def test_agent_http_blocks_attach_status_and_resume_completion_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine, _store = _isolated_engine(tmp_path, monkeypatch)
    registry = get_completion_gate_registry()
    approved = {"value": False}

    def review(request: dict[str, Any]) -> dict[str, Any]:
        if approved["value"]:
            return {"verdict": "pass", "summary": "approved"}
        return {
            "verdict": "blocked",
            "summary": "approval required",
            "required_user_action": {
                "type": "authority_approval",
                "request_id": "approval-http",
            },
        }

    registry.register("fixture.http", review)

    from blocks.agent import execute as execute_block
    from blocks.agent import resume_completion_gate as resume_block
    from blocks.agent import setup as setup_block
    from blocks.agent import status as status_block
    from blocks.agent._state import _engines
    from domain.agent.engine import AgentEngine

    _engines.clear()
    monkeypatch.setattr(
        AgentEngine,
        "_ai_complete",
        lambda self, messages, model, context, tools=None: {
            "status": "ok",
            "data": {"content": "http candidate"},
        },
    )
    started = execute_block.run(
        {
            "task": "answer",
            "model": "stub/model",
            "completion_gates": ["fixture.http"],
        },
        {},
    )
    assert started["status"] == "ok"
    assert started["data"]["status"] == "blocked"
    execution_id = started["data"]["execution_id"]

    status = status_block.run({"execution_id": execution_id}, {})
    assert status["data"]["status"] == "blocked"
    assert status["data"]["result"] == "http candidate"
    assert status["data"]["completion_gate"]["phase"] == "blocked"

    approved["value"] = True
    resumed = resume_block.run(
        {
            "execution_id": execution_id,
            "evidence": {"approval_id": "approval-http"},
        },
        {},
    )
    assert resumed["status"] == "ok"
    assert resumed["data"]["status"] == "completed"

    route_path = "/api/agent/{id}/completion-gate/resume"

    class RouteRegistry:
        def __init__(self) -> None:
            self.entries: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

        def get(self, _key: str) -> None:
            return None

        def register(
            self, key: str, value: dict[str, Any], meta: dict[str, Any] | None = None
        ) -> None:
            self.entries.append((key, value, meta or {}))

    route_registry = RouteRegistry()
    setup_block.run({"interface_registry": route_registry})
    route = next(
        value
        for key, value, _meta in route_registry.entries
        if key == "io.http.route" and value["method"] == "POST" and value["pattern"] == route_path
    )
    assert route["path_inject"] == {"id": "execution_id"}
    missing = route["handler"]({"execution_id": "missing"}, {})
    assert missing["status"] == "error"
    assert missing["error"]["message"] == "execution not found"


@pytest.mark.skipif(sys.platform == "win32", reason="soon imports fcntl in frontend settings")
def test_agent_engine_restart_during_revision_resumes_without_duplicate_instruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, store = _isolated_engine(tmp_path, monkeypatch)
    registry = get_completion_gate_registry()

    def review(request: dict[str, Any]) -> dict[str, Any]:
        if request["candidate"] == "draft before restart":
            return {
                "verdict": "revise",
                "summary": "add recovery proof",
                "instruction": "include the recovery proof",
            }
        return {"verdict": "pass", "summary": "recovery proof accepted"}

    registry.register("fixture.revision-restart", review)
    calls = 0

    def crash_during_revision(messages, model, context, tools=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "status": "ok",
                "data": {"content": "draft before restart"},
            }
        raise RuntimeError("simulated process loss during revision model call")

    engine._ai_complete = crash_during_revision
    with pytest.raises(RuntimeError, match="simulated process loss"):
        engine.execute(
            "answer",
            [],
            "stub/model",
            None,
            {"completion_gates": ["fixture.revision-restart"]},
        )

    stored = store.list_runs(status="running", limit=10)
    assert len(stored) == 1
    execution_id = stored[0]["run_id"]
    persisted = store.load_execution_dict(execution_id)
    assert persisted["context"]["completion_gate_state"]["phase"] == "revising"
    assert (
        sum(
            1
            for message in persisted["messages"]
            if "[COMPLETION GATE REVISION]" in str(message.get("content") or "")
        )
        == 1
    )

    from domain.agent.engine import AgentEngine

    restarted = AgentEngine()
    restarted._ai_complete = lambda messages, model, context, tools=None: {
        "status": "ok",
        "data": {"content": "final with recovery proof"},
    }
    resumed = restarted.resume_completion_gate(execution_id)

    assert resumed["status"] == "completed"
    assert resumed["result"]["execution_id"] == execution_id
    assert resumed["result"]["result"] == "final with recovery proof"
    completed_persisted = store.load_execution_dict(execution_id)
    assert (
        sum(
            1
            for message in completed_persisted["messages"]
            if "[COMPLETION GATE REVISION]" in str(message.get("content") or "")
        )
        == 1
    )
    assert any(
        event["event_type"] == "completion_gate_revision_resumed"
        for event in store.events(execution_id, 100)
    )


@pytest.mark.skipif(sys.platform == "win32", reason="soon imports fcntl in frontend settings")
def test_agent_engine_has_no_feature_specific_completion_gate_branch() -> None:
    source = (DEFAULTSPACK_ROOT / "domain" / "agent" / "engine.py").read_text(encoding="utf-8")

    assert "Loop Engineering" not in source
    assert "goal_completion_gate" not in source
    assert "loop_completion_gate" not in source


def _isolated_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", str(tmp_path / "agent_runtime"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AGENT_TRANSCRIPT_DIR", str(tmp_path / "transcripts"))
    from domain.agent.engine import AgentEngine
    from domain.agent_runtime.run_store import AgentRunStore
    from domain.agent_runtime.transcript import TranscriptStore

    monkeypatch.setattr(
        "domain.agent.engine.get_model_capabilities",
        lambda model: {
            "profile_id": model,
            "supports_tool_calling": True,
            "supports_vision": True,
            "supports_image_input": True,
            "supports_thinking": True,
            "supports_fast": True,
        },
    )
    AgentRunStore._instance = None
    TranscriptStore._instance = None
    get_completion_gate_registry().clear()
    engine = AgentEngine()
    return engine, AgentRunStore()
