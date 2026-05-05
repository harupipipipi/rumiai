from __future__ import annotations

from ._common import KeyManager, key_error, ok


def run(input_data, context=None):
    try:
        key_id = str(input_data.get("key_id") or input_data.get("id") or "")
        item = KeyManager().get_key(key_id)
        if not item:
            raise ValueError("api key not found")
        return ok({"key_id": key_id, "configured": bool(item.get("configured")), "provider_id": item.get("provider_id")})
    except Exception as exc:
        return key_error(exc)
