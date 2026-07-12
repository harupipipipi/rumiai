"""defaults.knowledge.delete — ナレッジ削除ハンドラー.

input_data:
    id : str — ナレッジ ID (必須)

戻り値:
    ok({"deleted": True})
"""

from blocks._common import ok, error
from domain.knowledge.store import KnowledgeStore


def run(input_data, context):
    try:
        entry_id = input_data.get("id")
        if not entry_id or not isinstance(entry_id, str):
            return error("id is required", "INVALID_INPUT")

        store = KnowledgeStore()
        deleted = store.delete(entry_id)
        if not deleted:
            return error("knowledge entry not found: " + entry_id, "NOT_FOUND")

        return ok({"deleted": True})
    except Exception as exc:
        return error("failed to delete knowledge: " + str(exc), "KNOWLEDGE_DELETE_ERROR")
