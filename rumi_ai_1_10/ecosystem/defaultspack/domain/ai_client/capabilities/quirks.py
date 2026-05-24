from __future__ import annotations

from typing import Any


DEFAULT_QUIRKS: dict[str, Any] = {
    "max_tokens_name": "max_tokens",
    "max_completion_tokens_name": "max_completion_tokens",
    "drop_reasoning_when_none": True,
    "reasoning_effort_values": ["low", "medium", "high"],
    "unsupported_params": [],
    "tool_name_regex": r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$",
    "tool_name_max_length": 128,
    "tool_schema_subset": "json_schema",
    "supports_strict_json_schema": False,
    "supports_stream_usage": True,
    "requires_system_as_first_message": False,
    "system_role_mapping": "system",
    "developer_role_mapping": "system",
    "supports_image_data_url": True,
    "supports_provider_file_id": False,
    "supports_builtin_tools": False,
    "supports_mcp_tools": False,
}


def merged_quirks(provider_quirks: dict[str, Any] | None, model_quirks: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **DEFAULT_QUIRKS,
        **(provider_quirks if isinstance(provider_quirks, dict) else {}),
        **(model_quirks if isinstance(model_quirks, dict) else {}),
    }
