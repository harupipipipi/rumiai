"""defaults.prompt.create — プロンプト作成 handler

入力:
    {"name": str, "content": str, "variables": [str]}

出力:
    {"status": "ok", "data": {"prompt": {...}}}
"""

from blocks._common import ok, error
from domain.prompt.manager import get_manager


def run(input_data: dict, context: dict) -> dict:
    name = input_data.get("name")
    content = input_data.get("content")

    if not name:
        return error("'name' is required", "INVALID_INPUT")
    if content is None:
        return error("'content' is required", "INVALID_INPUT")

    variables = input_data.get("variables", [])

    manager = get_manager()
    prompt = manager.create_prompt({
        "name": name,
        "content": content,
        "variables": variables,
    })
    return ok({"prompt": prompt})
