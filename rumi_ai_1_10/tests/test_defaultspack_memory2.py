from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.memory.store import MemoryStore  # noqa: E402
from domain.memory2.flush import flush_memory  # noqa: E402
from domain.memory2.markdown_store import MarkdownMemoryStore  # noqa: E402
from domain.memory2.sqlite_store import MemorySQLiteStore  # noqa: E402


def test_memory2_sqlite_and_markdown_store(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MEMORY2_DIR", str(tmp_path / "memory"))
    MemorySQLiteStore._instance = None

    store = MemorySQLiteStore()
    entry = store.add("Rumi likes durable memory", {"kind": "fact"}, scope="user")
    MarkdownMemoryStore().append_memory(entry["content"], entry["metadata"])

    results = store.search("durable", limit=3)
    assert results[0]["id"] == entry["id"]
    assert (tmp_path / "memory" / "MEMORY.md").exists()


def test_legacy_memory_store_bridges_to_memory2(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MEMORY2_DIR", str(tmp_path / "memory"))
    MemorySQLiteStore._instance = None
    MemoryStore._instance = None
    MemoryStore._initialized = False

    legacy = MemoryStore()
    entry = legacy.store("Project convention: keep APIs compatible", {"scope": "project"})

    assert entry["durable"] is True
    assert legacy.recall("compatible", limit=1)[0]["id"] == entry["id"]


def test_memory_flush_returns_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MEMORY2_DIR", str(tmp_path / "memory"))
    MemorySQLiteStore._instance = None

    refs = flush_memory(["Decision: use SQLite WAL", "NO_REPLY"], scope="session")

    assert len(refs) == 1
    assert refs[0]["scope"] == "session"


def test_memory_sqlite_store_supports_parallel_thread_access(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_MEMORY2_DIR", str(tmp_path / "memory"))
    MemorySQLiteStore._instance = None
    store = MemorySQLiteStore()

    def add_and_search(index: int):
        store.add(f"parallel memory {index}", {"token": "secret-value"}, scope="session")
        return len(store.search("parallel", limit=50, scope="session"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(add_and_search, range(20)))

    assert max(results) >= 1
    assert store.search("secret-value", limit=5) == []
