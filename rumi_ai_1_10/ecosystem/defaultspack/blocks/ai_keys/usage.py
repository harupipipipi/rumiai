from __future__ import annotations

from ._common import KeyUsageTracker, key_error, ok


def run(input_data, context=None):
    try:
        key_id = str(input_data.get("key_id") or input_data.get("id") or "")
        return ok({"key_id": key_id, "usage": KeyUsageTracker().get(key_id)})
    except Exception as exc:
        return key_error(exc)
