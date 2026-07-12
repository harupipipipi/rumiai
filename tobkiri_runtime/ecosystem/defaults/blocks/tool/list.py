import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.registry import ToolRegistry


def run(input_data, context):
    """defaults.tool.list — 登録済みツール一覧を返す"""
    filter_dict = input_data.get("filter")

    registry = ToolRegistry()
    tools_raw = registry.list_tools(filter_dict=filter_dict)

    tools = []
    for t in tools_raw:
        tools.append({
            "tool_id": t["tool_id"],
            "name": t["name"],
            "summary": t["summary"],
            "tags": t.get("tags", [])
        })

    return ok({"tools": tools})
