import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok


def _pack_root():
    return Path(__file__).resolve().parents[2]


def run(input_data, context=None):
    compact_id = input_data.get("compact_id")
    if not compact_id:
        return error("'compact_id' is required", code="INVALID_INPUT")
    path = _pack_root() / "user_data" / "context" / (compact_id + ".json")
    if not path.is_file():
        return error("Compact context not found", code="NOT_FOUND")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["restored"] = True
    return ok(payload)
