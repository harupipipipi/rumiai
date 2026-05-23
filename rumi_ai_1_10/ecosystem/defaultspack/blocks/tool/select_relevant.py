import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.chat.tool_recommender import search_tools
from domain.tool.registry import ToolRegistry


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    query = str(data.get("query") or message.get("content") or message.get("text") or "").strip()
    tools = data.get("tools")
    if tools is None and isinstance(message, dict):
        tools = message.get("tools") or message.get("available_tools")
    if not isinstance(tools, list):
        tools = ToolRegistry().list_tools()
    try:
        limit = int(data.get("limit", 8))
    except (TypeError, ValueError):
        limit = 8
    matches = search_tools(query, tools, limit=max(1, min(24, limit)), threshold=0.06)
    selected_ids = {item["tool_id"] for item in matches}
    selected_tools = [tool for tool in tools if str(tool.get("tool_id") or tool.get("name") or "") in selected_ids]
    return ok(
        {
            "profile_id": data.get("profile_id"),
            "tools": selected_tools,
            "matches": matches,
            "selection_reason": "vector_docs_schema_skill_metadata",
        }
    )
