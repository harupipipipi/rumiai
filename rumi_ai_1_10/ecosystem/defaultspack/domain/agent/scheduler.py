"""
domain/agent/scheduler.py - In-memory scheduler engine

Manages scheduled agent executions using threading.Timer.
Supports three schedule types:
  - interval: execute every N seconds/minutes/hours
  - cron: execute according to a cron expression (min hour dom month dow)
  - once: execute at a specific datetime then auto-disable

No external dependencies. Pure stdlib.
"""

import sys
import os
import threading
import time
import calendar
import math
import re
from itertools import count
from typing import Any
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import gen_id, timestamp
from domain.agent.schedule_store import (
    current_schedules_dir,
    save_schedule,
    load_schedule,
    load_all_schedules,
    delete_schedule as store_delete,
    append_history,
    load_history,
)
from domain.tool.scheduled_approval import approve_schedule_pending_approval


_APPROVAL_REQUIRED_FINISH_REASONS = {"approval_required", "authority_approval_required"}
_SCHEDULE_AUTO_APPROVAL_DEFAULT_FOLLOWUPS = 3
_SCHEDULE_AUTO_APPROVAL_MAX_FOLLOWUPS = 64
_SCHEDULE_AUTO_APPROVAL_UNLIMITED_VALUES = {"none", "null", "unlimited", "infinite", "infinity"}
_SCHEDULE_TASK_DEFAULT_TIMEOUT_SECONDS = 300.0


class _SchedulerTaskTimedOut(TimeoutError):
    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds
        super().__init__(_scheduler_timeout_error(timeout_seconds))


