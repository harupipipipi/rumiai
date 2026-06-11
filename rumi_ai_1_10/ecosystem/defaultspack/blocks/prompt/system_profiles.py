"""HTTP handlers for system prompt profile management."""

from blocks._common import ok, error
from domain.prompt.manager import get_manager


def _payload_for_update(input_data: dict) -> dict:
    payload = dict(input_data)
    for key in ("_method", "_actual_method", "prompt_id", "action"):
        payload.pop(key, None)
    if isinstance(payload.get("updates"), dict):
        payload.update(payload["updates"])
        payload.pop("updates", None)
    return payload


def run(input_data: dict, context: dict) -> dict:
    method = str(input_data.get("_actual_method") or input_data.get("_method") or "GET").upper()
    action = str(input_data.get("action") or "").strip().lower()
    prompt_id = str(input_data.get("prompt_id") or input_data.get("id") or input_data.get("name") or "").strip()
    manager = get_manager()

    if method == "GET":
        return ok(manager.list_system_prompts())

    if method == "POST" and action == "activate":
        if not prompt_id:
            return error("'prompt_id' is required", "INVALID_INPUT")
        result = manager.activate_system_prompt(prompt_id)
        if result is None:
            return error("system prompt not found", "NOT_FOUND")
        return ok({**manager.list_system_prompts(), **result})

    if method == "POST" and action in {"set_inline", "set"}:
        if "content" not in input_data and "body" not in input_data:
            return error("'content' is required", "INVALID_INPUT")
        content = input_data.get("content", input_data.get("body", ""))
        active_content = manager.set_system_prompt(str(content))
        return ok({
            **manager.list_system_prompts(),
            "active_id": "",
            "active_content": active_content,
            "inline_content": str(content),
        })

    if method == "POST":
        if "content" not in input_data and "body" not in input_data:
            return error("'content' is required", "INVALID_INPUT")
        prompt = manager.create_system_prompt(input_data)
        return ok({**manager.list_system_prompts(), "prompt": prompt})

    if method == "PUT":
        if not prompt_id:
            return error("'prompt_id' is required", "INVALID_INPUT")
        prompt = manager.update_system_prompt(prompt_id, _payload_for_update(input_data))
        if prompt is None:
            return error("system prompt not found or read-only", "NOT_FOUND")
        return ok({**manager.list_system_prompts(), "prompt": prompt})

    if method == "DELETE":
        if not prompt_id:
            return error("'prompt_id' is required", "INVALID_INPUT")
        deleted = manager.delete_system_prompt(prompt_id)
        if not deleted:
            return error("system prompt not found or read-only", "NOT_FOUND")
        return ok({**manager.list_system_prompts(), "deleted": True})

    return error("unsupported method", "METHOD_NOT_ALLOWED")
