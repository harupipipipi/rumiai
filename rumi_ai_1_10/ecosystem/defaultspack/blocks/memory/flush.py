import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.memory2.flush import flush_memory


def run(input_data, context=None):
    items = input_data.get("items", [])
    if isinstance(input_data.get("content"), str):
        items = [input_data["content"]]
    if not isinstance(items, list):
        items = [str(items)]
    refs = flush_memory(
        [str(item) for item in items],
        scope=input_data.get("scope", "session"),
        metadata=input_data.get("metadata", {}) if isinstance(input_data.get("metadata", {}), dict) else {},
    )
    return ok({"memory_flush_refs": refs})
