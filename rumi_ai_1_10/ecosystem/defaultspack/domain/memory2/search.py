from __future__ import annotations

from typing import Any

from .sqlite_store import MemorySQLiteStore


class MemorySearch:
    def __init__(self, store: MemorySQLiteStore | None = None) -> None:
        self.store = store or MemorySQLiteStore()

    def search(self, query: str, limit: int = 5, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        return self.store.search(
            query,
            limit=limit,
            scope=filters.get("scope"),
            agent_id=filters.get("agent_id"),
            project_id=filters.get("project_id"),
        )
