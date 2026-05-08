import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.memory2.markdown_store import MarkdownMemoryStore
from domain.memory2.sqlite_store import MemorySQLiteStore


def run(input_data, context=None):
    content = input_data.get("content") if isinstance(input_data, dict) else None
    if not content:
        return error("content is required", "INVALID_INPUT")
    metadata = input_data.get("metadata", {}) if isinstance(input_data.get("metadata", {}), dict) else {}
    scope = input_data.get("scope", "user")
    entry = MemorySQLiteStore().add(
        str(content),
        metadata,
        scope=scope,
        agent_id=input_data.get("agent_id"),
        project_id=input_data.get("project_id"),
        source=input_data.get("source", "manual"),
    )
    MarkdownMemoryStore().append_memory(str(content), {"scope": scope, **metadata})
    return ok(entry)
