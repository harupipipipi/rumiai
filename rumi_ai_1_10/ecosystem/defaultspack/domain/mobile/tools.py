from __future__ import annotations

from typing import Any

from domain.tool.permission_resolver import ToolPermissionResolver
from domain.tool.service_catalog import ToolServiceCatalog


MOBILE_COMPATIBLE_TAG = "mobile-compatible"
MOBILE_FLUTTER_TAG = "mobile-flutter"
MOBILE_IOS_TAG = "mobile-ios"
MOBILE_ANDROID_TAG = "mobile-android"
MOBILE_SWIFT_NATIVE_TAG = "mobile-swift-native"
MOBILE_KOTLIN_NATIVE_TAG = "mobile-kotlin-native"
MOBILE_PC_DELEGATED_TAG = "pc-delegated"
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
        "platform_tags": {
            "flutter": MOBILE_FLUTTER_TAG,
            "ios": MOBILE_IOS_TAG,
            "android": MOBILE_ANDROID_TAG,
            "swift": MOBILE_SWIFT_NATIVE_TAG,
            "kotlin": MOBILE_KOTLIN_NATIVE_TAG,
            "pc_delegated": MOBILE_PC_DELEGATED_TAG,
        },
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
        plan = _mobile_port_plan(service_id, tags, tool)
        return {
            "compatible": False,
            "available": False,
            "execution_location": "unsupported",
            "unavailable_reason": blocked_reason,
            "platforms": plan["platforms"],
            "runtime_layers": plan["runtime_layers"],
            "native_layers": plan["native_layers"],
            "requires_pc": True,
            "requires_mobile_approval": plan["requires_mobile_approval"],
            "implementation_status": plan["implementation_status"],
            "tags": _platform_tags(plan, pc_delegated=True),
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
        "platforms": ["ios", "android"],
        "runtime_layers": ["flutter", "pc-defaultspack-runtime"],
        "native_layers": [],
        "requires_pc": True,
        "requires_mobile_approval": False,
        "implementation_status": "pc_delegated",
        "tags": [
            MOBILE_COMPATIBLE_TAG,
            MOBILE_FLUTTER_TAG,
            MOBILE_IOS_TAG,
            MOBILE_ANDROID_TAG,
            MOBILE_PC_DELEGATED_TAG,
        ],
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


def _mobile_port_plan(service_id: str, tags: set[str], tool: dict[str, Any]) -> dict[str, Any]:
    tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip().lower()
    if tool_id in {"media_clipboard_read", "media_clipboard_write"}:
        return {
            "platforms": ["ios", "android"],
            "runtime_layers": ["flutter", "ios-swift", "android-kotlin"],
            "native_layers": [
                "ios:Swift UIPasteboard",
                "android:Kotlin ClipboardManager",
            ],
            "requires_mobile_approval": True,
            "implementation_status": "feasible_needs_mobile_approval_ui",
        }
    if "media" in tags or tool_id.startswith(("audio_", "image_", "ocr_")):
        return {
            "platforms": ["ios", "android"],
            "runtime_layers": ["flutter", "ios-swift", "android-kotlin", "provider"],
            "native_layers": [
                "ios:Swift media/photo permission bridge",
                "android:Kotlin media permission bridge",
            ],
            "requires_mobile_approval": True,
            "implementation_status": "feasible_needs_picker_permission_or_provider",
        }
    if service_id == "browser" or "browser" in tags:
        return {
            "platforms": [],
            "runtime_layers": ["pc-browser-session"],
            "native_layers": [],
            "requires_mobile_approval": False,
            "implementation_status": "pc_browser_session_only",
        }
    if tags & {"desktop", "computer", "computer_use", "workspace", "sandbox", "terminal", "agent_os"}:
        return {
            "platforms": [],
            "runtime_layers": ["pc-defaultspack-runtime"],
            "native_layers": [],
            "requires_mobile_approval": False,
            "implementation_status": "pc_only",
        }
    if "agent" in tags:
        return {
            "platforms": [],
            "runtime_layers": ["pc-agent-service"],
            "native_layers": [],
            "requires_mobile_approval": False,
            "implementation_status": "pc_agent_runtime_only",
        }
    return {
        "platforms": [],
        "runtime_layers": ["pc-defaultspack-runtime"],
        "native_layers": [],
        "requires_mobile_approval": False,
        "implementation_status": "pc_delegation_required",
    }


def _platform_tags(plan: dict[str, Any], *, pc_delegated: bool) -> list[str]:
    platforms = {str(item).strip().lower() for item in plan.get("platforms") or []}
    runtime_layers = {str(item).strip().lower() for item in plan.get("runtime_layers") or []}
    tags: list[str] = []
    if "flutter" in runtime_layers or "dart" in runtime_layers:
        tags.append(MOBILE_FLUTTER_TAG)
    if "ios" in platforms:
        tags.append(MOBILE_IOS_TAG)
    if "android" in platforms:
        tags.append(MOBILE_ANDROID_TAG)
    if any("swift" in layer for layer in runtime_layers):
        tags.append(MOBILE_SWIFT_NATIVE_TAG)
    if any("kotlin" in layer for layer in runtime_layers):
        tags.append(MOBILE_KOTLIN_NATIVE_TAG)
    if pc_delegated:
        tags.append(MOBILE_PC_DELEGATED_TAG)
    return tags


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
