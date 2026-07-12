"""defaults.prompt.system — システムプロンプト handler

入力:
    {"action": "get"}
        → {"status": "ok", "data": {"content": str}}

    {"action": "set", "content": str}
        → {"status": "ok", "data": {"content": str}}
"""

from blocks._common import ok, error
from domain.prompt.manager import get_manager


def run(input_data: dict, context: dict) -> dict:
    action = input_data.get("action")

    if action not in ("get", "set"):
        return error(
            "'action' must be 'get' or 'set'",
            "INVALID_INPUT",
        )

    manager = get_manager()

    if action == "get":
        content = manager.get_system_prompt()
        return ok({"content": content})

    # action == "set"
    content = input_data.get("content")
    if content is None:
        return error(
            "'content' is required for 'set' action",
            "INVALID_INPUT",
        )

    result = manager.set_system_prompt(content)
    return ok({"content": result})
