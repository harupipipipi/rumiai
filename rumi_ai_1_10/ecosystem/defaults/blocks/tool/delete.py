import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.registry import ToolRegistry


def run(input_data, context):
    """defaults.tool.delete — 動的ツールを削除する"""
    name = input_data.get("name")
    if not name:
        return error("name is required", "MISSING_PARAM")

    registry = ToolRegistry()

    existing = registry.get(name)
    if existing is None:
        return error("Tool '{}' not found".format(name), "NOT_FOUND")

    exec_type = existing.get("execution", {}).get("type", "")
    if exec_type != "dynamic":
        return error("Only dynamic tools can be deleted", "NOT_DYNAMIC")

    deleted = registry.unregister_dynamic(name)
    if deleted is None:
        return error("Failed to delete tool '{}'".format(name), "DELETE_ERROR")

    return ok({
        "deleted": name,
        "tool_id": deleted.get("tool_id", name),
    })
