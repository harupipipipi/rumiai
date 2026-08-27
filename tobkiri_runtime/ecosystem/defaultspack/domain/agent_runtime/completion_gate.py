from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable


CompletionGateHandler = Callable[[dict[str, Any]], dict[str, Any]]
GateEventRecorder = Callable[[str, dict[str, Any]], None]
CancellationCheck = Callable[[], bool]


class CompletionGateContractError(ValueError):
    """Raised when a gate or policy violates the completion-gate contract."""


@dataclass(frozen=True)
class CompletionGateRegistration:
    """One globally registered completion gate implementation."""

    gate_id: str
    handler: CompletionGateHandler
    enabled: bool = True
    allow_transformed_result: bool = False


@dataclass(frozen=True)
class CompletionGatePolicy:
    """Bounded policy attached to one agent run."""

    gate_ids: tuple[str, ...]
    max_iterations: int = 3
    max_attempts_per_gate: int = 2
    timeout_seconds: float = 30.0
    max_wall_clock_seconds: float = 300.0
    stagnation_limit: int = 2
    failure_mode: str = "blocked"

    @classmethod
    def from_context(cls, context: dict[str, Any] | None) -> "CompletionGatePolicy":
        """Resolve ordered gate IDs and budgets from run/profile policy."""

        context = context if isinstance(context, dict) else {}
        run_policy = (
            context.get("run_policy") if isinstance(context.get("run_policy"), dict) else {}
        )
        runtime_profile = (
            context.get("runtime_profile")
            if isinstance(context.get("runtime_profile"), dict)
            else {}
        )
        raw_gates = context.get("completion_gates")
        if raw_gates is None:
            raw_gates = run_policy.get("completion_gates")
        if raw_gates is None:
            raw_gates = runtime_profile.get("completion_gates")
        gate_ids = _normalize_gate_ids(raw_gates)

        raw_policy: dict[str, Any] = {}
        for source in (
            runtime_profile.get("completion_gate_policy"),
            run_policy.get("completion_gate_policy"),
            context.get("completion_gate_policy"),
        ):
            if isinstance(source, dict):
                raw_policy.update(source)
        failure_mode = str(raw_policy.get("failure_mode") or "blocked").strip().lower()
        if failure_mode not in {"blocked", "failed"}:
            raise CompletionGateContractError(
                "completion gate failure_mode must be 'blocked' or 'failed'"
            )
        return cls(
            gate_ids=gate_ids,
            max_iterations=_bounded_int(raw_policy.get("max_iterations"), 3, 1, 100),
            max_attempts_per_gate=_bounded_int(raw_policy.get("max_attempts_per_gate"), 2, 1, 20),
            timeout_seconds=_bounded_float(raw_policy.get("timeout_seconds"), 30.0, 0.01, 3600.0),
            max_wall_clock_seconds=_bounded_float(
                raw_policy.get("max_wall_clock_seconds"), 300.0, 0.01, 86400.0
            ),
            stagnation_limit=_bounded_int(raw_policy.get("stagnation_limit"), 2, 1, 20),
            failure_mode=failure_mode,
        )


