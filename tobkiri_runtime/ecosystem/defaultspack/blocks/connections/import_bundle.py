from __future__ import annotations

import json
from typing import Any

from blocks._common import error, ok
from domain.connections.store import import_connection_bundle


def _import_payload(input_data: dict[str, Any]) -> str | dict[str, Any]:
    for key in ("credential_bundle", "connection", "bundle"):
        value = input_data.get(key)
        if isinstance(value, (str, dict)):
            return value
    if any(key in input_data for key in ("access_token", "token", "api_token", "CLOUDFLARE_API_TOKEN")):
        return dict(input_data)
    return {}


def run(input_data, context):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    method = str(payload.get("_method") or "POST").upper()
    if method != "POST":
        return error("unsupported method", "METHOD_NOT_ALLOWED")

    provider_id = str(payload.get("provider_id") or "").strip()
    try:
        result = import_connection_bundle(_import_payload(payload), provider_id=provider_id)
    except (ValueError, KeyError, RuntimeError, json.JSONDecodeError):
        return error("credential import failed", "CONNECTION_IMPORT_FAILED")
    return ok({key: value for key, value in result.items() if key not in {"access_token", "refresh_token", "token"}})
