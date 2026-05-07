from __future__ import annotations

from pathlib import Path

from .sqlite_store import default_memory_dir


def write_wiki_page(slug: str, content: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in slug) or "page"
    path = default_memory_dir() / "wiki" / f"{safe}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
