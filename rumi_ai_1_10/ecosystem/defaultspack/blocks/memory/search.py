import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.memory2.search import MemorySearch


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    query = str(input_data.get("query", input_data.get("q", ""))) if isinstance(input_data, dict) else ""
    limit = int(input_data.get("limit", 5) if isinstance(input_data, dict) else 5)
    filters = input_data.get("filters", {}) if isinstance(input_data.get("filters", {}), dict) else {}
    for key in ("scope", "agent_id", "project_id"):
        if key in input_data:
            filters[key] = input_data[key]
    return ok({"results": MemorySearch().search(query, limit=limit, filters=filters)})
