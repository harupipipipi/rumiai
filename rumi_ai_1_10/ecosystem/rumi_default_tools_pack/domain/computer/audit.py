"""Audit logging for all ComputerSeat actions.

Records every action to a JSON-lines file for traceability and debugging.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: float = 0.0
    action: str = ""
    driver: str = ""
    target_app: str = ""
    target_pid: int | None = None
    intent: str = ""
    selected_element: str = ""
    approval_required: bool = False
    result: dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """Append-only JSON-lines audit logger for ComputerSeat actions.

    Each line in the log file is a JSON object representing one action.
    """

    def __init__(self, log_path: str | Path | None = None) -> None:
        """Initialize the audit logger.

        Args:
            log_path: Path to the audit log file. Defaults to
                      ~/.rumi/computer_seat_audit.jsonl
        """
        if log_path is None:
            log_dir = Path.home() / ".rumi"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "computer_seat_audit.jsonl"
        self._log_path = Path(log_path)

    @property
    def log_path(self) -> Path:
        """Return the path to the audit log file."""
        return self._log_path

    def record(
        self,
        action: str,
        driver: str = "",
        target_app: str = "",
        target_pid: int | None = None,
        intent: str = "",
        selected_element: str = "",
        approval_required: bool = False,
        result: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Record an action to the audit log.

        Args:
            action: The action name (e.g. "click", "type_text").
            driver: The driver that executed the action.
            target_app: The target application name.
            target_pid: The target process ID.
            intent: The high-level intent description.
            selected_element: The element that was targeted.
            approval_required: Whether user approval was required.
            result: The action result data.

        Returns:
            The AuditEntry that was recorded.
        """
        entry = AuditEntry(
            timestamp=time.time(),
            action=action,
            driver=driver,
            target_app=target_app,
            target_pid=target_pid,
            intent=intent,
            selected_element=selected_element,
            approval_required=approval_required,
            result=result or {},
        )
        self._write(entry)
        return entry

    def _write(self, entry: AuditEntry) -> None:
        """Append an entry to the log file."""
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except OSError:
            # Audit logging should never crash the main flow
            pass
