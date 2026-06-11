import json
import os
import sys
from pathlib import Path
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.context_engine.validation import validate_compact_packet


def _pack_root():
    return Path(__file__).resolve().parents[2]


def run(input_data, context=None):
    compact_id = input_data.get("compact_id")
    if not compact_id:
        return error("'compact_id' is required", code="INVALID_INPUT")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", str(compact_id)):
        return error("'compact_id' contains unsafe characters", code="INVALID_INPUT")
    path = _pack_root() / "user_data" / "context" / (compact_id + ".json")
    root = (_pack_root() / "user_data" / "context").resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return error("'compact_id' resolves outside context store", code="INVALID_INPUT")
    if not path.is_file():
        return error("Compact context not found", code="NOT_FOUND")
    payload = json.loads(path.read_text(encoding="utf-8"))
    validation = validate_compact_packet(payload)
    if not validation.valid:
        return error("Stored compact context is invalid: " + "; ".join(validation.errors), code="INVALID_CONTEXT_PACKET")
    payload["validation"] = validation.to_dict()
    payload["restored"] = True
    return ok(payload)