class CompletionGateRegistry:
    """Thread-safe global registry for pack-owned completion gates."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._registrations: dict[str, CompletionGateRegistration] = {}

    def register(
        self,
        gate_id: str,
        handler: CompletionGateHandler,
        *,
        enabled: bool = True,
        allow_transformed_result: bool = False,
        replace: bool = False,
    ) -> CompletionGateRegistration:
        """Register a gate without coupling AgentEngine to its owning pack."""

        clean_id = _clean_gate_id(gate_id)
        if not callable(handler):
            raise CompletionGateContractError("completion gate handler must be callable")
        registration = CompletionGateRegistration(
            gate_id=clean_id,
            handler=handler,
            enabled=bool(enabled),
            allow_transformed_result=bool(allow_transformed_result),
        )
        with self._lock:
            if clean_id in self._registrations and not replace:
                raise CompletionGateContractError(
                    f"completion gate is already registered: {clean_id}"
                )
            self._registrations[clean_id] = registration
        return registration

    def unregister(self, gate_id: str) -> None:
        """Remove a gate registration."""

        with self._lock:
            self._registrations.pop(str(gate_id).strip(), None)

    def resolve(self, gate_id: str) -> CompletionGateRegistration | None:
        """Resolve a gate by stable ID."""

        with self._lock:
            return self._registrations.get(str(gate_id).strip())

    def clear(self) -> None:
        """Clear registrations; intended for isolated runtime tests."""

        with self._lock:
            self._registrations.clear()


class CompletionGateCoordinator:
    """Evaluate ordered gates while persisting bounded, idempotent state."""

    def __init__(self, registry: CompletionGateRegistry | None = None) -> None:
        self.registry = registry or get_completion_gate_registry()

    def evaluate(
        self,
        execution: Any,
        candidate: Any,
        *,
        record_event: GateEventRecorder,
        is_cancelled: CancellationCheck,
    ) -> dict[str, Any]:
        """Evaluate the attached chain and return a lifecycle action."""

        try:
            policy = CompletionGatePolicy.from_context(getattr(execution, "context", {}))
        except CompletionGateContractError as exc:
            outcome = self._terminal_policy_failure(execution, str(exc), "invalid_policy")
            outcome["candidate"] = candidate
            return outcome
        if not policy.gate_ids:
            return {"action": "pass", "candidate": candidate, "gate_ids": []}

        context = getattr(execution, "context", {})
        if not isinstance(context, dict):
            context = {}
            execution.context = context
        state = context.get("completion_gate_state")
        if not isinstance(state, dict):
            state = {}
            context["completion_gate_state"] = state
        candidate_hash = _stable_hash(candidate)
        if state.get("candidate_hash") != candidate_hash:
            state.update(
                {
                    "phase": "waiting",
                    "candidate": candidate,
                    "candidate_hash": candidate_hash,
                    "gate_index": 0,
                    "gate_ids": list(policy.gate_ids),
                    "updated_at_epoch": time.time(),
                }
            )
            state.setdefault("started_at_epoch", time.time())
            state.setdefault("iteration", 0)
            state.setdefault("attempts", {})
            state.setdefault("deliveries", {})
            state.setdefault("verdicts", [])
            state.setdefault("revision_signatures", [])

        if tuple(state.get("gate_ids") or ()) != policy.gate_ids:
            return self._terminal_policy_failure(
                execution,
                "completion gate chain changed after candidate creation",
                "chain_changed",
            )
        if len(set(policy.gate_ids)) != len(policy.gate_ids):
            return self._terminal_policy_failure(
                execution,
                "completion gate chain contains a cycle or duplicate gate ID",
                "gate_cycle",
            )
        if (
            time.time() - float(state.get("started_at_epoch") or time.time())
            > policy.max_wall_clock_seconds
        ):
            return self._terminal_policy_failure(
                execution,
                "completion gate wall-clock budget exhausted",
                "wall_clock_budget",
                policy=policy,
            )

        start_index = max(0, int(state.get("gate_index") or 0))
        current_candidate = state.get("candidate", candidate)
        for gate_index in range(start_index, len(policy.gate_ids)):
            if is_cancelled():
                state["phase"] = "cancelled"
                state["terminal_reason"] = "cancelled"
                record_event(
                    "completion_gate_cancelled",
                    {"gate_index": gate_index, "candidate_hash": candidate_hash},
                )
                return {"action": "cancelled", "candidate": current_candidate}
            gate_id = policy.gate_ids[gate_index]
            registration = self.registry.resolve(gate_id)
            if registration is None or not registration.enabled:
                reason = (
                    f"unknown completion gate: {gate_id}"
                    if registration is None
                    else f"disabled completion gate: {gate_id}"
                )
                return self._terminal_policy_failure(
                    execution,
                    reason,
                    "gate_unavailable",
                    policy=policy,
                    gate_id=gate_id,
                )

            iteration = int(state.get("iteration") or 0)
            attempt_key = f"{iteration}:{gate_id}"
            attempts = state.setdefault("attempts", {})
            prior_attempts = int(attempts.get(attempt_key) or 0)
            delivery_key = (
                f"{getattr(execution, 'execution_id', '')}:"
                f"{iteration}:{int(state.get('resume_count') or 0)}:"
                f"{gate_index}:{gate_id}:{candidate_hash}"
            )
            deliveries = state.setdefault("deliveries", {})
            cached = deliveries.get(delivery_key)
            if isinstance(cached, dict) and isinstance(cached.get("result"), dict):
                result = dict(cached["result"])
            else:
                result = self._deliver_with_retry(
                    execution,
                    current_candidate,
                    gate_id=gate_id,
                    gate_index=gate_index,
                    iteration=iteration,
                    delivery_key=delivery_key,
                    registration=registration,
                    policy=policy,
                    prior_attempts=prior_attempts,
                    attempts=attempts,
                    deliveries=deliveries,
                    record_event=record_event,
                    is_cancelled=is_cancelled,
                )

            if result.get("_delivery_error"):
                return self._terminal_policy_failure(
                    execution,
                    str(result.get("summary") or "completion gate delivery failed"),
                    str(result.get("terminal_reason") or "provider_failure"),
                    policy=policy,
                    gate_id=gate_id,
                )
            try:
                normalized = _validate_result(result, registration)
            except CompletionGateContractError as exc:
                return self._terminal_policy_failure(
                    execution,
                    str(exc),
                    "malformed_verdict",
                    policy=policy,
                    gate_id=gate_id,
                )
            if not normalized["resolved_model"]:
                normalized["resolved_model"] = str(getattr(execution, "model", "default"))
            if is_cancelled():
                state["phase"] = "cancelled"
                state["terminal_reason"] = "cancelled_after_delivery"
                record_event(
                    "completion_gate_cancelled",
                    {
                        "gate_id": gate_id,
                        "attempt": attempts.get(attempt_key),
                        "candidate_hash": candidate_hash,
                    },
                )
                return {"action": "cancelled", "candidate": current_candidate}

            verdict_record = {
                "gate_id": gate_id,
                "gate_index": gate_index,
                "iteration": iteration,
                "attempt": attempts.get(attempt_key),
                "verdict": normalized["verdict"],
                "summary": normalized["summary"],
                "evidence": normalized["evidence"],
                "instruction": normalized["instruction"],
                "resolved_model": normalized["resolved_model"],
                "metadata": normalized["metadata"],
                "idempotency_key": delivery_key,
            }
            state.setdefault("verdicts", []).append(verdict_record)
            record_event("completion_gate_verdict", verdict_record)

            if "transformed_result" in normalized:
                current_candidate = normalized["transformed_result"]
                state["candidate"] = current_candidate
                state["candidate_hash"] = _stable_hash(current_candidate)
                candidate_hash = state["candidate_hash"]
            verdict = normalized["verdict"]
            if verdict == "pass":
                state["gate_index"] = gate_index + 1
                state["updated_at_epoch"] = time.time()
                continue
            if verdict == "blocked":
                state["phase"] = "blocked"
                state["gate_index"] = gate_index
                state["pending_requirement"] = normalized["required_user_action"]
                state["terminal_reason"] = "gate_blocked"
                return {
                    "action": "blocked",
                    "candidate": current_candidate,
                    "gate_id": gate_id,
                    "summary": normalized["summary"],
                    "required_user_action": normalized["required_user_action"],
                    "evidence": normalized["evidence"],
                }

            instruction = normalized["instruction"]
            next_iteration = iteration + 1
            if next_iteration > policy.max_iterations:
                return self._terminal_policy_failure(
                    execution,
                    "completion gate iteration budget exhausted",
                    "iteration_budget",
                    policy=policy,
                    gate_id=gate_id,
                )
            signature = _stable_hash(
                {"gate_id": gate_id, "instruction": instruction.strip().lower()}
            )
            signatures = state.setdefault("revision_signatures", [])
            signatures.append(signature)
            if signatures.count(signature) >= policy.stagnation_limit:
                return self._terminal_policy_failure(
                    execution,
                    "completion gate revision stagnated",
                    "stagnation_budget",
                    policy=policy,
                    gate_id=gate_id,
                )
            state.update(
                {
                    "phase": "revising",
                    "iteration": next_iteration,
                    "gate_index": 0,
                    "revision_instruction": instruction,
                    "revision_gate_id": gate_id,
                    "pending_requirement": None,
                    "updated_at_epoch": time.time(),
                }
            )
            return {
                "action": "revise",
                "candidate": current_candidate,
                "gate_id": gate_id,
                "instruction": instruction,
                "summary": normalized["summary"],
                "evidence": normalized["evidence"],
            }

        state["phase"] = "passed"
        state["gate_index"] = len(policy.gate_ids)
        state["pending_requirement"] = None
        state["terminal_reason"] = "all_gates_passed"
        state["updated_at_epoch"] = time.time()
        return {
            "action": "pass",
            "candidate": current_candidate,
            "gate_ids": list(policy.gate_ids),
        }

    def _deliver_with_retry(
        self,
        execution: Any,
        candidate: Any,
        *,
        gate_id: str,
        gate_index: int,
        iteration: int,
        delivery_key: str,
        registration: CompletionGateRegistration,
        policy: CompletionGatePolicy,
        prior_attempts: int,
        attempts: dict[str, Any],
        deliveries: dict[str, Any],
        record_event: GateEventRecorder,
        is_cancelled: CancellationCheck,
    ) -> dict[str, Any]:
        attempt_key = f"{iteration}:{gate_id}"
        for attempt in range(prior_attempts + 1, policy.max_attempts_per_gate + 1):
            attempts[attempt_key] = attempt
            request = {
                "contract_version": "tobkiri.completion_gate.v1",
                "run_id": str(getattr(execution, "execution_id", "")),
                "gate_id": gate_id,
                "gate_index": gate_index,
                "attempt": attempt,
                "iteration": iteration,
                "idempotency_key": delivery_key,
                "candidate": candidate,
                "receipts": [
                    step.to_dict() if hasattr(step, "to_dict") else dict(step)
                    for step in list(getattr(execution, "steps", []) or [])
                ],
                "model": str(getattr(execution, "model", "default")),
                "principal": (
                    getattr(execution, "context", {}).get("principal")
                    if isinstance(getattr(execution, "context", {}), dict)
                    else None
                ),
                "resume_evidence": list(
                    (
                        getattr(execution, "context", {})
                        .get("completion_gate_state", {})
                        .get("resume_evidence", [])
                    )
                    if isinstance(getattr(execution, "context", {}), dict)
                    else []
                ),
            }
            deliveries[delivery_key] = {
                "status": "inflight",
                "attempt": attempt,
                "request_hash": _stable_hash(request),
            }
            record_event(
                "completion_gate_attempt_started",
                {
                    "gate_id": gate_id,
                    "gate_index": gate_index,
                    "attempt": attempt,
                    "iteration": iteration,
                    "idempotency_key": delivery_key,
                    "candidate": candidate,
                    "resolved_model": request["model"],
                },
            )
            if is_cancelled():
                return {
                    "_delivery_error": True,
                    "summary": "run cancelled before gate delivery",
                    "terminal_reason": "cancelled",
                }
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="completion-gate")
            future = executor.submit(registration.handler, request)
            try:
                result = future.result(timeout=policy.timeout_seconds)
            except FutureTimeoutError:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                deliveries[delivery_key] = {"status": "timeout", "attempt": attempt}
                record_event(
                    "completion_gate_delivery_failed",
                    {
                        "gate_id": gate_id,
                        "attempt": attempt,
                        "terminal_reason": "timeout",
                    },
                )
                return {
                    "_delivery_error": True,
                    "summary": f"completion gate timed out: {gate_id}",
                    "terminal_reason": "timeout",
                }
            except Exception as exc:
                executor.shutdown(wait=False, cancel_futures=True)
                deliveries[delivery_key] = {
                    "status": "provider_failure",
                    "attempt": attempt,
                    "error": str(exc),
                }
                record_event(
                    "completion_gate_delivery_failed",
                    {
                        "gate_id": gate_id,
                        "attempt": attempt,
                        "terminal_reason": "provider_failure",
                        "error": str(exc),
                    },
                )
                if attempt < policy.max_attempts_per_gate:
                    continue
                return {
                    "_delivery_error": True,
                    "summary": f"completion gate provider failed: {gate_id}",
                    "terminal_reason": "provider_failure",
                }
            else:
                executor.shutdown(wait=False, cancel_futures=True)
                if not isinstance(result, dict):
                    result = {"_malformed_raw_type": type(result).__name__}
                deliveries[delivery_key] = {
                    "status": "delivered",
                    "attempt": attempt,
                    "result": result,
                }
                return dict(result)
        return {
            "_delivery_error": True,
            "summary": f"completion gate retry budget exhausted: {gate_id}",
            "terminal_reason": "retry_budget",
        }

    @staticmethod
    def _terminal_policy_failure(
        execution: Any,
        summary: str,
        terminal_reason: str,
        *,
        policy: CompletionGatePolicy | None = None,
        gate_id: str | None = None,
    ) -> dict[str, Any]:
        context = getattr(execution, "context", {})
        state = (
            context.get("completion_gate_state")
            if isinstance(context, dict) and isinstance(context.get("completion_gate_state"), dict)
            else {}
        )
        mode = policy.failure_mode if policy is not None else "blocked"
        state["phase"] = mode
        state["terminal_reason"] = terminal_reason
        state["summary"] = summary
        action = "failed" if mode == "failed" else "blocked"
        return {
            "action": action,
            "candidate": state.get("candidate"),
            "gate_id": gate_id,
            "summary": summary,
            "terminal_reason": terminal_reason,
            "required_user_action": (
                {"type": "operator_review", "reason": summary} if action == "blocked" else None
            ),
        }


def _validate_result(
    value: dict[str, Any], registration: CompletionGateRegistration
) -> dict[str, Any]:
    if "_malformed_raw_type" in value:
        raise CompletionGateContractError(
            "completion gate result must be an object, got " + str(value["_malformed_raw_type"])
        )
    verdict = str(value.get("verdict") or "").strip().lower()
    if verdict not in {"pass", "revise", "blocked"}:
        raise CompletionGateContractError(
            "completion gate verdict must be pass, revise, or blocked"
        )
    summary = value.get("summary", "")
    instruction = value.get("instruction", "")
    evidence = value.get("evidence", [])
    metadata = value.get("metadata", {})
    required_user_action = value.get("required_user_action")
    if not isinstance(summary, str):
        raise CompletionGateContractError("completion gate summary must be a string")
    if not isinstance(instruction, str):
        raise CompletionGateContractError("completion gate instruction must be a string")
    if verdict == "revise" and not instruction.strip():
        raise CompletionGateContractError("revise verdict requires an instruction")
    if not isinstance(evidence, list):
        raise CompletionGateContractError("completion gate evidence must be a list")
    if len(evidence) > 100:
        raise CompletionGateContractError("completion gate evidence exceeds the 100-item limit")
    if not isinstance(metadata, dict):
        raise CompletionGateContractError("completion gate metadata must be an object")
    if required_user_action is not None and not isinstance(required_user_action, dict):
        raise CompletionGateContractError(
            "completion gate required_user_action must be an object or null"
        )
    if verdict == "blocked" and required_user_action is None:
        required_user_action = {"type": "operator_review", "reason": summary}
    normalized = {
        "verdict": verdict,
        "summary": summary,
        "instruction": instruction,
        "evidence": evidence,
        "required_user_action": required_user_action,
        "metadata": metadata,
        "resolved_model": str(value.get("resolved_model") or metadata.get("resolved_model") or ""),
    }
    if "transformed_result" in value:
        if not registration.allow_transformed_result:
            raise CompletionGateContractError(
                "completion gate is not allowed to transform the candidate result"
            )
        normalized["transformed_result"] = value["transformed_result"]
    return normalized


def _normalize_gate_ids(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    items = [value] if isinstance(value, (str, dict)) else value
    if not isinstance(items, (list, tuple)):
        raise CompletionGateContractError("completion_gates must be a list")
    result: list[str] = []
    for item in items:
        raw_id = item.get("id") or item.get("gate_id") if isinstance(item, dict) else item
        result.append(_clean_gate_id(raw_id))
    return tuple(result)


def _clean_gate_id(value: Any) -> str:
    gate_id = str(value or "").strip()
    if not gate_id:
        raise CompletionGateContractError("completion gate ID is required")
    if len(gate_id) > 200:
        raise CompletionGateContractError("completion gate ID is too long")
    return gate_id


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError) as exc:
        raise CompletionGateContractError("completion gate integer budget is invalid") from exc
    return max(minimum, min(parsed, maximum))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError) as exc:
        raise CompletionGateContractError("completion gate time budget is invalid") from exc
    return max(minimum, min(parsed, maximum))


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


_registry = CompletionGateRegistry()


def get_completion_gate_registry() -> CompletionGateRegistry:
    """Return the process-global completion-gate registry."""

    return _registry


def register_completion_gate(
    gate_id: str,
    handler: CompletionGateHandler,
    **kwargs: Any,
) -> CompletionGateRegistration:
    """Register a pack-owned completion gate in the global registry."""

    return _registry.register(gate_id, handler, **kwargs)
