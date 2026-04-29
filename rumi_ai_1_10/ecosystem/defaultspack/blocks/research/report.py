import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import error, ok

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.artifact.store import ArtifactStore
from domain.knowledge.store import KnowledgeStore


def run(input_data, context):
    del context
    query = input_data.get("query")
    if not isinstance(query, str) or not query.strip():
        return error("query is required", "INVALID_INPUT")
    limit = input_data.get("limit", 8)
    results = KnowledgeStore().search(query=query.strip(), limit=limit if isinstance(limit, int) else 8)
    lines = [f"# Research Report: {query.strip()}", "", "## Summary", "", "Local knowledge search results.", "", "## Sources"]
    for index, item in enumerate(results, start=1):
        metadata = item.get("metadata", {}) or {}
        title = metadata.get("title") or metadata.get("source") or item.get("id")
        lines.extend(["", f"### {index}. {title}", "", item.get("content", "")[:1200]])
    content = "\n".join(lines).strip() + "\n"
    save = bool(input_data.get("save", False))
    artifact = None
    if save:
        artifact = ArtifactStore().create(
            artifact_type="report",
            title=f"Research Report: {query.strip()}",
            content=content,
            path=input_data.get("path"),
            source_task=query.strip(),
        )
    return ok({"query": query.strip(), "report": content, "artifact": artifact, "source_count": len(results)})
