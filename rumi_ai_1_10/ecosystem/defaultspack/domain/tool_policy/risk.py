from __future__ import annotations

from typing import Any

from .models import ToolRisk


_FILE_WRITE_NAME_PARTS = ("write", "create", "update", "patch")
_FILE_DELETE_NAME_PARTS = ("delete",)


def resolve_tool_risk(tool_def: Any, tool_name: str = "") -> str:
    if not isinstance(tool_def, dict):
        return ToolRisk.READ_ONLY.value
    values = {
        str(tool_def.get("category") or "").lower(),
        str(tool_def.get("action_type") or "").lower(),
    }
    _add_collection_values(values, tool_def.get("tags"))
    _add_collection_values(values, tool_def.get("capability_grants"))
    _add_collection_values(values, tool_def.get("capabilities"))
    metadata = tool_def.get("metadata")
    if isinstance(metadata, dict):
        values.update(str(metadata.get(key) or "").lower() for key in ("category", "action_type", "risk"))
        _add_collection_values(values, metadata.get("tags"))
        _add_collection_values(values, metadata.get("capability_grants"))
        _add_collection_values(values, metadata.get("capabilities"))
    execution = tool_def.get("execution")
    if isinstance(execution, dict):
        values.update(str(execution.get(key) or "").lower() for key in ("category", "action_type", "risk", "type"))
        _add_collection_values(values, execution.get("tags"))
        _add_collection_values(values, execution.get("capability_grants"))
        _add_collection_values(values, execution.get("capabilities"))
    name = (tool_name or tool_def.get("name") or tool_def.get("tool_id") or "").lower()

    if "git_push" in values or name.startswith("git_push") or "push" in name:
        return ToolRisk.GIT_PUSH.value
    if "git_write" in values or name.startswith("git_commit") or name.startswith("git_branch") or "commit" in name:
        return ToolRisk.GIT_WRITE.value
    if "shell" in values or "terminal" in values or "exec" in values:
        return ToolRisk.SHELL.value
    if "network" in values or "web" in values or "mcp" in values:
        return ToolRisk.NETWORK.value
    if "computer" in values or "desktop" in values:
        return ToolRisk.COMPUTER.value
    if "browser" in values:
        return ToolRisk.BROWSER.value
    if "credential" in values or "secret" in values:
        return ToolRisk.CREDENTIAL.value
    if "external_message" in values or "message" in values and "send" in name:
        return ToolRisk.EXTERNAL_MESSAGE.value
    if "scheduler_create" in values or "schedule" in name:
        return ToolRisk.SCHEDULER_CREATE.value
    if "pack_install" in values or "install" in name:
        return ToolRisk.PACK_INSTALL.value
    if (
        tool_def.get("write_action") is True
        or values.intersection({"write", "create", "update", "patch"})
        or any(part in name for part in _FILE_WRITE_NAME_PARTS)
    ):
        return ToolRisk.FILE_WRITE.value
    if values.intersection({"delete", "remove", "destructive"}) or any(
        part in name for part in _FILE_DELETE_NAME_PARTS
    ):
        return ToolRisk.FILE_DELETE.value
    return ToolRisk.READ_ONLY.value


def _add_collection_values(values: set[str], raw: Any) -> None:
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        return
    for item in items:
        token = str(item or "").strip().lower()
        if not token:
            continue
        values.add(token)
        normalized = token.replace(".", "_").replace("-", "_").replace(":", "_")
        values.update(part for part in normalized.split("_") if part)
