"""Bounded, secret-free diagnostic audit events for ComputerSeat.

This JSONL sink is intentionally secondary to the broker audit.  It records
only fixed operational facts for local diagnosis and must never be used as an
approval, authorization, or execution record.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_OUTPUT_FIELDS = frozenset(
    {
        "timestamp_ms",
        "action",
        "driver",
        "approval_required",
        "target_app_present",
        "target_bundle_present",
        "target_pid_present",
        "target_window_present",
        "executed",
        "result_ok",
        "is_fallback",
        "can_parallel_user_work",
        "requires_foreground",
        "uses_physical_input",
    }
)


@dataclass(frozen=True)
class AuditEntry:
    """A fixed, scalar-only ComputerSeat diagnostic event.

    Target identifiers, element identifiers, payloads, results, errors, and
    content are deliberately absent.  Presence flags retain enough context to
    diagnose routing without recording user or application data.
    """

    timestamp_ms: int
    action: str
    driver: str
    approval_required: bool
    target_app_present: bool
    target_bundle_present: bool
    target_pid_present: bool
    target_window_present: bool
    executed: bool
    result_ok: bool
    is_fallback: bool
    can_parallel_user_work: bool
    requires_foreground: bool
    uses_physical_input: bool


def target_audit_facts(target: Any) -> dict[str, bool]:
    """Return only target-presence facts; never return target identifiers."""
    return {
        "target_app_present": bool(
            _field(target, "app") or _field(target, "application") or _field(target, "target_app")
        ),
        "target_bundle_present": bool(_field(target, "bundle_id")),
        "target_pid_present": _field(target, "pid") not in (None, ""),
        "target_window_present": bool(
            _field(target, "window_id") not in (None, "")
            or _field(target, "hwnd") not in (None, "")
            or _field(target, "window_title")
            or _field(target, "title")
        ),
    }


def result_audit_facts(result: Any) -> dict[str, bool]:
    """Extract fixed result facts without traversing result payloads."""
    executed = _field(result, "executed") is True
    return {
        "executed": executed,
        "result_ok": executed,
        "is_fallback": _field(result, "is_fallback") is True,
        "can_parallel_user_work": _field(result, "can_parallel_user_work") is True,
        "requires_foreground": _field(result, "requires_foreground") is True,
        "uses_physical_input": _field(result, "uses_physical_input") is True,
    }


class AuditLogger:
    """Append fixed, scalar-only JSONL diagnostics for ComputerSeat actions.

    The broker audit remains the authoritative record for ComputerSeat
    operations.  This best-effort sink intentionally cannot carry enough
    information to authorize, replay, or reconstruct an action.
    """

    def __init__(self, log_path: str | Path | None = None) -> None:
        """Initialize the diagnostic logger.

        Args:
            log_path: Path to the diagnostic JSONL file. Defaults to
                ``~/.rumi/computer_seat_audit.jsonl``.
        """
        if log_path is None:
            log_dir = Path.home() / ".rumi"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "computer_seat_audit.jsonl"
        self._log_path = Path(log_path)

    @property
    def log_path(self) -> Path:
        """Return the path to the diagnostic log file."""
        return self._log_path

    def record(
        self,
        action: str,
        driver: str = "",
        *,
        approval_required: bool = False,
        target_app_present: bool = False,
        target_bundle_present: bool = False,
        target_pid_present: bool = False,
        target_window_present: bool = False,
        executed: bool = False,
        result_ok: bool = False,
        is_fallback: bool = False,
        can_parallel_user_work: bool = False,
        requires_foreground: bool = False,
        uses_physical_input: bool = False,
    ) -> AuditEntry:
        """Record a fixed, non-content diagnostic event.

        This method accepts no arbitrary mapping, target identifier, element,
        payload, intent, or result object.  Callers must derive the explicit
        facts above before reaching the diagnostic boundary.
        """
        entry = AuditEntry(
            timestamp_ms=int(time.time() * 1000),
            action=_safe_token(action, fallback="unknown"),
            driver=_safe_token(driver, fallback="unknown"),
            approval_required=approval_required is True,
            target_app_present=target_app_present is True,
            target_bundle_present=target_bundle_present is True,
            target_pid_present=target_pid_present is True,
            target_window_present=target_window_present is True,
            executed=executed is True,
            result_ok=result_ok is True,
            is_fallback=is_fallback is True,
            can_parallel_user_work=can_parallel_user_work is True,
            requires_foreground=requires_foreground is True,
            uses_physical_input=uses_physical_input is True,
        )
        self._write(entry)
        return entry

    def _write(self, entry: AuditEntry) -> None:
        """Append an event to an owner-only JSONL file, best effort."""
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self._log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.fchmod(descriptor, 0o600)
                event = {key: value for key, value in asdict(entry).items() if key in _OUTPUT_FIELDS}
                payload = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
                os.write(descriptor, payload.encode("utf-8"))
            finally:
                os.close(descriptor)
        except OSError:
            # Diagnostics must never change ComputerSeat execution behavior.
            return


def _safe_token(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text if _SAFE_TOKEN.fullmatch(text) else fallback


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
