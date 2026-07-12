from __future__ import annotations

from typing import Any

from .markdown_store import MarkdownMemoryStore
from .sqlite_store import MemorySQLiteStore


FLUSH_PROMPT = (
    "The session is near compaction. Save durable facts, decisions, project conventions, "
    "user preferences, and unresolved follow-ups to memory. If nothing should be saved, "
    "reply exactly NO_REPLY."
)


def flush_memory(
    items: list[str],
    *,
    scope: str = "session",
    metadata: dict[str, Any] | None = None,
    store: MemorySQLiteStore | None = None,
    markdown: MarkdownMemoryStore | None = None,
) -> list[dict[str, Any]]:
    store = store or MemorySQLiteStore()
    markdown = markdown or MarkdownMemoryStore()
    refs = []
    for item in items:
        text = str(item).strip()
        if not text or text == "NO_REPLY":
            continue
        entry = store.add(text, metadata or {}, scope=scope, source="flush")
        markdown.append_memory(text, {"scope": scope, **(metadata or {})})
        refs.append({"id": entry["id"], "scope": scope})
    return refs
