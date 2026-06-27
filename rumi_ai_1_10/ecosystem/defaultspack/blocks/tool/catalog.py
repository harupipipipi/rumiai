import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.mobile.tools import annotate_mobile_tool_record
from domain.tool.permission_resolver import ToolPermissionResolver
from domain.tool.registry import ToolRegistry
from domain.tool.service_catalog import ToolServiceCatalog


def run(input_data, context):
    registry = ToolRegistry()
    tools = registry.list_tools()
    catalog = ToolServiceCatalog(tools)
    resolver = ToolPermissionResolver()
    records = []
    for tool in tools:
        record = annotate_mobile_tool_record(catalog.compact_record(tool), tool)
        records.append(
            {
                **record,
                "permission": resolver.resolve(tool, context=context if isinstance(context, dict) else {}),
            }
        )
    return ok(
        {
            "services": catalog.services(),
            "tools": records,
            "count": len(records),
        }
    )
