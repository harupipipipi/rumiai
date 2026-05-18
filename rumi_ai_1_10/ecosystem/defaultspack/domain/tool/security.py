from __future__ import annotations

from typing import Any


TRUSTED_TOOL_PACK_IDS = {"defaultspack", "rumi_default_tools_pack"}
SUPPORTED_AUTHORABLE_EXECUTION_TYPES = {"rumi_function", "capability", "mcp"}
TRUSTED_LEGACY_EXECUTION_TYPES = {"local", "handler", "dynamic", "prompt"}
VALID_RISKS = {"low", "medium", "high"}

_UNSAFE_ACTION_TYPES = {
    "create",
    "delete",
    "desktop",
    "execute",
    "file_write",
    "patch",
    "push",
    "shell",
    "update",
    "write",
}
_UNSAFE_CATEGORIES = {
    "computer",
    "desktop",
    "file_write",
    "filesystem_write",
    "git",
    "shell",
}
_UNSAFE_TEXT_MARKERS = (
    "chmod",
    "commit",
    "create",
    "delete",
    "desktop",
    "execute",
    "file write",
    "filesystem",
    "git push",
    "modify",
    "patch",
    "remove",
    "shell",
    "subprocess",
    "terminal",
    "update",
    "write",
    "writing",
)


def source_pack_id_from_tool(tool_def: dict[str, Any]) -> str:
    metadata = tool_def.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("source_pack_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = tool_def.get("source_pack_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def source_pack_id_from_manifest(manifest: dict[str, Any], fallback: str = "") -> str:
    for source in (
        manifest,
        manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {},
        manifest.get("config") if isinstance(manifest.get("config"), dict) else {},
    ):
        value = source.get("source_pack_id") if isinstance(source, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(fallback or "").strip()


def is_trusted_tool(tool_def: dict[str, Any]) -> bool:
    if source_pack_id_from_tool(tool_def) in TRUSTED_TOOL_PACK_IDS:
        return True
    metadata = tool_def.get("metadata")
    if isinstance(metadata, dict) and metadata.get("trusted") is True:
        return True
    return bool(tool_def.get("trusted") is True)


def is_trusted_pack_id(pack_id: str) -> bool:
    return str(pack_id or "").strip() in TRUSTED_TOOL_PACK_IDS


def execution_type(tool_def: dict[str, Any]) -> str:
    execution = tool_def.get("execution")
    if not isinstance(execution, dict):
        return ""
    return str(execution.get("type") or "").strip().lower()


def legacy_execution_requires_trust(exec_type: str) -> bool:
    return str(exec_type or "").strip().lower() in TRUSTED_LEGACY_EXECUTION_TYPES


def unsupported_execution_reason(tool_def: dict[str, Any]) -> str | None:
    exec_type = execution_type(tool_def) or "local"
    execution = tool_def.get("execution") if isinstance(tool_def.get("execution"), dict) else {}
    if exec_type in SUPPORTED_AUTHORABLE_EXECUTION_TYPES:
        if exec_type == "rumi_function" and not str(execution.get("qualified_name") or "").strip():
            return "rumi_function tools must declare execution.qualified_name"
        if exec_type == "capability" and not str(execution.get("permission_id") or "").strip():
            return "capability tools must declare execution.permission_id"
        if exec_type == "mcp":
            if not str(execution.get("server_name") or "").strip():
                return "mcp tools must declare execution.server_name"
        return None
    if legacy_execution_requires_trust(exec_type) and is_trusted_tool(tool_def):
        return None
    return "execution type '{}' is only allowed for trusted first-party tools".format(exec_type)


def normalize_risk(raw_risk: Any, tool_def: dict[str, Any], trusted: bool) -> tuple[str, bool]:
    risk = str(raw_risk or "").strip().lower()
    known = risk in VALID_RISKS
    if known:
        return risk, False
    if trusted and not appears_write_or_execute_capable(tool_def):
        return "low", True
    return "high", True


def requires_approval_for_security(tool_def: dict[str, Any]) -> bool:
    risk = str(_tool_value(tool_def, "risk") or "").strip().lower()
    return (
        bool(_tool_value(tool_def, "requires_approval"))
        or risk == "high"
        or appears_write_or_execute_capable(tool_def)
    )


def appears_write_or_execute_capable(tool_def: dict[str, Any]) -> bool:
    if bool(_tool_value(tool_def, "write_action")):
        return True
    action_type = str(_tool_value(tool_def, "action_type") or "").strip().lower()
    if action_type in _UNSAFE_ACTION_TYPES:
        return True
    category = str(_tool_value(tool_def, "category") or "").strip().lower()
    if category in _UNSAFE_CATEGORIES:
        return True
    tags = tool_def.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if str(tag or "").strip().lower() in _UNSAFE_ACTION_TYPES | _UNSAFE_CATEGORIES:
                return True
    return _unsafe_text_seen(
        tool_def.get("tool_id"),
        tool_def.get("name"),
        tool_def.get("summary"),
        tool_def.get("description"),
        _schema_text(tool_def.get("schema")),
        _schema_text(tool_def.get("execution")),
    )


def _tool_value(tool_def: dict[str, Any], key: str) -> Any:
    if key in tool_def:
        return tool_def.get(key)
    metadata = tool_def.get("metadata")
    if isinstance(metadata, dict) and key in metadata:
        return metadata.get(key)
    execution = tool_def.get("execution")
    if isinstance(execution, dict) and key in execution:
        return execution.get(key)
    return None


def _schema_text(value: Any) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(str(key))
            parts.append(_schema_text(item))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(_schema_text(item) for item in value)
    if isinstance(value, str):
        return value
    return ""


def _unsafe_text_seen(*values: Any) -> bool:
    text = " ".join(str(value or "").replace("_", " ").replace("-", " ").lower() for value in values)
    return any(marker in text for marker in _UNSAFE_TEXT_MARKERS)
