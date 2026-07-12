from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import TERMINAL_STATES
from .store import JsonFileStore, default_continuity_dir


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class HandoffOperationStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_continuity_dir()
        self.store = JsonFileStore(self.root / "handoff_operations.json")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation_id = str(payload.get("operation_id") or "handoff-" + uuid.uuid4().hex[:18])
        now = utc_now()
        operation = {
            "operation_id": operation_id,
            "status": str(payload.get("status") or "PLANNED"),
            "created_at": now,
            "updated_at": now,
            "events": [],
            **payload,
        }

        def _update(data: dict[str, Any]):
            operations = data.setdefault("operations", {})
            operations[operation_id] = operation
            return data, dict(operation)

        return self.store.update(_update)

    def get(self, operation_id: str) -> dict[str, Any] | None:
        data = self.store.read()
        operations = data.get("operations") if isinstance(data.get("operations"), dict) else {}
        operation = operations.get(str(operation_id))
        return dict(operation) if isinstance(operation, dict) else None

    def list(self) -> list[dict[str, Any]]:
        data = self.store.read()
        operations = data.get("operations") if isinstance(data.get("operations"), dict) else {}
        return sorted(
            (dict(item) for item in operations.values() if isinstance(item, dict)),
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )

    def transition(self, operation_id: str, status: str, *, message: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
        def _update(data: dict[str, Any]):
            operations = data.setdefault("operations", {})
            current = dict(operations.get(operation_id) or {"operation_id": operation_id, "created_at": utc_now(), "events": []})
            if str(current.get("status") or "") in TERMINAL_STATES:
                return data, current
            event = {"status": status, "message": message, "details": dict(details or {}), "at": utc_now()}
            events = list(current.get("events") if isinstance(current.get("events"), list) else [])
            events.append(event)
            current.update({"status": status, "updated_at": event["at"], "message": message, "events": events})
            if details:
                current.update(details)
            operations[operation_id] = current
            return data, dict(current)

        return self.store.update(_update)

    def cancel(self, operation_id: str) -> dict[str, Any] | None:
        if self.get(operation_id) is None:
            return None
        return self.transition(operation_id, "CANCELLED", message="Handoff operation was cancelled.")
