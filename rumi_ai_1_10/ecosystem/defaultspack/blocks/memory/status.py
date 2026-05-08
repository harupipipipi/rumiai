import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.memory2.markdown_store import MarkdownMemoryStore
from domain.memory2.sqlite_store import MemorySQLiteStore, default_memory_dir


def run(input_data, context=None):
    store = MemorySQLiteStore()
    count = store.conn.execute("SELECT COUNT(*) AS count FROM memory_entries WHERE archived_at IS NULL").fetchone()["count"]
    markdown = MarkdownMemoryStore()
    return ok({
        "enabled": True,
        "backend": "sqlite_markdown",
        "root": str(default_memory_dir()),
        "entry_count": count,
        "files": sorted(markdown.snapshot().keys()),
    })
