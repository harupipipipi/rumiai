"""defaults.memory.vector_store — ベクトルストアへの保存ハンドラー.

input_data:
    content  : str  — 保存するコンテンツ (必須)
    metadata : dict — 付加メタデータ (任意, デフォルト {})

戻り値:
    {"status": "ok", "data": {"id": str}}
"""

from __future__ import annotations

from typing import Any, Dict

from blocks._common import error, ok
from domain.memory.store import MemoryStore


def run(input_data: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """ベクトルストアにコンテンツを保存する."""
    try:
        content = input_data.get("content")
        if not content or not isinstance(content, str) or content.strip() == "":
            return error("content is required and must be a non-empty string", "INVALID_INPUT")

        metadata = input_data.get("metadata", {})
        if not isinstance(metadata, dict):
            return error("metadata must be a dict", "INVALID_INPUT")

        store = MemoryStore()
        entry = store.vector_add(content=content, metadata=metadata)

        return ok({"id": entry["id"]})

    except Exception as exc:
        return error(f"Failed to store vector: {exc}", "VECTOR_STORE_ERROR")
