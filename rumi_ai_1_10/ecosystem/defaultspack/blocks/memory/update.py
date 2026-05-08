import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.memory2.sqlite_store import MemorySQLiteStore


def run(input_data, context=None):
    memory_id = input_data.get("id") or input_data.get("memory_id")
    if not memory_id:
        return error("memory_id is required", "INVALID_INPUT")
    updates = input_data.get("updates", {})
    if not isinstance(updates, dict):
        updates = {key: value for key, value in input_data.items() if key not in {"id", "memory_id"}}
    entry = MemorySQLiteStore().update(memory_id, updates)
    if not entry:
        return error("memory not found", "NOT_FOUND")
    return ok(entry)
