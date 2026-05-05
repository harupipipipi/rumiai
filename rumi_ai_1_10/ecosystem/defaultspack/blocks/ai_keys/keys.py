import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.ai_client.key_manager import KeyManager


def run(input_data, context):
    del context
    input_data = input_data or {}
    method = str(input_data.get("_method") or input_data.get("method") or "GET").upper()
    manager = KeyManager()
    try:
        if method == "GET":
            key_id = str(input_data.get("key_id") or input_data.get("id") or "").strip()
            if key_id:
                item = manager.get_key(key_id)
                if item is None:
                    return error("key not found", "NOT_FOUND")
                return ok({"key": item})
            return ok({"keys": manager.list_keys()})
        if method == "POST":
            item = manager.create_key(
                provider_id=input_data.get("provider_id", ""),
                value=input_data.get("value", ""),
                name=input_data.get("name", ""),
                key_id=input_data.get("key_id"),
                env_var=input_data.get("env_var", ""),
                default_for_provider=bool(input_data.get("default_for_provider", False)),
                profile_ids=input_data.get("profile_ids") if isinstance(input_data.get("profile_ids"), list) else [],
                agent_ids=input_data.get("agent_ids") if isinstance(input_data.get("agent_ids"), list) else [],
                metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {},
            )
            return ok({"key": item})
        if method in {"PUT", "PATCH"}:
            key_id = str(input_data.get("key_id") or input_data.get("id") or "").strip()
            if not key_id:
                return error("key_id is required", "INVALID_INPUT")
            updates = input_data.get("updates") if isinstance(input_data.get("updates"), dict) else dict(input_data)
            item = manager.update_key(key_id, updates)
            if item is None:
                return error("key not found", "NOT_FOUND")
            return ok({"key": item})
        if method == "DELETE":
            key_id = str(input_data.get("key_id") or input_data.get("id") or "").strip()
            if not key_id:
                return error("key_id is required", "INVALID_INPUT")
            return ok({"deleted": manager.delete_key(key_id), "key_id": key_id})
    except Exception as exc:
        return error(str(exc), "API_KEY_MANAGER_ERROR")
    return error("unsupported method", "METHOD_NOT_ALLOWED")
