"""defaults.knowledge.create — ナレッジ追加ハンドラー.

input_data:
    content  : str  — テキスト本文 (必須)
    metadata : dict — 任意のメタデータ (任意, デフォルト {})

戻り値:
    ok({"id", "content", "metadata", "created_at", "updated_at"})
"""

from blocks._common import ok, error
from domain.knowledge.store import KnowledgeStore


def run(input_data, context):
    try:
        content = input_data.get("content")
        if not content or not isinstance(content, str) or content.strip() == "":
            return error("content is required and must be a non-empty string", "INVALID_INPUT")

        metadata = input_data.get("metadata", {})
        if not isinstance(metadata, dict):
            return error("metadata must be a dict", "INVALID_INPUT")

        store = KnowledgeStore()
        entry = store.create(content=content.strip(), metadata=metadata)

        return ok({
            "id": entry["id"],
            "content": entry["content"],
            "metadata": entry["metadata"],
            "created_at": entry["created_at"],
            "updated_at": entry["updated_at"],
        })
    except Exception as exc:
        return error("failed to create knowledge: " + str(exc), "KNOWLEDGE_CREATE_ERROR")
