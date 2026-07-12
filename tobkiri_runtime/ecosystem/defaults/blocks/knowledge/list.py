"""defaults.knowledge.list — ナレッジ一覧取得ハンドラー.

input_data:
    limit  : int — 最大件数 (任意, デフォルト 50)
    offset : int — オフセット (任意, デフォルト 0)

戻り値:
    ok({"items": [...], "total": int})
"""

from blocks._common import ok, error
from domain.knowledge.store import KnowledgeStore


def run(input_data, context):
    try:
        limit = input_data.get("limit", 50)
        if not isinstance(limit, int) or limit < 1:
            limit = 50

        offset = input_data.get("offset", 0)
        if not isinstance(offset, int) or offset < 0:
            offset = 0

        store = KnowledgeStore()
        result = store.list_entries(limit=limit, offset=offset)

        return ok(result)
    except Exception as exc:
        return error("failed to list knowledge: " + str(exc), "KNOWLEDGE_LIST_ERROR")
