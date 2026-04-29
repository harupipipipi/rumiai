import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import error, ok

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.knowledge.store import KnowledgeStore


def run(input_data, context):
    del context
    query = input_data.get("query")
    if not isinstance(query, str) or not query.strip():
        return error("query is required", "INVALID_INPUT")
    limit = input_data.get("limit", 8)
    if not isinstance(limit, int) or limit < 1:
        limit = 8
    results = KnowledgeStore().search(query=query.strip(), limit=limit, threshold=float(input_data.get("threshold", 0.0)))
    sources = []
    for item in results:
        metadata = item.get("metadata", {}) or {}
        sources.append(
            {
                "source_id": item.get("id"),
                "type": metadata.get("type", "local_file"),
                "title": metadata.get("title", metadata.get("source", item.get("id"))),
                "path": metadata.get("path", metadata.get("source", "")),
                "url": metadata.get("url", ""),
                "trust_level": metadata.get("trust_level", "medium"),
                "summary": item.get("content", "")[:500],
                "score": item.get("score", 0),
            }
        )
    return ok({"query": query.strip(), "sources": sources, "count": len(sources)})
