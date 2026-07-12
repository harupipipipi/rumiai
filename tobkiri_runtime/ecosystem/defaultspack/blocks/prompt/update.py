"""defaults.prompt.update — プロンプト更新 handler

入力:
    {
        "name": str,         # 更新対象のプロンプト名
        "updates": {         # 更新するフィールド
            "content": str,           # (optional) テンプレート本文
            "body": str,              # (optional) content のエイリアス
            "description": str,       # (optional)
            "variables": [...],       # (optional)
            "metadata": {...},        # (optional)
            "name": str               # (optional) 名前変更
        }
    }

出力:
    {"status": "ok", "data": {"prompt": {...}}}
"""

from blocks._common import ok, error
from domain.prompt.manager import get_manager


def run(input_data: dict, context: dict) -> dict:
    name = input_data.get("name")
    updates = input_data.get("updates")

    if not name:
        return error("'name' is required", "INVALID_INPUT")
    if not updates or not isinstance(updates, dict):
        return error("'updates' dict is required", "INVALID_INPUT")

    manager = get_manager()
    result = manager.update_prompt(name, updates)

    if result is None:
        return error(f"Prompt not found: {name}", "NOT_FOUND")

    return ok({"prompt": result})
