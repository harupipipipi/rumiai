"""defaults.knowledge.search — テキストクエリで関連ナレッジをベクトル検索するハンドラー.

input_data:
    query     : str   — 検索クエリ (必須)
    limit     : int   — 最大件数 (任意, デフォルト 5)
    threshold : float — 最低スコア (任意, デフォルト 0.0)

戻り値:
    ok({"results": [{"id", "content", "metadata", "score"}]})
"""

from blocks._common import ok, error
from domain.knowledge.store import KnowledgeStore


def run(input_data, context):
    try:
        query = input_data.get("query")
        if not query or not isinstance(query, str) or query.strip() == "":
            return error("query is required and must be a non-empty string", "INVALID_INPUT")

        limit = input_data.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            limit = 5

        threshold = input_data.get("threshold", 0.0)
        if not isinstance(threshold, (int, float)):
            threshold = 0.0

        store = KnowledgeStore()
        results = store.search(query=query.strip(), limit=limit, threshold=float(threshold))

        return ok({"results": results})
    except Exception as exc:
        return error("failed to search knowledge: " + str(exc), "KNOWLEDGE_SEARCH_ERROR")
