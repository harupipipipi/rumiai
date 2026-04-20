"""defaults.knowledge.update — ナレッジ更新ハンドラー.

input_data:
    id       : str  — ナレッジ ID (必須)
    content  : str  — 新しいテキスト本文 (任意)
    metadata : dict — 新しいメタデータ (任意)

content を変更した場合は embedding も再取得される。

戻り値:
    ok({"id", "content", "metadata", "created_at", "updated_at"})
"""

from blocks._common import ok, error
from domain.knowledge.store import KnowledgeStore


def run(input_data, context):
    try:
        entry_id = input_data.get("id")
        if not entry_id or not isinstance(entry_id, str):
            return error("id is required", "INVALID_INPUT")

        content = input_data.get("content")
        if content is not None:
            if not isinstance(content, str) or content.strip() == "":
                return error("content must be a non-empty string", "INVALID_INPUT")
            content = content.strip()

        metadata = input_data.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            return error("metadata must be a dict", "INVALID_INPUT")

        if content is None and metadata is None:
            return error("at least one of content or metadata is required", "INVALID_INPUT")

        store = KnowledgeStore()
        entry = store.update(entry_id, content=content, metadata=metadata)
        if entry is None:
            return error("knowledge entry not found: " + entry_id, "NOT_FOUND")

        return ok({
            "id": entry["id"],
            "content": entry["content"],
            "metadata": entry["metadata"],
            "created_at": entry["created_at"],
            "updated_at": entry["updated_at"],
        })
    except Exception as exc:
        return error("failed to update knowledge: " + str(exc), "KNOWLEDGE_UPDATE_ERROR")
