"""defaults.prompt.delete — プロンプト削除 handler

入力:
    {"name": str}

出力:
    {"status": "ok", "data": {"deleted": str}}
"""

from blocks._common import ok, error
from domain.prompt.manager import get_manager


def run(input_data: dict, context: dict) -> dict:
    name = input_data.get("name")

    if not name:
        return error("'name' is required", "INVALID_INPUT")

    manager = get_manager()
    deleted = manager.delete_prompt(name)

    if not deleted:
        return error(f"Prompt not found: {name}", "NOT_FOUND")

    return ok({"deleted": name})
