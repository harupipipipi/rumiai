"""Memory Store — シングルトンのインメモリストア.

4つのストレージ領域を管理する:
- short_term : dict  — セッション内のみ保持する key-value
- long_term  : list  — 永続的なメモリエントリ
- project_context : dict — プロジェクト固有の情報
- vector_store : list — ベクトルストア (最小動作版は文字列部分一致で代用)
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional


def _timestamp() -> str:
    """ISO 8601 タイムスタンプを返す."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _compute_score(query: str, content: str) -> float:
    """クエリとコンテンツの類似度スコアを計算する.

    最小動作版ではベクトル検索の代わりに文字列ベースの
    3段階マッチングで代用する:
      1. 完全一致        → 1.0
      2. 部分文字列一致  → len(query) / len(content)
      3. 単語レベル一致  → 一致単語数 / クエリ単語数
    """
    q = query.lower().strip()
    c = content.lower().strip()

    if not q or not c:
        return 0.0

    # 完全一致
    if q == c:
        return 1.0

    # 部分文字列一致
    if q in c:
        return round(len(q) / max(len(c), 1), 4)

    # 単語レベルのマッチング
    q_words = set(q.split())
    c_words = set(c.split())
    if not q_words:
        return 0.0
    matched = q_words & c_words
    if not matched:
        return 0.0
    return round(len(matched) / len(q_words), 4)


class MemoryStore:
    """スレッドセーフなシングルトン Memory Store."""

    _instance: Optional["MemoryStore"] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    # -- シングルトン ---------------------------------------------------------
    def __new__(cls) -> "MemoryStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self.short_term: Dict[str, Any] = {}
            self.long_term: List[Dict[str, Any]] = []
            self.project_context: Dict[str, Any] = {}
            self.vector_store: List[Dict[str, Any]] = []
            self._initialized = True

    # -- long_term 操作 -------------------------------------------------------
    def store(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """long_term にメモリエントリを追加する."""
        entry = {
            "id": str(uuid.uuid4()),
            "content": content,
            "metadata": metadata if metadata is not None else {},
            "created_at": _timestamp(),
        }
        with self._lock:
            self.long_term.append(entry)
        try:
            from domain.memory2.markdown_store import MarkdownMemoryStore
            from domain.memory2.sqlite_store import MemorySQLiteStore

            durable = MemorySQLiteStore().add(
                content,
                metadata or {},
                scope=(metadata or {}).get("scope", "user") if isinstance(metadata, dict) else "user",
                source="legacy_memory_store",
                memory_id=entry["id"],
            )
            MarkdownMemoryStore().append_memory(content, metadata or {})
            entry.update({"durable": True, "durable_id": durable["id"]})
        except Exception:
            entry["durable"] = False
        return entry

    def recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """long_term から部分一致検索し、スコア順で返す."""
        results: List[Dict[str, Any]] = []
        with self._lock:
            entries = list(self.long_term)

        for entry in entries:
            score = _compute_score(query, entry["content"])
            if score > 0.0:
                results.append({
                    "id": entry["id"],
                    "content": entry["content"],
                    "metadata": entry["metadata"],
                    "score": score,
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        try:
            from domain.memory2.search import MemorySearch

            seen = {item["id"] for item in results}
            for item in MemorySearch().search(query, limit=limit):
                if item["id"] in seen:
                    continue
                results.append({
                    "id": item["id"],
                    "content": item["content"],
                    "metadata": item.get("metadata", {}),
                    "score": item.get("score", 0.0),
                })
        except Exception:
            pass

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """recall のエイリアス."""
        return self.recall(query, limit)

    # -- vector_store 操作 ----------------------------------------------------
    def vector_add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """vector_store にエントリを追加する (embedding は None)."""
        entry = {
            "id": str(uuid.uuid4()),
            "content": content,
            "embedding": None,
            "metadata": metadata if metadata is not None else {},
        }
        with self._lock:
            self.vector_store.append(entry)
        try:
            from domain.memory2.sqlite_store import MemorySQLiteStore

            MemorySQLiteStore().add(
                content,
                metadata or {},
                scope=(metadata or {}).get("scope", "user") if isinstance(metadata, dict) else "user",
                source="legacy_vector_store",
                memory_id=entry["id"],
            )
        except Exception:
            pass
        return entry

    def vector_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """vector_store から部分一致検索しスコア順で返す."""
        results: List[Dict[str, Any]] = []
        with self._lock:
            entries = list(self.vector_store)

        for entry in entries:
            score = _compute_score(query, entry["content"])
            if score > 0.0:
                results.append({
                    "id": entry["id"],
                    "content": entry["content"],
                    "metadata": entry["metadata"],
                    "score": score,
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    # -- 削除・クリア ---------------------------------------------------------
    def delete(self, memory_id: str) -> bool:
        """指定 ID のエントリを long_term と vector_store から削除する."""
        found = False
        with self._lock:
            before_lt = len(self.long_term)
            self.long_term = [e for e in self.long_term if e["id"] != memory_id]
            if len(self.long_term) < before_lt:
                found = True

            before_vs = len(self.vector_store)
            self.vector_store = [e for e in self.vector_store if e["id"] != memory_id]
            if len(self.vector_store) < before_vs:
                found = True
        try:
            from domain.memory2.sqlite_store import MemorySQLiteStore

            found = MemorySQLiteStore().delete(memory_id) or found
        except Exception:
            pass
        return found

    def clear(self) -> None:
        """全ストレージをクリアする."""
        with self._lock:
            self.short_term.clear()
            self.long_term.clear()
            self.project_context.clear()
            self.vector_store.clear()