def _format_timeout_seconds(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _scheduler_timeout_error(timeout_seconds: float) -> str:
    return (
        "scheduled task timed out after "
        + _format_timeout_seconds(timeout_seconds)
        + " seconds"
    )


def _task_timeout_seconds(raw_value: Any) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return _SCHEDULE_TASK_DEFAULT_TIMEOUT_SECONDS
    if not math.isfinite(value) or value <= 0:
        return _SCHEDULE_TASK_DEFAULT_TIMEOUT_SECONDS
    return value


def _wait_timeout_seconds(value: float) -> float:
    max_timeout = getattr(threading, "TIMEOUT_MAX", value)
    return max(0.0, min(float(value), float(max_timeout)))


def _remaining_timeout_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _run_with_timeout(call, timeout_seconds: float, *, task_timeout_seconds: float, cancel_event=None):
    if timeout_seconds <= 0:
        if cancel_event is not None:
            cancel_event.set()
        raise _SchedulerTaskTimedOut(task_timeout_seconds)

    done = threading.Event()
    outcome: dict[str, Any] = {}

    def target():
        try:
            outcome["result"] = call()
        except BaseException as exc:
            outcome["exception"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=target, name="scheduler-task-runner", daemon=True)
    worker.start()
    if not done.wait(_wait_timeout_seconds(timeout_seconds)):
        if cancel_event is not None:
            cancel_event.set()
        raise _SchedulerTaskTimedOut(task_timeout_seconds)

    exc = outcome.get("exception")
    if exc is not None:
        if isinstance(exc, Exception):
            raise exc
        raise RuntimeError(str(exc))
    return outcome.get("result")


def _chat_result_data(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("status") != "ok":
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _chat_result_finish_reason(result: dict[str, Any] | None) -> str:
    data = _chat_result_data(result)
    return str(data.get("finish_reason") or "").strip()


def _chat_result_content(result: dict[str, Any] | None) -> str:
    data = _chat_result_data(result)
    if not data:
        return ""
    content = data.get("content", data.get("text", ""))
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("text")
        )
    if isinstance(content, str):
        return content
    return str(content)


def _pending_approval_from_chat_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    data = _chat_result_data(result)
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    pending = metadata.get("pending_approval")
    if isinstance(pending, dict):
        return pending
    events = data.get("events") if isinstance(data.get("events"), list) else []
    for event in reversed(events):
        if isinstance(event, dict) and event.get("type") == "approval_requested":
            return event
    return None


def _scheduler_trigger_name(manual: bool) -> str:
    return "manual" if manual else "scheduled"


def _scheduler_chat_payload(
    *,
    conversation_id: str,
    content: str,
    task_cfg: dict[str, Any],
    schedule_id: str,
    exec_id: str,
    trigger: str,
    params: dict[str, Any],
    tools: list[Any] | None,
    metadata_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = task_cfg.get("metadata") if isinstance(task_cfg.get("metadata"), dict) else {}
    message_metadata = {
        **metadata,
        "source": "scheduler",
        "schedule_id": schedule_id,
        "schedule_execution_id": exec_id,
        "trigger": trigger,
        "profile_id": task_cfg.get("profile_id"),
        "agent_id": task_cfg.get("agent_id"),
    }
    if isinstance(metadata_extra, dict):
        message_metadata.update(metadata_extra)
    return {
        "conversation_id": conversation_id,
        "message": {
            "role": "user",
            "content": content,
            "metadata": message_metadata,
        },
        "params": dict(params),
        "tools": tools,
    }


def _schedule_auto_approval_limit(task_cfg: dict[str, Any]) -> int | None:
    policy = task_cfg.get("tool_policy") if isinstance(task_cfg.get("tool_policy"), dict) else {}
    if "schedule_auto_approve_max_followups" not in policy:
        raw_value: Any = _SCHEDULE_AUTO_APPROVAL_DEFAULT_FOLLOWUPS
    else:
        raw_value = policy.get("schedule_auto_approve_max_followups")
        if raw_value is None:
            return None
    if isinstance(raw_value, str):
        text = raw_value.strip().lower()
        if text in _SCHEDULE_AUTO_APPROVAL_UNLIMITED_VALUES:
            return None
        if not text:
            raw_value = _SCHEDULE_AUTO_APPROVAL_DEFAULT_FOLLOWUPS
    try:
        value = int(raw_value)
    except Exception:
        value = _SCHEDULE_AUTO_APPROVAL_DEFAULT_FOLLOWUPS
    return max(0, min(value, _SCHEDULE_AUTO_APPROVAL_MAX_FOLLOWUPS))


def _schedule_auto_approval_attempts(task_cfg: dict[str, Any]):
    limit = _schedule_auto_approval_limit(task_cfg)
    if limit is None:
        return count()
    return range(limit)


def _initial_tool_choice(task_cfg: dict[str, Any]) -> Any:
    policy = task_cfg.get("tool_policy") if isinstance(task_cfg.get("tool_policy"), dict) else {}
    value = policy.get("schedule_initial_tool_choice")
    if isinstance(value, dict):
        return value
    if str(value or "").strip().lower() in {"auto", "none", "required"}:
        return str(value).strip().lower()
    return None


def _followup_params(params: dict[str, Any]) -> dict[str, Any]:
    followup = dict(params)
    followup.pop("tool_choice", None)
    return followup


def _scheduler_chat_context(task_cfg: dict[str, Any]) -> dict[str, Any]:
    policy = task_cfg.get("tool_policy") if isinstance(task_cfg.get("tool_policy"), dict) else {}
    context: dict[str, Any] = {"profile_policy": policy}
    metadata = task_cfg.get("metadata") if isinstance(task_cfg.get("metadata"), dict) else {}
    profile_id = str(task_cfg.get("profile_id") or policy.get("profile_id") or metadata.get("profile_id") or "").strip()
    company_id = str(metadata.get("company_id") or "").strip()
    if profile_id == "defaultspack.mimo_coding_company" and company_id == "mimo-coding-company":
        context["owner_pack"] = "defaultspack"
        context["source"] = "scheduler"
    return context


def _resume_scheduled_chat_approvals(
    *,
    result: dict[str, Any],
    send_chat,
    conversation_id: str,
    task_cfg: dict[str, Any],
    schedule_id: str,
    exec_id: str,
    trigger: str,
    params: dict[str, Any],
    tools: list[Any] | None,
    cancel_event=None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    auto_approvals: list[dict[str, Any]] = []
    for _idx in _schedule_auto_approval_attempts(task_cfg):
        if cancel_event is not None and cancel_event.is_set():
            break
        if _chat_result_finish_reason(result) not in _APPROVAL_REQUIRED_FINISH_REASONS:
            break
        pending = _pending_approval_from_chat_result(result)
        if not isinstance(pending, dict):
            break
        approved = approve_schedule_pending_approval(task_cfg, pending, conversation_id=conversation_id)
        if not approved:
            break
        if cancel_event is not None and cancel_event.is_set():
            break
        auto_approvals.append(approved["summary"])
        result = send_chat(
            _scheduler_chat_payload(
                conversation_id=conversation_id,
                content=(
                    "Continue the approved scheduled tool request. "
                    "Use the approved result to continue the assigned scheduled task and summarize what happened."
                ),
                task_cfg=task_cfg,
                schedule_id=schedule_id,
                exec_id=exec_id,
                trigger=trigger,
                params=_followup_params(params),
                tools=tools,
                metadata_extra={
                    "source": "scheduler_approval_followup",
                    "approval_followup": approved["followup"],
                },
            ),
            _scheduler_chat_context(task_cfg),
        )
    return result, auto_approvals


# ---------------------------------------------------------------------------
# Minimal cron expression parser (5-field: minute hour day month weekday)
# ---------------------------------------------------------------------------

def _parse_cron_field(field, min_val, max_val):
    """Parse a single cron field into a set of integers.

    Supports: *, N, N-M, N-M/S, */S, N,M,O
    """
    result = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        # Handle */N
        if part.startswith("*/"):
            step_str = part[2:]
            if not step_str.isdigit():
                raise ValueError("invalid cron step: " + part)
            step = int(step_str)
            if step < 1:
                raise ValueError("cron step must be >= 1")
            for v in range(min_val, max_val + 1, step):
                result.add(v)
            continue
        # Handle *
        if part == "*":
            for v in range(min_val, max_val + 1):
                result.add(v)
            continue
        # Handle N-M or N-M/S
        range_match = re.match(r"^(\d+)-(\d+)(?:/(\d+))?$", part)
        if range_match:
            lo = int(range_match.group(1))
            hi = int(range_match.group(2))
            step = int(range_match.group(3)) if range_match.group(3) else 1
            if lo < min_val or hi > max_val or lo > hi or step < 1:
                raise ValueError("invalid cron range: " + part)
            for v in range(lo, hi + 1, step):
                result.add(v)
            continue
        # Handle plain number
        if part.isdigit():
            v = int(part)
            if v < min_val or v > max_val:
                raise ValueError("cron value out of range: " + part)
            result.add(v)
            continue
        raise ValueError("invalid cron token: " + part)
    return result


def parse_cron_expression(expr):
    """Parse a 5-field cron expression. Returns dict with sets for each field.

    Fields: minute(0-59) hour(0-23) day(1-31) month(1-12) weekday(0-6, 0=Sun)
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError("cron expression must have exactly 5 fields, got " + str(len(parts)))
    return {
        "minute": _parse_cron_field(parts[0], 0, 59),
        "hour": _parse_cron_field(parts[1], 0, 23),
        "day": _parse_cron_field(parts[2], 1, 31),
        "month": _parse_cron_field(parts[3], 1, 12),
        "weekday": _parse_cron_field(parts[4], 0, 6),
    }


def cron_matches(parsed_cron, dt):
    """Check if a datetime matches a parsed cron expression."""
    # weekday: Python Monday=0 ... Sunday=6; cron Sunday=0
    cron_dow = (dt.weekday() + 1) % 7  # Convert Python weekday to cron weekday
    return (
        dt.minute in parsed_cron["minute"]
        and dt.hour in parsed_cron["hour"]
        and dt.day in parsed_cron["day"]
        and dt.month in parsed_cron["month"]
        and cron_dow in parsed_cron["weekday"]
    )


def next_cron_time(parsed_cron, from_dt):
    """Find the next datetime after from_dt that matches the cron expression.

    Searches up to 366 days ahead. Returns a datetime or None.
    """
    # Start from the next minute
    candidate = from_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = from_dt + timedelta(days=366)
    while candidate < limit:
        if cron_matches(parsed_cron, candidate):
            return candidate
        candidate += timedelta(minutes=1)
        # Optimisation: if current hour is not in cron hours, skip to next hour
        cron_dow = (candidate.weekday() + 1) % 7
        if candidate.month not in parsed_cron["month"]:
            # Skip to first day of next month
            if candidate.month == 12:
                candidate = candidate.replace(year=candidate.year + 1, month=1, day=1, hour=0, minute=0)
            else:
                candidate = candidate.replace(month=candidate.month + 1, day=1, hour=0, minute=0)
            continue
        if candidate.day not in parsed_cron["day"] or cron_dow not in parsed_cron["weekday"]:
            # Skip to next day
            candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if candidate.hour not in parsed_cron["hour"]:
            # Skip to next hour
            candidate = (candidate + timedelta(hours=1)).replace(minute=0)
            continue
    return None


def _interval_to_seconds(value, unit):
    """Convert an interval value+unit to seconds."""
    multipliers = {"seconds": 1, "minutes": 60, "hours": 3600}
    if unit not in multipliers:
        raise ValueError("unit must be one of: seconds, minutes, hours")
    return value * multipliers[unit]


def _parse_iso_datetime(dt_str):
    """Parse an ISO 8601 datetime string to a UTC datetime object."""
    # Handle Z suffix
    s = dt_str.replace("Z", "+00:00")
    # Python 3.7+ fromisoformat handles timezone offsets
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, AttributeError):
        # Fallback: try strptime for common formats
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(dt_str.rstrip("Z"), fmt.rstrip("%z"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        raise ValueError("cannot parse datetime: " + dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _running_execution_details(sched: dict[str, Any]) -> dict[str, Any] | None:
    running = sched.get("running_execution")
    if isinstance(running, dict):
        return running
    return None


def _running_execution_started_at(sched: dict[str, Any]) -> tuple[str | None, datetime | None]:
    running = _running_execution_details(sched) or {}
    for raw_value in (
        running.get("started_at"),
        sched.get("running_started_at"),
        running.get("created_at"),
        sched.get("updated_at"),
    ):
        if raw_value is None:
            continue
        raw_text = str(raw_value).strip()
        if not raw_text:
            continue
        try:
            return raw_text, _parse_iso_datetime(raw_text)
        except ValueError:
            continue
    return None, None


def _running_execution_timeout_seconds(sched: dict[str, Any]) -> float:
    running = _running_execution_details(sched) or {}
    task_cfg = sched.get("task") if isinstance(sched.get("task"), dict) else {}
    if running.get("timeout_seconds") is not None:
        return _task_timeout_seconds(running.get("timeout_seconds"))
    return _task_timeout_seconds(task_cfg.get("timeout", 300))


def _running_execution_trigger(sched: dict[str, Any]) -> str:
    running = _running_execution_details(sched) or {}
    trigger = str(running.get("trigger") or "").strip()
    if trigger in {"manual", "scheduled"}:
        return trigger
    return "scheduled"


def _stale_running_execution(sched: dict[str, Any], *, now_dt: datetime | None = None) -> dict[str, Any] | None:
    running = _running_execution_details(sched)
    if running is None:
        return None
    started_at, started_dt = _running_execution_started_at(sched)
    if started_dt is None:
        return None
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    timeout_seconds = _running_execution_timeout_seconds(sched)
    if (now_dt - started_dt).total_seconds() < timeout_seconds:
        return None
    execution_id = str(running.get("execution_id") or "").strip()
    if not execution_id:
        execution_id = "sexec_recovered_" + gen_id()
    return {
        "execution_id": execution_id,
        "started_at": started_at or started_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trigger": _running_execution_trigger(sched),
        "timeout_seconds": timeout_seconds,
    }


# ---------------------------------------------------------------------------
# Scheduler singleton
# ---------------------------------------------------------------------------

class Scheduler:
    """In-memory scheduler backed by threading.Timer.

    Each schedule has a corresponding Timer that fires at the next execution time.
    When the timer fires, the task is executed and the timer is re-armed for the
    next occurrence (unless the schedule type is 'once').
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialised = False
            return cls._instance

    def __init__(self):
        if self._initialised:
            return
        self._initialised = True
        self._lock = threading.Lock()
        self._timers = {}        # schedule_id -> threading.Timer
        self._schedules = {}     # schedule_id -> schedule dict (in-memory cache)
        self._conversation_locks = {}  # conversation_id -> threading.Lock
        self._active_execution_ids = set()
        self._loaded = False
        self._loaded_schedules_dir = None

    # ---- public API ----

    def ensure_loaded(self):
        """Load schedules once and keep active schedule timers armed."""
        should_load = False
        timers_to_cancel = []
        schedules_dir = current_schedules_dir()
        with self._lock:
            if self._loaded_schedules_dir != schedules_dir:
                timers_to_cancel = list(self._timers.values())
                self._timers.clear()
                self._schedules.clear()
                self._loaded = False
                self._loaded_schedules_dir = schedules_dir
            if not self._loaded:
                self._loaded = True
                should_load = True
        for timer in timers_to_cancel:
            timer.cancel()
        if should_load:
            all_scheds = load_all_schedules()
            for sd in all_scheds:
                sid = sd.get("id")
                if not sid:
                    continue
                with self._lock:
                    self._schedules[sid] = sd
        self._recover_stale_running_executions()
        self._ensure_active_timers()

    def create_schedule(self, schedule_type, task_config, schedule_config, name="", description=""):
        """Create and persist a new schedule.

        schedule_type: "interval" | "cron" | "once"
        task_config: {message, model, conversation_id, timeout}
        schedule_config: depends on type
          - interval: {value: int, unit: "seconds"|"minutes"|"hours"}
          - cron: {expression: "0 9 * * *"}
          - once: {run_at: "2025-03-01T09:00:00Z"}
        """
        self.ensure_loaded()

        # Validate schedule_type
        if schedule_type not in ("interval", "cron", "once"):
            raise ValueError("schedule_type must be one of: interval, cron, once")

        # Validate task_config
        if not isinstance(task_config, dict):
            raise ValueError("task_config must be a dict")
        if not task_config.get("message"):
            raise ValueError("task_config.message is required")

        # Validate schedule_config
        if not isinstance(schedule_config, dict):
            raise ValueError("schedule_config must be a dict")

        if schedule_type == "interval":
            val = schedule_config.get("value")
            unit = schedule_config.get("unit", "minutes")
            if not isinstance(val, (int, float)) or val <= 0:
                raise ValueError("schedule_config.value must be a positive number")
            _interval_to_seconds(val, unit)  # validates unit
        elif schedule_type == "cron":
            expr = schedule_config.get("expression")
            if not expr:
                raise ValueError("schedule_config.expression is required for cron type")
            parse_cron_expression(expr)  # validates expression
        elif schedule_type == "once":
            run_at = schedule_config.get("run_at")
            if not run_at:
                raise ValueError("schedule_config.run_at is required for once type")
            _parse_iso_datetime(run_at)  # validates datetime

        now = timestamp()
        sid = "sched_" + gen_id()

        task = {
            "message": task_config.get("message"),
            "model": task_config.get("model", "default"),
            "conversation_id": task_config.get("conversation_id"),
            "timeout": task_config.get("timeout", 300),
        }
        for key in ("profile_id", "agent_id", "tools", "tool_policy", "metadata", "thinking_level"):
            if key in task_config:
                task[key] = task_config.get(key)

        schedule = {
            "id": sid,
            "name": name if name else "Schedule " + sid[:12],
            "description": description,
            "type": schedule_type,
            "task": task,
            "config": schedule_config,
            "status": "active",
            "execution_count": 0,
            "last_executed_at": None,
            "next_execution_at": None,
            "created_at": now,
            "updated_at": now,
        }

        # Compute next execution time
        schedule["next_execution_at"] = self._compute_next_execution(schedule)

        save_schedule(schedule)
        with self._lock:
            self._schedules[sid] = schedule

        self._arm_timer(sid)
        return schedule

    def get_schedule(self, schedule_id):
        """Return a schedule dict or None."""
        self.ensure_loaded()
        with self._lock:
            return self._schedules.get(schedule_id)

    def list_schedules(self, status_filter=None):
        """Return list of all schedules, optionally filtered by status."""
        self.ensure_loaded()
        with self._lock:
            all_s = list(self._schedules.values())
        if status_filter:
            all_s = [s for s in all_s if s.get("status") == status_filter]
        all_s.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return all_s

    def update_schedule(self, schedule_id, updates):
        """Update a schedule. Allowed fields: name, description, task, config, type.

        Returns the updated schedule dict or None if not found.
        """
        self.ensure_loaded()
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None:
            return None

        allowed_keys = ("name", "description", "task", "config", "type")
        changed = False
        for key in allowed_keys:
            if key in updates:
                if key == "type":
                    if updates[key] not in ("interval", "cron", "once"):
                        raise ValueError("type must be one of: interval, cron, once")
                if key == "config":
                    # Re-validate config based on type
                    stype = updates.get("type", sched.get("type"))
                    cfg = updates["config"]
                    if stype == "interval":
                        val = cfg.get("value")
                        unit = cfg.get("unit", "minutes")
                        if not isinstance(val, (int, float)) or val <= 0:
                            raise ValueError("config.value must be a positive number")
                        _interval_to_seconds(val, unit)
                    elif stype == "cron":
                        expr = cfg.get("expression")
                        if not expr:
                            raise ValueError("config.expression is required for cron type")
                        parse_cron_expression(expr)
                    elif stype == "once":
                        run_at = cfg.get("run_at")
                        if not run_at:
                            raise ValueError("config.run_at is required for once type")
                        _parse_iso_datetime(run_at)
                if key == "task":
                    if not isinstance(updates["task"], dict):
                        raise ValueError("task must be a dict")
                    # Merge with existing task
                    merged_task = dict(sched.get("task", {}))
                    merged_task.update(updates["task"])
                    if not merged_task.get("message"):
                        raise ValueError("task.message cannot be empty")
                    sched["task"] = merged_task
                    changed = True
                    continue
                sched[key] = updates[key]
                changed = True

        if changed:
            sched["updated_at"] = timestamp()
            if sched.get("status") == "active":
                sched["next_execution_at"] = self._compute_next_execution(sched)
            save_schedule(sched)
            with self._lock:
                self._schedules[schedule_id] = sched
            if sched.get("status") == "active":
                self._cancel_timer(schedule_id)
                self._arm_timer(schedule_id)

        return sched

    def delete_schedule(self, schedule_id):
        """Delete a schedule. Returns True if deleted."""
        self.ensure_loaded()
        self._cancel_timer(schedule_id)
        with self._lock:
            removed = self._schedules.pop(schedule_id, None)
        store_delete(schedule_id)
        return removed is not None

    def pause_schedule(self, schedule_id):
        """Pause an active schedule. Returns updated schedule or None."""
        self.ensure_loaded()
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None:
            return None
        if sched.get("status") != "active":
            return sched  # already not active
        self._cancel_timer(schedule_id)
        sched["status"] = "paused"
        sched["next_execution_at"] = None
        sched["updated_at"] = timestamp()
        save_schedule(sched)
        with self._lock:
            self._schedules[schedule_id] = sched
        return sched

    def resume_schedule(self, schedule_id):
        """Resume a paused schedule. Returns updated schedule or None."""
        self.ensure_loaded()
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None:
            return None
        if sched.get("status") == "active":
            return sched  # already active
        if sched.get("status") == "completed":
            return sched  # once-type that already ran, cannot resume
        sched["status"] = "active"
        sched["next_execution_at"] = self._compute_next_execution(sched)
        sched["updated_at"] = timestamp()
        save_schedule(sched)
        with self._lock:
            self._schedules[schedule_id] = sched
        self._arm_timer(schedule_id)
        return sched

    def trigger_now(self, schedule_id):
        """Manually trigger a schedule execution immediately.

        Returns execution history entry.
        """
        self.ensure_loaded()
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None:
            return None
        return self._execute_task(schedule_id, manual=True)

    def get_history(self, schedule_id, limit=50, offset=0):
        """Return execution history for a schedule."""
        self.ensure_loaded()
        entries, total = load_history(schedule_id, limit=limit, offset=offset)
        return {"entries": entries, "total": total, "limit": limit, "offset": offset}

    # ---- internal ----

    def _compute_next_execution(self, sched):
        """Compute the ISO timestamp of the next execution."""
        stype = sched.get("type")
        cfg = sched.get("config", {})
        now = datetime.now(timezone.utc)

        if stype == "interval":
            val = cfg.get("value", 60)
            unit = cfg.get("unit", "minutes")
            secs = _interval_to_seconds(val, unit)
            nxt = now + timedelta(seconds=secs)
            return nxt.strftime("%Y-%m-%dT%H:%M:%SZ")

        if stype == "cron":
            expr = cfg.get("expression", "* * * * *")
            parsed = parse_cron_expression(expr)
            nxt = next_cron_time(parsed, now)
            if nxt is None:
                return None
            return nxt.strftime("%Y-%m-%dT%H:%M:%SZ")

        if stype == "once":
            run_at = cfg.get("run_at")
            if not run_at:
                return None
            dt = _parse_iso_datetime(run_at)
            if dt <= now:
                return None  # already past
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        return None

    def _seconds_until_next(self, sched):
        """Return seconds until the next scheduled execution, or None."""
        nxt_str = sched.get("next_execution_at")
        if not nxt_str:
            return None
        try:
            nxt = _parse_iso_datetime(nxt_str)
        except ValueError:
            return None
        now = datetime.now(timezone.utc)
        delta = (nxt - now).total_seconds()
        if delta < 0:
            return 0.1  # fire immediately if overdue
        return max(delta, 0.1)

    def _arm_timer(self, schedule_id):
        """Set a threading.Timer for the next execution of a schedule."""
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None or sched.get("status") != "active":
            return
        delay = self._seconds_until_next(sched)
        if delay is None:
            return
        # Cap very long delays at 1 hour and re-check then
        max_delay = 3600.0
        if delay > max_delay:
            timer = threading.Timer(max_delay, self._recheck_and_arm, args=[schedule_id])
        else:
            timer = threading.Timer(delay, self._on_timer_fire, args=[schedule_id])
        timer.daemon = True
        with self._lock:
            old = self._timers.pop(schedule_id, None)
            if old is not None:
                old.cancel()
            self._timers[schedule_id] = timer
        timer.start()

    def _timer_needs_arm(self, schedule_id):
        with self._lock:
            timer = self._timers.get(schedule_id)
        if timer is None:
            return True
        is_alive = getattr(timer, "is_alive", None)
        if not callable(is_alive):
            return False
        return not is_alive()

    def _recover_stale_running_executions(self):
        with self._lock:
            schedule_ids = list(self._schedules.keys())
        for schedule_id in schedule_ids:
            self._recover_stale_running_execution(schedule_id)

    def _recover_stale_running_execution(self, schedule_id):
        with self._lock:
            sched = self._schedules.get(schedule_id)
            if sched is None:
                return False
            stale = _stale_running_execution(sched)
            if stale is None:
                return False
            if stale["execution_id"] in self._active_execution_ids:
                return False
            self._active_execution_ids.add(stale["execution_id"])

        try:
            completed_at = timestamp()
            history_entry = {
                "execution_id": stale["execution_id"],
                "schedule_id": schedule_id,
                "started_at": stale["started_at"],
                "completed_at": completed_at,
                "status": "error",
                "trigger": stale["trigger"],
                "result": None,
                "error": _scheduler_timeout_error(stale["timeout_seconds"]),
                "timeout_seconds": stale["timeout_seconds"],
                "recovered_stale_running_execution": True,
            }
            append_history(schedule_id, history_entry)

            with self._lock:
                sched = self._schedules.get(schedule_id)
                if sched is None:
                    return True
                current = _running_execution_details(sched)
                if isinstance(current, dict):
                    current_execution_id = str(current.get("execution_id") or "").strip()
                    if current_execution_id and current_execution_id != stale["execution_id"]:
                        return True
                sched.pop("running_execution", None)
                sched.pop("running_started_at", None)
                try:
                    execution_count = int(sched.get("execution_count", 0))
                except (TypeError, ValueError):
                    execution_count = 0
                sched["execution_count"] = execution_count + 1
                sched["last_executed_at"] = completed_at
                if stale["trigger"] != "manual":
                    if sched.get("type") == "once":
                        sched["status"] = "completed"
                        sched["next_execution_at"] = None
                    elif sched.get("status") == "active":
                        sched["next_execution_at"] = self._compute_next_execution(sched)
                sched["updated_at"] = timestamp()
                save_schedule(sched)
                self._schedules[schedule_id] = sched
            return True
        finally:
            with self._lock:
                self._active_execution_ids.discard(stale["execution_id"])

    def _ensure_active_timers(self):
        with self._lock:
            active_ids = [
                sid
                for sid, sched in self._schedules.items()
                if sched.get("status") == "active"
            ]
            inactive_ids = [
                sid
                for sid, sched in self._schedules.items()
                if sched.get("status") != "active"
            ]

        for schedule_id in inactive_ids:
            self._cancel_timer(schedule_id)
        for schedule_id in active_ids:
            if self._timer_needs_arm(schedule_id):
                self._arm_timer(schedule_id)

    def _recheck_and_arm(self, schedule_id):
        """Called when delay was capped; re-compute and re-arm."""
        self._recover_stale_running_execution(schedule_id)
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None or sched.get("status") != "active":
            return
        self._arm_timer(schedule_id)

    def _cancel_timer(self, schedule_id):
        """Cancel any running timer for a schedule."""
        with self._lock:
            timer = self._timers.pop(schedule_id, None)
        if timer is not None:
            timer.cancel()

    def _mark_schedule_running(self, schedule_id, execution_id, started_at, trigger, timeout_seconds):
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None:
            return
        sched["running_execution"] = {
            "execution_id": execution_id,
            "schedule_id": schedule_id,
            "started_at": started_at,
            "trigger": trigger,
            "timeout_seconds": timeout_seconds,
        }
        sched["running_started_at"] = started_at
        sched["updated_at"] = timestamp()
        save_schedule(sched)
        with self._lock:
            self._schedules[schedule_id] = sched

    def _conversation_execution_lock(self, conversation_id):
        key = str(conversation_id or "").strip()
        if not key:
            return None
        with self._lock:
            lock = self._conversation_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._conversation_locks[key] = lock
            return lock

    def _on_timer_fire(self, schedule_id):
        """Called when a timer fires. Execute the task and re-arm."""
        self._recover_stale_running_execution(schedule_id)
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None or sched.get("status") != "active":
            return
        self._execute_task(schedule_id, manual=False)
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None or sched.get("status") != "active" or not sched.get("next_execution_at"):
            return
        if sched.get("type") != "once":
            self._arm_timer(schedule_id)

    def _execute_task(self, schedule_id, manual=False):
        """Execute the agent task for a schedule and record history."""
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is None:
            return None

        task_cfg = sched.get("task", {})
        message = task_cfg.get("message", "")
        model = task_cfg.get("model", "default")
        timeout_seconds = _task_timeout_seconds(task_cfg.get("timeout", 300))
        conversation_id = task_cfg.get("conversation_id")

        exec_id = "sexec_" + gen_id()
        started_at = timestamp()
        deadline = time.monotonic() + timeout_seconds
        cancel_event = threading.Event()

        history_entry = {
            "execution_id": exec_id,
            "schedule_id": schedule_id,
            "started_at": started_at,
            "completed_at": None,
            "status": "running",
            "trigger": "manual" if manual else "scheduled",
            "result": None,
            "error": None,
        }
        auto_approvals = []
        trigger = _scheduler_trigger_name(manual)
        with self._lock:
            self._active_execution_ids.add(exec_id)
        self._mark_schedule_running(schedule_id, exec_id, started_at, trigger, timeout_seconds)

        try:
            if conversation_id:
                conversation_lock = self._conversation_execution_lock(conversation_id)
                if conversation_lock is None:
                    raise ValueError("task.conversation_id cannot be blank")
                lock_timeout = _remaining_timeout_seconds(deadline)
                if not conversation_lock.acquire(timeout=_wait_timeout_seconds(lock_timeout)):
                    cancel_event.set()
                    raise _SchedulerTaskTimedOut(timeout_seconds)
                try:
                    from blocks.chat.send import run as chat_send_run

                    params = {}
                    if task_cfg.get("model"):
                        params["model"] = task_cfg.get("model")
                    if isinstance(task_cfg.get("tool_policy"), dict):
                        params["tool_policy"] = task_cfg["tool_policy"]
                    if task_cfg.get("thinking_level"):
                        params["thinking_level"] = task_cfg.get("thinking_level")
                    tools = task_cfg.get("tools") if isinstance(task_cfg.get("tools"), list) else None
                    if tools and "tool_choice" not in params:
                        initial_tool_choice = _initial_tool_choice(task_cfg)
                        if initial_tool_choice is not None:
                            params["tool_choice"] = initial_tool_choice

                    def run_chat_task():
                        chat_result = chat_send_run(
                            _scheduler_chat_payload(
                                conversation_id=conversation_id,
                                content=message,
                                task_cfg=task_cfg,
                                schedule_id=schedule_id,
                                exec_id=exec_id,
                                trigger=trigger,
                                params=params,
                                tools=tools,
                            ),
                            _scheduler_chat_context(task_cfg),
                        )
                        return _resume_scheduled_chat_approvals(
                            result=chat_result,
                            send_chat=chat_send_run,
                            conversation_id=conversation_id,
                            task_cfg=task_cfg,
                            schedule_id=schedule_id,
                            exec_id=exec_id,
                            trigger=trigger,
                            params=params,
                            tools=tools,
                            cancel_event=cancel_event,
                        )

                    result, auto_approvals = _run_with_timeout(
                        run_chat_task,
                        _remaining_timeout_seconds(deadline),
                        task_timeout_seconds=timeout_seconds,
                        cancel_event=cancel_event,
                    )
                finally:
                    conversation_lock.release()
            else:
                from blocks.ai.complete import run as ai_complete_run

                messages = []
                system_content = (
                    "You are a scheduled agent. Execute the following task. "
                    "Be concise and precise in your response."
                )
                messages.append({"role": "system", "content": system_content})
                messages.append({"role": "user", "content": message})

                empty_context = {}

                def run_completion_task():
                    return ai_complete_run({"messages": messages, "model": model}, empty_context)

                result = _run_with_timeout(
                    run_completion_task,
                    _remaining_timeout_seconds(deadline),
                    task_timeout_seconds=timeout_seconds,
                    cancel_event=cancel_event,
                )

            if result.get("status") == "ok":
                data = result.get("data", {})
                if isinstance(data, dict):
                    content = _chat_result_content(result)
                    finish_reason = _chat_result_finish_reason(result)
                elif isinstance(data, str):
                    content = data
                    finish_reason = ""
                else:
                    content = str(data)
                    finish_reason = ""
                if finish_reason in _APPROVAL_REQUIRED_FINISH_REASONS:
                    content = (finish_reason + "\n" + content).strip()
                    history_entry["status"] = finish_reason
                else:
                    history_entry["status"] = "completed"
                history_entry["result"] = content
                if finish_reason:
                    history_entry["finish_reason"] = finish_reason
                if auto_approvals:
                    history_entry["auto_approvals"] = auto_approvals
            else:
                err = result.get("error", {})
                if isinstance(err, dict):
                    err_msg = err.get("message", str(err))
                else:
                    err_msg = str(err)
                history_entry["status"] = "error"
                history_entry["error"] = err_msg

        except Exception as exc:
            history_entry["status"] = "error"
            history_entry["error"] = str(exc)
            if isinstance(exc, _SchedulerTaskTimedOut):
                history_entry["timeout_seconds"] = exc.timeout_seconds

        history_entry["completed_at"] = timestamp()
        append_history(schedule_id, history_entry)

        # Update schedule metadata
        with self._lock:
            sched = self._schedules.get(schedule_id)
        if sched is not None:
            sched.pop("running_execution", None)
            sched.pop("running_started_at", None)
            sched["execution_count"] = sched.get("execution_count", 0) + 1
            sched["last_executed_at"] = history_entry["completed_at"]
            if not manual:
                if sched.get("type") == "once":
                    sched["status"] = "completed"
                    sched["next_execution_at"] = None
                elif sched.get("status") == "active":
                    sched["next_execution_at"] = self._compute_next_execution(sched)
            sched["updated_at"] = timestamp()
            save_schedule(sched)
            with self._lock:
                self._schedules[schedule_id] = sched

        with self._lock:
            self._active_execution_ids.discard(exec_id)
        return history_entry

    def shutdown(self):
        """Cancel all timers. Called on process exit."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
