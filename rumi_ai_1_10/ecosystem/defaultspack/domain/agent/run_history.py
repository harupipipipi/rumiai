from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


class RunHistory:
    def __init__(self, root: Path | None = None) -> None:
        pack_root = Path(root or _pack_root())
        override = (
            os.environ.get("RUMI_DEFAULTSPACK_AGENT_RUN_HISTORY_PATH", "").strip()
            or os.environ.get("RUMI_DEFAULTSPACK_AGENT_RUNS_PATH", "").strip()
        )
        self.path = Path(override) if override else pack_root / "user_data" / "shared" / "agents" / "runs.json"

    def append(self, agent_id: str, run: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        runs = data.setdefault(agent_id, [])
        runs.append(run)
        self._write(data)
        return run

    def append_run(self, run: dict[str, Any]) -> dict[str, Any]:
        return self.append(str((run or {}).get("agent_id") or ""), dict(run or {}))

    def list(self, agent_id: str) -> list[dict[str, Any]]:
        runs = self._read().get(agent_id)
        return list(runs) if isinstance(runs, list) else []

    def list_runs(self, agent_id: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if agent_id:
            runs = list(reversed(self.list(agent_id)))
        else:
            data = self._read()
            runs = []
            for value in data.values():
                if isinstance(value, list):
                    runs.extend(item for item in value if isinstance(item, dict))
            runs.sort(key=lambda item: str(item.get("started_at") or ""), reverse=True)
        total = len(runs)
        return {"entries": runs[offset: offset + limit], "total": total, "limit": limit, "offset": offset}

    def append_log(self, agent_id: str, message: str, **fields: Any) -> dict[str, Any]:
        return self.append(agent_id, {"agent_id": agent_id, "message": message, "log": True, **fields})

    def list_logs(self, agent_id: str = "", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        runs = self.list_runs(agent_id, limit=1000, offset=0)["entries"]
        logs = [item for item in runs if item.get("log")]
        total = len(logs)
        return {"entries": logs[offset: offset + limit], "total": total, "limit": limit, "offset": offset}

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


RunHistoryStore = RunHistory
