from __future__ import annotations

from typing import Any

from domain.tool.permission_resolver import ToolPermissionResolver
from domain.tool.service_catalog import ToolServiceCatalog


MOBILE_COMPATIBLE_TAG = "mobile-compatible"
MOBILE_AGENT_TEMPLATE = {
    "template_id": "rumi.composer.default",
    "ai_input_id": "rumi.composer.default:default_ai_input",
    "tool_policy_id": "rumi.composer.default:default_tools",
}

_HOST_BOUND_SERVICES = {
    "browser",
    "computer",
    "terminal",
    "coding",
    "files",
    "artifacts",
    "mcp",
}
_HOST_BOUND_TAGS = {
    "agent_os",
    "browser",
    "coding",
    "computer_use",
    "desktop",
    "file",
    "files",
    "host",
    "mcp",
    "sandbox",
    "shell",
    "terminal",
    "workspace",
}


def mobile_agent_template() -> dict[str, str]:
    return dict(MOBILE_AGENT_TEMPLATE)


def annotate_mobile_tool_record(record: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(record)
    compatibility = mobile_tool_compatibility(tool, record)
    tags = _ordered_tags([*list(annotated.get("tags") or []), *(compatibility.get("tags") or [])])
    annotated["tags"] = tags
    annotated["mobile"] = compatibility
    annotated["mobile_compatible"] = bool(compatibility.get("compatible"))
    annotated["mobile_unavailable_reason"] = str(compatibility.get("unavailable_reason") or "")
    annotated["execution_location"] = str(compatibility.get("execution_location") or "pc")
    return annotated


def mobile_tool_records(
    tools: list[dict[str, Any]],
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    catalog = ToolServiceCatalog(tools)
    resolver = ToolPermissionResolver()
    request_context = context if isinstance(context, dict) else {}
    records: list[dict[str, Any]] = []
    for tool in tools:
        record = catalog.compact_record(tool)
        record["permission"] = resolver.resolve(tool, context=request_context)
        records.append(annotate_mobile_tool_record(record, tool))
    return records


def mobile_tool_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    compatible = [record for record in records if record.get("mobile_compatible")]
    unavailable = [record for record in records if not record.get("mobile_compatible")]
    return {
        "compatible_count": len(compatible),
        "unavailable_count": len(unavailable),
        "compatible_tag": MOBILE_COMPATIBLE_TAG,
        "agent_template": mobile_agent_template(),
    }


def mobile_tool_compatibility(tool: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = record if isinstance(record, dict) else ToolServiceCatalog.compact_record(tool)
    service_id = str(record.get("service_id") or "").strip().lower()
    tags = _tag_set(record.get("tags")) | _tag_set(tool.get("tags"))
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    tags |= _tag_set(metadata.get("tags"))

    blocked_reason = _blocked_reason(service_id, tags, tool)
    connection_status = str(record.get("connection_status") or "").strip().lower()
    if blocked_reason:
        return {
            "compatible": False,
            "available": False,
            "execution_location": "unsupported",
            "unavailable_reason": blocked_reason,
            "tags": [],
            "agent_template": mobile_agent_template(),
        }
    unavailable_reason = ""
    if connection_status == "setup_required":
        unavailable_reason = "PC側で接続またはAPI key設定が必要です。"
    elif connection_status in {"unavailable", "error"}:
        unavailable_reason = "PC側でこのtoolを利用できません。"
    return {
        "compatible": True,
        "available": not unavailable_reason,
        "execution_location": "pc",
        "unavailable_reason": unavailable_reason,
        "tags": [MOBILE_COMPATIBLE_TAG],
        "agent_template": mobile_agent_template(),
    }


def _blocked_reason(service_id: str, tags: set[str], tool: dict[str, Any]) -> str:
    if service_id in _HOST_BOUND_SERVICES:
        return "スマホ単体ではPC/desktop/terminal/workspace系toolを実行できません。PC接続時にPC側runtimeで実行してください。"
    if tags & _HOST_BOUND_TAGS:
        return "このtoolはPC側のhost runtimeまたはworkspaceに依存するため、スマホ単体では実行できません。"
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    runtime_caps = tool.get("requires_runtime_capabilities") or metadata.get("requires_runtime_capabilities")
    if isinstance(runtime_caps, list) and runtime_caps:
        return "このtoolはruntime capabilityが必要なため、スマホ単体では実行できません。"
    if tool.get("enabled") is False:
        return "このtoolはPC側で無効化されています。"
    return ""


def _tag_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {part.strip().lower() for part in value.replace(",", " ").split() if part.strip()}
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value if str(item or "").strip()}
    return set()


def _ordered_tags(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value or "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        output.append(tag)
    return output
