import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    tools = data.get("tools")
    if tools is None and isinstance(message, dict):
        tools = message.get("tools") or message.get("available_tools")
    if not isinstance(tools, list):
        tools = []
    return ok({"profile_id": data.get("profile_id"), "tools": tools, "selection_reason": "profile_workspace_default"})
