import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.registry import ToolRegistry


def run(input_data, context):
    """defaults.tool.update — 動的ツール定義を部分更新する"""
    name = input_data.get("name")
    if not name:
        return error("name is required", "MISSING_PARAM")

    updates = input_data.get("updates")
    if updates is None or not isinstance(updates, dict):
        return error("updates (dict) is required", "MISSING_PARAM")

    if not updates:
        return error("updates must not be empty", "INVALID_PARAM")

    # name / tool_id の変更は禁止
    if "name" in updates or "tool_id" in updates:
        return error("Cannot change name or tool_id via update", "INVALID_PARAM")

    registry = ToolRegistry()

    existing = registry.get(name)
    if existing is None:
        return error("Tool '{}' not found".format(name), "NOT_FOUND")

    exec_type = existing.get("execution", {}).get("type", "")
    if exec_type != "dynamic":
        return error("Only dynamic tools can be updated", "NOT_DYNAMIC")

    # updated_at を追加
    updates["updated_at"] = timestamp()

    updated = registry.update_dynamic(name, updates)
    if updated is None:
        return error("Failed to update tool '{}'".format(name), "UPDATE_ERROR")

    return ok({
        "tool_id": updated["tool_id"],
        "name": updated["name"],
        "summary": updated.get("summary", ""),
        "tags": updated.get("tags", []),
        "updated_at": updated.get("updated_at", ""),
    })
