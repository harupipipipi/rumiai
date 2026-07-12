"""defaults.memory.recall — メモリからの検索ハンドラー.

input_data:
    query : str — 検索クエリ (必須)
    limit : int — 最大件数 (任意, デフォルト 5)

戻り値:
    {"status": "ok", "data": {"results": [{"id": str, "content": str, "metadata": dict, "score": float}]}}
"""

from __future__ import annotations

from typing import Any, Dict

from blocks._common import error, ok
from domain.memory.store import MemoryStore


def run(input_data: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """メモリからクエリに一致するエントリを検索する."""
    try:
        query = input_data.get("query")
        if not query or not isinstance(query, str) or query.strip() == "":
            return error("query is required and must be a non-empty string", "INVALID_INPUT")

        limit = input_data.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            limit = 5

        store = MemoryStore()
        results = store.recall(query=query, limit=limit)

        return ok({"results": results})

    except Exception as exc:
        return error(f"Failed to recall memory: {exc}", "RECALL_ERROR")
