"""Mobile tool catalog facade."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from blocks.tool.invoke import run as invoke_tool
from domain.function_runtime.bridge import invoke_defaultspack_function
from domain.mobile.tools import mobile_agent_template, mobile_tool_records, mobile_tool_summary
from domain.tool.registry import ToolRegistry


def _merged(input_data):
    if not isinstance(input_data, dict):
        return {}
    merged = {}
    for key in ("body", "params", "query_params", "query"):
        value = input_data.get(key)
        if isinstance(value, dict):
            merged.update(value)
    for key, value in input_data.items():
        if key in {"body", "params", "query_params", "query"}:
            continue
        merged[key] = value
    return merged


def run(input_data, context=None):
    payload = _merged(input_data)
    if str(payload.get("action") or "").strip().lower() == "invoke":
        return _invoke(payload, context if isinstance(context, dict) else {})

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


def _invoke(payload, context):
    tool_name = str(
        payload.get("tool_name") or payload.get("tool_id") or payload.get("name") or ""
    ).strip()
    if not tool_name:
        return error("tool_name is required", "MISSING_PARAM")

    arguments = payload.get("arguments")
    if arguments is None:
        arguments = payload.get("args")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return error("arguments must be an object", "INVALID_INPUT")

    if _is_defaultspack_tool_function(tool_name):
        result = invoke_defaultspack_function(
            tool_name,
            arguments,
            _mobile_invoke_context(context),
            principal_id="defaultspack",
        )
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        return ok(
            {
                "tool_name": tool_name,
                "function_id": tool_name,
                "result": result.get("data") if isinstance(result, dict) else result,
                "is_error": False,
                "execution_location": "pc",
                "runtime": "defaultspack_function",
            }
        )

    invoke_context = dict(context or {})
    invoke_context.setdefault("_source_component", "defaultspack:mobile:tools")
    invoke_context.setdefault("_mobile_tool_delegate", True)
    return invoke_tool(
        {
            "tool_name": tool_name,
            "arguments": arguments,
            **(
                {"context": payload.get("context")}
                if isinstance(payload.get("context"), dict)
                else {}
            ),
        },
        invoke_context,
    )


def _mobile_invoke_context(context):
    invoke_context = dict(context or {})
    invoke_context.setdefault("_source_component", "defaultspack:mobile:tools")
    invoke_context.setdefault("_mobile_tool_delegate", True)
    return invoke_context


def _is_defaultspack_tool_function(function_id):
    normalized = str(function_id or "").strip()
    if not normalized or "/" in normalized or "\\" in normalized:
        return False
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "functions"
        / normalized
        / "manifest.json"
    )
    try:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    tags = manifest.get("tags") if isinstance(manifest, dict) else []
    if not isinstance(tags, list):
        return False
    normalized_tags = {str(tag).strip() for tag in tags}
    return "tool" in normalized_tags or "agent" in normalized_tags
