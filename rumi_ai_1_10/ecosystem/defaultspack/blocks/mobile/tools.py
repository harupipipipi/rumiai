"""Mobile tool catalog facade."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.mobile.tools import mobile_agent_template, mobile_tool_records, mobile_tool_summary
from domain.tool.registry import ToolRegistry


def run(input_data, context=None):
    del input_data
    tools = ToolRegistry().list_tools()
    records = mobile_tool_records(tools, context=context if isinstance(context, dict) else {})
    return ok(
        {
            "agent_template": mobile_agent_template(),
            "tools": records,
            "summary": mobile_tool_summary(records),
            "count": len(records),
        }
    )
