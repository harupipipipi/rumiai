"""
blocks.tool.runtime.unregister — ランタイムtoolを削除する

input_data:
  - name: str（必須）— 削除するtool名
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import ok, error


def run(input_data, context):
    """ランタイムtoolを削除する"""
    if not isinstance(input_data, dict):
        return error("input_data must be a dict", "INVALID_INPUT")

    name = input_data.get("name")
    if not name or not isinstance(name, str):
        return error("name is required and must be a non-empty string", "MISSING_PARAM")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    from domain.tool.runtime_creator import RuntimeToolCreator

    creator = RuntimeToolCreator()

    try:
        deleted = creator.unregister_runtime_tool(name)
    except ValueError as exc:
        return error(str(exc), "NOT_FOUND")
    except Exception as exc:
        return error("Unregister failed: {}".format(exc), "DELETE_ERROR")

    return ok({
        "deleted": name,
        "tool_id": deleted.get("tool_id", name),
    })
