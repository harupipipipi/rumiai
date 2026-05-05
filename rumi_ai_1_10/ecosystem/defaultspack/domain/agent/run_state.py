from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from blocks._common import timestamp


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


class RunStateStore:
    def __init__(self, root: Path | None = None) -> None:
        pack_root = Path(root or _pack_root())
        override = (
            os.environ.get("RUMI_DEFAULTSPACK_AGENT_RUN_STATE_PATH", "").strip()
            or os.environ.get("RUMI_DEFAULTSPACK_AGENT_STATE_PATH", "").strip()
        )
        self.path = Path(override) if override else pack_root / "user_data" / "shared" / "agents" / "state.json"

    def get(self, agent_id: str) -> dict[str, Any]:
        return dict(self._read().get(agent_id) or {"agent_id": agent_id, "status": "idle"})

    def update(self, agent_id: str, **updates: Any) -> dict[str, Any]:
        data = self._read()
        state = dict(data.get(agent_id) or {"agent_id": agent_id})
        state.update(updates)
        state["agent_id"] = agent_id
        state["updated_at"] = timestamp()
        data[agent_id] = state
        self._write(data)
        return state

    def transition(self, agent_id: str, status: str, **updates: Any) -> dict[str, Any]:
        return self.update(agent_id, status=status, **updates)

    def list(self) -> dict[str, Any]:
        return self._read()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
