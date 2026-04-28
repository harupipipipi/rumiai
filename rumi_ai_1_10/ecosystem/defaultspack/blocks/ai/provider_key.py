import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.ai_client.api_key_store import provider_key_status, set_provider_api_key


def run(input_data, context):
    del context
    method = (input_data or {}).get("_method", "GET").upper()
    if method == "GET":
        return ok({"providers": provider_key_status()})
    if method == "POST":
        provider_id = str((input_data or {}).get("provider_id", "")).strip()
        value = str((input_data or {}).get("value", ""))
        result = set_provider_api_key(provider_id, value)
        if not result.get("success"):
            return error(result.get("error") or "failed to save api key", "API_KEY_SAVE_FAILED")
        return ok({key: value for key, value in result.items() if key != "error"})
    return error("unsupported method", "METHOD_NOT_ALLOWED")
