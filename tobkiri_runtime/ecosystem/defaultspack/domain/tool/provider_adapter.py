from __future__ import annotations

import json
from typing import Any

from domain.tool.name_mapping import ToolNameMapping, build_tool_name_mapping
from domain.tool.protocol import ProviderToolDefinition, RumiToolCall, RumiToolDefinition
from domain.tool.schema_adapter import provider_tool_parameters, tool_name_from_definition


def rumi_tool_from_definition(tool: Any) -> RumiToolDefinition:
    if isinstance(tool, RumiToolDefinition):
        return tool
    if not isinstance(tool, dict):
        return RumiToolDefinition(name=str(tool or "tool"))
    function_value = tool.get("function")
    function_def: dict[str, Any] = function_value if isinstance(function_value, dict) else {}
    name = str(function_def.get("name") or tool_name_from_definition(tool) or "").strip()
    schema_value = tool.get("schema")
    schema: dict[str, Any] = schema_value if isinstance(schema_value, dict) else {}
    schema_parameters = schema.get("parameters")
    parameters = function_def.get("parameters") or (schema_parameters if isinstance(schema_parameters, dict) else schema)
    return RumiToolDefinition(
        name=name,
        description=str(function_def.get("description") or tool.get("summary") or tool.get("description") or ""),
        parameters=provider_tool_parameters(parameters),
        metadata={key: value for key, value in tool.items() if key not in {"function", "schema"}},
    )


def adapt_rumi_tools_to_provider_tools(
    tools: list[Any],
    provider_capabilities: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], ToolNameMapping, list[ProviderToolDefinition]]:
    caps = provider_capabilities if isinstance(provider_capabilities, dict) else {}
    quirks = caps.get("quirks") if isinstance(caps.get("quirks"), dict) else {}
    rumi_tools = [rumi_tool_from_definition(tool) for tool in tools or []]
    mapping = build_tool_name_mapping([tool.name for tool in rumi_tools], quirks)
    provider_tools: list[dict[str, Any]] = []
    definitions: list[ProviderToolDefinition] = []
    for tool in rumi_tools:
        alias = mapping.alias_for(tool.name)
        payload: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": alias,
                "description": tool.description,
                "parameters": provider_tool_parameters(tool.parameters),
            },
        }
        provider_tools.append(payload)
        definitions.append(ProviderToolDefinition(name=tool.name, provider_alias=alias, provider_payload=payload, original=tool))
    return provider_tools, mapping, definitions


def decode_provider_tool_call_to_rumi_tool_call(tool_call: dict[str, Any], mapping: ToolNameMapping | None = None) -> RumiToolCall:
    function_value = tool_call.get("function")
    function_def: dict[str, Any] = function_value if isinstance(function_value, dict) else {}
    alias = str(function_def.get("name") or tool_call.get("name") or "").strip()
    name = mapping.original_for(alias) if mapping is not None else alias
    args = function_def.get("arguments", tool_call.get("arguments", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            pass
    return RumiToolCall(
        id=str(tool_call.get("id") or tool_call.get("tool_call_id") or ""),
        name=name,
        arguments=args,
        provider_alias=alias,
    )
