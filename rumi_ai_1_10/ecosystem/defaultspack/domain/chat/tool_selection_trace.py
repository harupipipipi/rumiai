from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ToolSelectionTraceStore:
    def __init__(self, *, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        self._root = self._pack_root / "user_data" / "shared" / "tool_selection_traces"

    def save(self, trace: dict[str, Any]) -> None:
        trace_id = str(trace.get("selection_id") or "").strip()
        if not trace_id:
            return
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            (self._root / f"{trace_id}.json").write_text(
                json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            return

    def get(self, trace_id: str) -> dict[str, Any] | None:
        candidate = str(trace_id or "").strip()
        if not candidate or "/" in candidate or "\\" in candidate:
            return None
        path = self._root / f"{candidate}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None
