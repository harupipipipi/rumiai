from __future__ import annotations

from .markdown_store import MarkdownMemoryStore


def record_dream(content: str) -> str:
    store = MarkdownMemoryStore()
    path = store.root / "DREAMS.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {content}\n")
    return str(path)
