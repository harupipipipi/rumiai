import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.ai_client.api_key_store import (
    delete_provider_api_key,
    provider_key_status,
    rename_provider_api_key,
    set_provider_api_key,
)


def run(input_data, context):
    del context
    method = (input_data or {}).get("_method", "GET").upper()
    if method == "GET":
        return ok({"providers": provider_key_status()})
    if method == "POST":
        action = str((input_data or {}).get("action", "upsert")).strip().lower()
        provider_id = str((input_data or {}).get("provider_id", "")).strip()
        api_id = str((input_data or {}).get("api_id", "")).strip()
        name = str((input_data or {}).get("name", "")).strip()
        if action == "delete":
            result = delete_provider_api_key(provider_id, api_id)
        elif action == "rename":
            new_api_id = str((input_data or {}).get("new_api_id", "")).strip()
            result = rename_provider_api_key(
                provider_id,
                api_id,
                name,
                new_api_id=new_api_id or None,
                base_url=(input_data or {}).get("base_url"),
                allowed_models=(input_data or {}).get("allowed_models"),
                default_model=(input_data or {}).get("default_model"),
                notes=(input_data or {}).get("notes"),
                quota_label=(input_data or {}).get("quota_label"),
            )
        else:
            value = str((input_data or {}).get("value", ""))
            result = set_provider_api_key(
                provider_id,
                value,
                api_id=api_id or None,
                name=name or None,
                base_url=(input_data or {}).get("base_url"),
                allowed_models=(input_data or {}).get("allowed_models"),
                default_model=(input_data or {}).get("default_model"),
                notes=(input_data or {}).get("notes"),
                quota_label=(input_data or {}).get("quota_label"),
            )
        if not result.get("success"):
            return error(result.get("error") or "failed to save api key", "API_KEY_SAVE_FAILED")
        return ok({key: value for key, value in result.items() if key != "error"})
    return error("unsupported method", "METHOD_NOT_ALLOWED")
