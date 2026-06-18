import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.chat.tool_selection_trace import ToolSelectionTraceStore


def run(input_data, context):
    trace_id = str((input_data or {}).get("trace_id") or "").strip()
    if not trace_id:
        return error("trace_id is required", "INVALID_INPUT")
    trace = ToolSelectionTraceStore().get(trace_id)
    if trace is None:
        return error("Tool selection trace not found", "NOT_FOUND")
    return ok(trace)
