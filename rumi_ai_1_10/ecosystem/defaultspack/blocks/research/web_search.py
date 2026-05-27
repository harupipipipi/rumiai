import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.research.providers import ExternalWebProvider


def run(input_data, context=None):
    query = input_data.get("query")
    if not query:
        return error("'query' is required", code="INVALID_INPUT")
    provider = ExternalWebProvider()
    result = provider.search(
        query,
        limit=int(input_data.get("limit", 5)),
        allow_network=bool(input_data.get("allow_network", True)),
        timeout=float(input_data.get("timeout", 8.0)),
        domains=input_data.get("domains"),
        official_only=bool(input_data.get("official_only", False)),
        fetch_pages=bool(input_data.get("fetch_pages", False)),
    )
    return ok(result.as_dict())
