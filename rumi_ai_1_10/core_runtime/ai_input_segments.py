from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .ai_input_models import PromptSegment, ToolSchemaSegment
from .ai_input_token_estimator import estimate_json_tokens, estimate_tokens
from .profile_graph_models import normalize_profile_graph_selected
from .profile_workspace import ProfileWorkspaceManager, profile_workspace_payload

_DEFAULTSPACK_IMPORT_ROOT = Path(__file__).resolve().parent.parent / "ecosystem" / "defaultspack"
if str(_DEFAULTSPACK_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_DEFAULTSPACK_IMPORT_ROOT))

from ecosystem.defaultspack.domain.prompt.effective import resolve_effective_prompt  # noqa: E402
from ecosystem.defaultspack.domain.tool.registry import ToolRegistry  # noqa: E402
from ecosystem.defaultspack.domain.tool.schema_adapter import (  # noqa: E402
    adapt_tool_definition,
    tool_name_from_definition,
)


def collect_prompt_segments(
    profile: dict[str, Any],
    *,
    workspace_manager: ProfileWorkspaceManager | None = None,
    include_text: bool = True,
) -> list[PromptSegment]:
    profile_id = str(profile.get("profile_id") or "").strip()
    manager = workspace_manager or ProfileWorkspaceManager()
    prompt_ids = _profile_prompt_ids(profile)
    segments: list[PromptSegment] = []
    seen: set[str] = set()
    for index, prompt_id in enumerate(prompt_ids):
        if prompt_id in seen:
            continue
        seen.add(prompt_id)
        text, source, source_type, metadata = _resolve_prompt_text(profile, prompt_id, manager)
        segment_id = f"prompt:{prompt_id}"
        if not text and include_text:
            text = ""
        segments.append(
            PromptSegment(
                id=segment_id,
                text=text if include_text else text,
                source=source,
                source_type=source_type,
                tokens=estimate_tokens(text),
                priority=50 + index,
                enabled=True,
                metadata={
                    "profile_id": profile_id,
                    "prompt_id": prompt_id,
                    "allow_disable": True,
                    **metadata,
                },
            )
        )
    return segments


def collect_tool_schema_segments(profile: dict[str, Any], available_tools: list[dict[str, Any]] | None = None) -> list[ToolSchemaSegment]:
    policy = profile.get("policy") if isinstance(profile.get("policy"), dict) else {}
    allowlist = _tool_allowlist(policy)
    tools = list(available_tools) if isinstance(available_tools, list) else list(ToolRegistry().list_tools())
    segments: list[ToolSchemaSegment] = []
    for tool in sorted(tools, key=lambda item: str(item.get("tool_id") or item.get("name") or "")):
        if not isinstance(tool, dict):
            continue
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        name = str(tool.get("name") or tool_id).strip()
        if not tool_id and not name:
            continue
        adapted = adapt_tool_definition(tool)
        schema = {}
        if isinstance(adapted, dict):
            function_def = adapted.get("function") if isinstance(adapted.get("function"), dict) else {}
            schema = function_def.get("parameters") if isinstance(function_def.get("parameters"), dict) else {}
        if not schema:
            schema = tool.get("schema") if isinstance(tool.get("schema"), dict) else {}
        enabled = not allowlist or tool_id in allowlist or name in allowlist
        segments.append(
            ToolSchemaSegment(
                id=f"tool_schema:{tool_id or name}",
                tool_id=tool_id or name,
                name=name or tool_id,
                schema=dict(schema),
                tokens=estimate_json_tokens(schema),
                enabled=enabled,
                reason="" if enabled else "not_in_tool_allowlist",
                metadata={
                    "allow_disable": True,
                    "source": _tool_source(tool),
                    "provider_name": tool_name_from_definition(tool),
                },
            )
        )
    return segments


def collect_policy_segment(profile: dict[str, Any]) -> PromptSegment:
    policy = profile.get("policy") if isinstance(profile.get("policy"), dict) else {}
    text = json.dumps(policy, ensure_ascii=False, sort_keys=True)
    return PromptSegment(
        id="policy:profile",
        text=text,
        source="profile.policy",
        source_type="profile_policy",
        tokens=estimate_json_tokens(policy),
        priority=10,
        enabled=True,
        metadata={"allow_disable": False},
    )


def _profile_prompt_ids(profile: dict[str, Any]) -> list[str]:
    metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    selected = normalize_profile_graph_selected(metadata.get("selected"))
    selected_prompts = selected.get("prompts") if isinstance(selected.get("prompts"), list) else []
    candidates: list[Any] = [
        *selected_prompts,
        profile.get("system_prompt_id"),
        profile.get("default_prompt_id"),
        metadata.get("system_prompt_id"),
        metadata.get("default_prompt_id"),
        "default_chat",
    ]
    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        prompt_id = str(item or "").strip()
        if not prompt_id or prompt_id in seen:
            continue
        seen.add(prompt_id)
        result.append(prompt_id)
    return result


def _resolve_prompt_text(
    profile: dict[str, Any],
    prompt_id: str,
    workspace_manager: ProfileWorkspaceManager,
) -> tuple[str, str, str, dict[str, Any]]:
    profile_id = str(profile.get("profile_id") or "").strip()
    workspace = profile_workspace_payload(workspace_manager.paths_for_profile(profile_id)) if profile_id else {}
    payload = {
        "profile_id": profile_id,
        "base_pack": profile.get("base_pack") or "defaultspack",
        "system_prompt_id": prompt_id,
        "default_prompt_id": profile.get("default_prompt_id"),
        "workspace": workspace,
    }
    try:
        effective = resolve_effective_prompt(payload)
    except Exception:
        return "", f"profile.prompt:{prompt_id}", "unresolved", {"prompt_resolution_error": True}
    text = str(effective.get("final_content") or effective.get("content") or "")
    return (
        text,
        str(effective.get("source") or f"profile.prompt:{prompt_id}"),
        str(effective.get("source_type") or "profile_prompt"),
        {
            "resolved_prompt_id": effective.get("prompt_id"),
            "source_chain": effective.get("source_chain") if isinstance(effective.get("source_chain"), list) else [],
        },
    )


def _tool_allowlist(policy: dict[str, Any]) -> set[str]:
    value = policy.get("tool_allowlist") or policy.get("enabled_tools") or policy.get("allowed_tools")
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _tool_source(tool: dict[str, Any]) -> str:
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    return str(metadata.get("source_pack_id") or tool.get("source_pack_id") or metadata.get("source") or "")
