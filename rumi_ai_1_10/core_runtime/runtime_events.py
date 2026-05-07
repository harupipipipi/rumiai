"""Generic runtime events used by durable pack features."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional


RuntimeEventType = Literal[
    "run_started",
    "run_step",
    "run_completed",
    "run_failed",
    "compact_started",
    "compact_completed",
    "tool_started",
    "tool_completed",
    "approval_requested",
    "approval_decided",
    "memory_flushed",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RuntimeEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}
