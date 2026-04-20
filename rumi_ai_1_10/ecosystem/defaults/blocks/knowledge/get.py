"""defaults.knowledge.get — ID でナレッジを取得するハンドラー.

input_data:
    id : str — ナレッジ ID (必須)

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

        store = KnowledgeStore()
        entry = store.get(entry_id)
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
        return error("failed to get knowledge: " + str(exc), "KNOWLEDGE_GET_ERROR")
