from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .run_store import AgentRunStore


class RecoveryService:
    def __init__(self, store: AgentRunStore | None = None) -> None:
        self.store = store or AgentRunStore()

    def mark_stale_runs(self, *, stale_after_seconds: int = 600) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        stale: list[str] = []
        for run in self.store.list_runs(status="running", limit=1000):
            heartbeat = run.get("heartbeat_at") or run.get("updated_at")
            if _parse_ts(heartbeat) < cutoff:
                self.store.update_status(run["run_id"], "stale", error="heartbeat expired")
                stale.append(run["run_id"])
        return stale


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromtimestamp(0, timezone.utc)
