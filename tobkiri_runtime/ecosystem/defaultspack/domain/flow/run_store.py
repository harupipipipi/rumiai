"""Durable execution records for declarative Tobkiri flows."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


_TERMINAL_STATUSES = {"completed", "cancelled", "failed"}
_RESUMABLE_STATUSES = {"paused", "waiting_approval", "failed"}


def default_flow_run_store_path() -> Path:
    """Return the host-owned flow run database path."""

    override = os.environ.get("RUMI_DEFAULTSPACK_FLOW_RUN_STORE", "").strip()
    if override:
        return Path(override)
    return (
        Path(__file__).resolve().parents[2]
        / "user_data"
        / "shared"
        / "flow_runs.json"
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_safe(value: Any) -> Any:
    """Copy JSON-compatible state without persisting callbacks or secrets."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if callable(item) or any(
                marker in text_key.lower()
                for marker in (
                    "api_key",
                    "approval_token",
                    "authorization",
                    "credential",
                    "password",
                    "secret",
                )
            ):
                continue
            result[text_key] = _json_safe(item)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value if not callable(item)]
    return str(value)


class FlowRunStore:
    """Atomic JSON store for flow state, checkpoints, events, and control flags."""

    _process_lock = threading.RLock()

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_flow_run_store_path()
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    def create(
        self,
        *,
        flow_id: str,
        trigger_input: dict[str, Any],
        execution_id: str | None = None,
        trace_id: str | None = None,
        budgets: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create and persist a new running flow record."""

        now = _now_ms()
        run_id = str(execution_id or f"flow-{uuid.uuid4().hex}")
        record = {
            "schema_version": 1,
            "run_id": run_id,
            "trace_id": str(trace_id or run_id),
            "flow_id": str(flow_id),
            "status": "running",
            "phase": "starting",
            "iteration": 0,
            "trigger_input": _json_safe(trigger_input),
            "values": {},
            "outputs": {},
            "completed_steps": [],
            "checkpoints": [],
            "events": [],
            "receipts": {},
            "budget": {
                "max_tokens": 0,
                "max_cost_usd": 0.0,
                "timeout_seconds": 0,
                "used_tokens": 0,
                "used_cost_usd": 0.0,
                **_json_safe(budgets or {}),
            },
            "control": {
                "cancel_requested": False,
                "pause_requested": False,
                "retry_from_phase": "",
            },
            "stop_reason": "",
            "loop_break_reason": "",
            "created_at": now,
            "updated_at": now,
            "started_at": now,
            "completed_at": None,
            "metadata": _json_safe(metadata or {}),
        }

        def update(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            runs = data.setdefault("runs", {})
            if not isinstance(runs, dict):
                runs = {}
                data["runs"] = runs
            if run_id in runs:
                raise ValueError(f"flow run already exists: {run_id}")
            runs[run_id] = record
            data["schema_version"] = 1
            return data, deepcopy(record)

        return self._update(update)

    def get(self, run_id: str) -> dict[str, Any] | None:
        """Return a copy of one run record."""

        data = self._read()
        runs = data.get("runs") if isinstance(data.get("runs"), dict) else {}
        record = runs.get(str(run_id))
        return deepcopy(record) if isinstance(record, dict) else None

    def list(self, *, flow_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        """List newest run records, optionally filtered by flow id."""

        data = self._read()
        runs = data.get("runs") if isinstance(data.get("runs"), dict) else {}
        records = [
            deepcopy(record)
            for record in runs.values()
            if isinstance(record, dict)
            and (not flow_id or str(record.get("flow_id")) == str(flow_id))
        ]
        records.sort(key=lambda item: int(item.get("updated_at") or 0), reverse=True)
        return records[: max(1, min(int(limit or 100), 1000))]

    def resume(self, run_id: str) -> dict[str, Any]:
        """Clear pause/failure control state and resume a durable run."""

        def mutate(record: dict[str, Any]) -> None:
            status = str(record.get("status") or "")
            if status == "cancelled":
                raise ValueError("cancelled flow runs cannot be resumed")
            if status == "completed":
                raise ValueError("completed flow runs do not need resume")
            control = record.setdefault("control", {})
            control["pause_requested"] = False
            control["cancel_requested"] = False
            record["status"] = "running"
            record["stop_reason"] = ""
            record["resumed_at"] = _now_ms()

        return self._mutate_run(run_id, mutate)

    def request_cancel(self, run_id: str, *, reason: str = "user_cancel") -> dict[str, Any]:
        """Persist a cancellation request visible to running workers."""

        def mutate(record: dict[str, Any]) -> None:
            control = record.setdefault("control", {})
            control["cancel_requested"] = True
            record["stop_reason"] = str(reason or "user_cancel")
            if str(record.get("status") or "") in _RESUMABLE_STATUSES:
                record["status"] = "cancelled"
                record["completed_at"] = _now_ms()

        return self._mutate_run(run_id, mutate)

    def request_pause(self, run_id: str, *, reason: str = "user_pause") -> dict[str, Any]:
        """Persist a pause request visible at the next checkpoint boundary."""

        def mutate(record: dict[str, Any]) -> None:
            control = record.setdefault("control", {})
            control["pause_requested"] = True
            record["stop_reason"] = str(reason or "user_pause")

        return self._mutate_run(run_id, mutate)

    def prepare_retry(self, run_id: str, phase: str) -> dict[str, Any]:
        """Discard checkpoints from ``phase`` onward and prepare a deterministic retry."""

        phase = str(phase or "").strip()
        if not phase:
            raise ValueError("retry phase is required")

        def mutate(record: dict[str, Any]) -> None:
            checkpoints = [
                item
                for item in record.get("checkpoints", [])
                if isinstance(item, dict)
            ]
            boundary = next(
                (
                    index
                    for index, item in enumerate(checkpoints)
                    if str(item.get("phase") or item.get("step_id") or "") == phase
                ),
                None,
            )
            if boundary is None:
                raise ValueError(f"flow phase not found in checkpoints: {phase}")
            retained = checkpoints[:boundary]
            record["checkpoints"] = retained
            last = retained[-1] if retained else {}
            record["values"] = deepcopy(last.get("values") or {})
            record["outputs"] = deepcopy(last.get("outputs") or {})
            record["completed_steps"] = [
                str(item.get("step_id"))
                for item in retained
                if str(item.get("step_id") or "")
                and int(item.get("iteration") or 0) == 0
            ]
            retained_steps = set(record["completed_steps"])
            receipts = (
                record.get("receipts")
                if isinstance(record.get("receipts"), dict)
                else {}
            )
            record["receipts"] = {
                key: value
                for key, value in receipts.items()
                if len(str(key).rsplit(":", 2)) >= 2
                and str(key).rsplit(":", 2)[-2] in retained_steps
            }
            record["phase"] = phase
            record["iteration"] = 0
            record["status"] = "running"
            record["stop_reason"] = ""
            control = record.setdefault("control", {})
            control["retry_from_phase"] = phase
            control["cancel_requested"] = False
            control["pause_requested"] = False

        return self._mutate_run(run_id, mutate)

    def checkpoint(
        self,
        run_id: str,
        *,
        phase: str,
        step_id: str,
        values: dict[str, Any],
        outputs: dict[str, Any],
        iteration: int = 0,
        event: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Atomically persist one completed phase or loop iteration."""

        safe_values = _json_safe(values)
        safe_outputs = _json_safe(outputs)
        safe_event = _json_safe(event or {})
        safe_usage = _json_safe(usage or {})

        def mutate(record: dict[str, Any]) -> None:
            now = _now_ms()
            record["phase"] = str(phase or step_id)
            record["iteration"] = max(0, int(iteration or 0))
            record["values"] = safe_values
            record["outputs"] = safe_outputs
            completed = record.setdefault("completed_steps", [])
            if iteration == 0 and step_id and step_id not in completed:
                completed.append(step_id)
            checkpoint = {
                "checkpoint_id": f"ckpt-{uuid.uuid4().hex}",
                "phase": str(phase or step_id),
                "step_id": str(step_id),
                "iteration": max(0, int(iteration or 0)),
                "values": safe_values,
                "outputs": safe_outputs,
                "created_at": now,
            }
            record.setdefault("checkpoints", []).append(checkpoint)
            if safe_event:
                record.setdefault("events", []).append(
                    {"timestamp": now, **safe_event}
                )
            self._apply_usage(record, safe_usage)
            control = record.setdefault("control", {})
            if control.get("cancel_requested"):
                record["status"] = "cancelled"
                record["completed_at"] = now
            elif control.get("pause_requested"):
                record["status"] = "paused"

        return self._mutate_run(run_id, mutate)

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        """Append a public, redacted flow event."""

        safe_event = _json_safe(event)

        def mutate(record: dict[str, Any]) -> None:
            record.setdefault("events", []).append(
                {"timestamp": _now_ms(), **safe_event}
            )
            record["events"] = record["events"][-4000:]

        return self._mutate_run(run_id, mutate)

    def record_receipt(
        self,
        run_id: str,
        *,
        receipt_key: str,
        result: Any,
    ) -> dict[str, Any]:
        """Record an exactly-once function/tool result for resume safety."""

        safe_result = _json_safe(result)

        def mutate(record: dict[str, Any]) -> None:
            record.setdefault("receipts", {})[str(receipt_key)] = {
                "result": safe_result,
                "created_at": _now_ms(),
            }

        return self._mutate_run(run_id, mutate)

    def receipt(self, run_id: str, receipt_key: str) -> Any:
        """Return a previously recorded exactly-once result."""

        record = self.get(run_id) or {}
        receipts = record.get("receipts") if isinstance(record.get("receipts"), dict) else {}
        receipt = receipts.get(str(receipt_key))
        return deepcopy(receipt.get("result")) if isinstance(receipt, dict) else None

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        stop_reason: str = "",
        loop_break_reason: str = "",
        result: Any = None,
    ) -> dict[str, Any]:
        """Mark a run terminal or resumably paused."""

        normalized = str(status or "failed")
        if normalized not in {
            "completed",
            "cancelled",
            "failed",
            "paused",
            "waiting_approval",
        }:
            normalized = "failed"

        def mutate(record: dict[str, Any]) -> None:
            record["status"] = normalized
            record["stop_reason"] = str(stop_reason or "")
            record["loop_break_reason"] = str(loop_break_reason or "")
            if result is not None:
                record["result"] = _json_safe(result)
            if normalized in _TERMINAL_STATUSES:
                record["completed_at"] = _now_ms()

        return self._mutate_run(run_id, mutate)

    def control_state(self, run_id: str) -> dict[str, Any]:
        """Return cancellation, pause, timeout, and budget state."""

        record = self.get(run_id) or {}
        control = dict(record.get("control") or {})
        budget = dict(record.get("budget") or {})
        started_at = int(record.get("started_at") or 0)
        timeout_seconds = float(budget.get("timeout_seconds") or 0)
        timed_out = bool(
            timeout_seconds > 0
            and started_at > 0
            and _now_ms() - started_at >= timeout_seconds * 1000
        )
        max_tokens = int(budget.get("max_tokens") or 0)
        max_cost = float(budget.get("max_cost_usd") or 0)
        return {
            **control,
            "timed_out": timed_out,
            "token_budget_exhausted": bool(
                max_tokens > 0 and int(budget.get("used_tokens") or 0) >= max_tokens
            ),
            "cost_budget_exhausted": bool(
                max_cost > 0
                and float(budget.get("used_cost_usd") or 0) >= max_cost
            ),
        }

    @staticmethod
    def _apply_usage(record: dict[str, Any], usage: dict[str, Any]) -> None:
        budget = record.setdefault("budget", {})
        tokens = int(
            usage.get("total_tokens")
            or usage.get("tokens")
            or (
                int(usage.get("input_tokens") or 0)
                + int(usage.get("output_tokens") or 0)
            )
            or 0
        )
        cost = float(usage.get("cost_usd") or usage.get("total_cost_usd") or 0)
        budget["used_tokens"] = int(budget.get("used_tokens") or 0) + tokens
        budget["used_cost_usd"] = round(
            float(budget.get("used_cost_usd") or 0) + cost,
            12,
        )

    def _mutate_run(
        self,
        run_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        run_id = str(run_id)

        def update(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            runs = data.setdefault("runs", {})
            if not isinstance(runs, dict) or not isinstance(runs.get(run_id), dict):
                raise KeyError(f"flow run not found: {run_id}")
            record = runs[run_id]
            callback(record)
            record["updated_at"] = _now_ms()
            return data, deepcopy(record)

        return self._update(update)

    def _read(self) -> dict[str, Any]:
        with self._process_lock:
            with self._file_lock():
                return self._read_unlocked()

    def _update(
        self,
        callback: Callable[
            [dict[str, Any]],
            tuple[dict[str, Any], dict[str, Any]],
        ],
    ) -> dict[str, Any]:
        with self._process_lock:
            with self._file_lock():
                data = self._read_unlocked()
                next_data, result = callback(data)
                self._write_unlocked(next_data)
                return result

    @contextmanager
    def _file_lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            self._lock_handle(handle)
            try:
                yield
            finally:
                self._unlock_handle(handle)

    def _read_unlocked(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"schema_version": 1, "runs": {}}
        return raw if isinstance(raw, dict) else {"schema_version": 1, "runs": {}}

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(self.path)

    @staticmethod
    def _lock_handle(handle) -> None:
        if os.name == "nt":
            try:
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            except (ImportError, OSError):
                return
            return
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            return

    @staticmethod
    def _unlock_handle(handle) -> None:
        if os.name == "nt":
            try:
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except (ImportError, OSError):
                return
            return
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            return
