from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path
from typing import Any

from core_runtime.profile_paths import active_profile_id
from core_runtime.ai_input_token_estimator import estimate_tokens
from core_runtime.ai_input_trace_store import AiInputTraceStore
from core_runtime.profile_workspace import ProfileWorkspaceManager, profile_workspace_payload, validate_profile_id

from .effective import resolve_effective_prompt, validate_prompt_template
from .manager import get_manager
from .prompt_compactor import compact_prompt
from .prompt_linter import lint_prompt
from ..skill_trigger import RuntimeSkillTriggerService
from .usage import active_prompt_summary, append_runtime_prompt_segment, prompt_usage_from_trace


_SAFE_PROMPT_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def load_prompt_studio(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    prompt_id = str(data.get("prompt_id") or data.get("name") or "").strip()
    active = _studio_active_summary(profile_id, data)
    prompts = _merge_prompt_records([*_prompt_records(profile_id), *_segment_records_from_active(active.get("segments", []))])
    prompts = _annotate_prompt_records(prompts, active.get("segments", []))
    if not prompt_id and prompts:
        active_prompt = next((item for item in prompts if item.get("activation_state") == "active"), None)
        prompt_id = str((active_prompt or prompts[0]).get("name") or (active_prompt or prompts[0]).get("id") or "")
    selected = _prompt_detail(profile_id, prompt_id, prompts) if prompt_id else None
    return {
        "profile_id": profile_id,
        "profile_workspace": profile_workspace_payload(ProfileWorkspaceManager().paths_for_profile(profile_id)),
        "prompts": prompts,
        "selected_prompt": selected,
        "active_summary": active.get("summary", {}),
        "traces": [],
    }


def save_prompt(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    prompt_id = _clean_prompt_id(data.get("prompt_id") or data.get("name"))
    body = str(data.get("body") if data.get("body") is not None else data.get("content") or "")
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    force_override = bool(data.get("create_override") or data.get("override"))
    manager = get_manager()
    existing = manager.get_prompt_by_name(prompt_id) or manager.get_prompt(prompt_id)
    read_only = bool(existing and existing.get("read_only"))
    existing_description = str((existing or {}).get("description") or "")
    existing_variables = (
        list((existing or {}).get("variables") or [])
        if isinstance((existing or {}).get("variables"), list)
        else []
    )
    description = str(data.get("description") or "") if "description" in data else existing_description
    variables = data.get("variables") if "variables" in data and isinstance(data.get("variables"), list) else existing_variables

    if force_override or read_only or existing is None:
        return create_profile_override(
            {
                "profile_id": profile_id,
                "prompt_id": prompt_id,
                "body": body,
                "description": description,
                "variables": variables,
                "metadata": metadata,
                "reason": data.get("reason") or "manual_save",
            }
        )

    _record_version(
        profile_id=profile_id,
        prompt_id=prompt_id,
        scope="user_prompt",
        previous_body=str(existing.get("body") or existing.get("content") or ""),
        next_body=body,
        reason=str(data.get("reason") or "manual_save"),
        metadata={"source_type": "user_data"},
    )
    updated = manager.update_prompt(
        str(existing.get("name") or prompt_id),
        {
            "body": body,
            "content": body,
            "description": description,
            "variables": variables,
            "metadata": {
                **dict(existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}),
                **metadata,
            },
        },
    )
    return {"action": "saved", "profile_id": profile_id, "prompt": updated, "source_type": "user_data"}


def create_profile_override(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    prompt_id = _clean_prompt_id(data.get("prompt_id") or data.get("name"))
    body = data.get("body")
    if body is None:
        existing = get_manager().get_prompt_by_name(prompt_id) or get_manager().get_prompt(prompt_id)
        body = str((existing or {}).get("body") or (existing or {}).get("content") or "")
    body = str(body or "")
    path = _profile_override_path(profile_id, prompt_id)
    previous_exists = path.is_file()
    previous_body = path.read_text(encoding="utf-8") if previous_exists else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    version = _record_version(
        profile_id=profile_id,
        prompt_id=prompt_id,
        scope="profile_override",
        previous_body=previous_body,
        next_body=body,
        reason=str(data.get("reason") or "manual_override"),
        metadata={
            **(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}),
            "source_type": "profile_override",
            "path": str(path),
            "previous_exists": previous_exists,
            "description": data.get("description") or "",
            "variables": data.get("variables") if isinstance(data.get("variables"), list) else [],
        },
    )
    return {
        "action": "override_saved",
        "profile_id": profile_id,
        "prompt_id": prompt_id,
        "path": str(path),
        "prompt": _profile_override_record(profile_id, path),
        "version": version,
    }


def diff_prompt(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    prompt_id = _clean_prompt_id(data.get("prompt_id") or data.get("name"))
    base = data.get("base")
    draft = data.get("draft")
    if base is None:
        base = _base_prompt_body(prompt_id)
    if draft is None:
        draft = _effective_prompt_body(profile_id, prompt_id)
    lines = list(
        difflib.unified_diff(
            str(base or "").splitlines(),
            str(draft or "").splitlines(),
            fromfile=f"{prompt_id}:base",
            tofile=f"{prompt_id}:draft",
            lineterm="",
        )
    )
    return {"profile_id": profile_id, "prompt_id": prompt_id, "diff": "\n".join(lines), "changed": bool(lines)}


def prompt_versions(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    prompt_id = _clean_prompt_id(data.get("prompt_id") or data.get("name"))
    versions = []
    for scope in ("profile_override", "user_prompt"):
        versions.extend(_list_versions(profile_id, prompt_id, scope))
    versions.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {"profile_id": profile_id, "prompt_id": prompt_id, "versions": versions, "count": len(versions)}


def rollback_prompt(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    prompt_id = _clean_prompt_id(data.get("prompt_id") or data.get("name"))
    version_id = str(data.get("version_id") or data.get("version") or "").strip()
    if not version_id:
        raise ValueError("version_id is required")
    version = _load_version(profile_id, prompt_id, version_id)
    if version is None:
        raise ValueError(f"Version not found: {version_id}")
    scope = str(version.get("scope") or "profile_override")
    use_previous = bool(data.get("use_previous", True))
    body = str(version.get("previous_body") if use_previous else version.get("next_body") or "")
    if scope == "user_prompt":
        prompt = get_manager().update_prompt(prompt_id, {"body": body, "content": body})
        return {"action": "rolled_back", "profile_id": profile_id, "prompt_id": prompt_id, "scope": scope, "prompt": prompt}
    path = _profile_override_path(profile_id, prompt_id)
    path_was_file = path.is_file()
    previous = path.read_text(encoding="utf-8") if path_was_file else ""
    version_metadata = version.get("metadata") if isinstance(version.get("metadata"), dict) else {}
    if use_previous and version_metadata.get("previous_exists") is False:
        if path.is_file():
            path.unlink()
        _record_version(
            profile_id=profile_id,
            prompt_id=prompt_id,
            scope="profile_override",
            previous_body=previous,
            next_body="",
            reason=f"rollback:{version_id}",
            metadata={
                "rolled_back_from": version_id,
                "previous_exists": path_was_file,
                "removed_override": True,
            },
        )
        return {
            "action": "rolled_back",
            "profile_id": profile_id,
            "prompt_id": prompt_id,
            "scope": scope,
            "path": str(path),
            "removed_override": True,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _record_version(
        profile_id=profile_id,
        prompt_id=prompt_id,
        scope="profile_override",
        previous_body=previous,
        next_body=body,
        reason=f"rollback:{version_id}",
        metadata={"rolled_back_from": version_id},
    )
    return {"action": "rolled_back", "profile_id": profile_id, "prompt_id": prompt_id, "scope": scope, "path": str(path)}


def lint_prompt_text(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    text = str(data.get("prompt") or data.get("text") or data.get("body") or "")
    return lint_prompt(text, token_budget=data.get("token_budget"))


def compact_prompt_text(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    text = str(data.get("prompt") or data.get("text") or data.get("body") or "")
    return compact_prompt(text, target_chars=data.get("target_chars"))


def test_prompt_input(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    prompt_id = str(data.get("prompt_id") or data.get("name") or "").strip()
    user_text = str(data.get("user_text") or data.get("message") or data.get("input") or "").strip()
    conversation_id = str(data.get("conversation_id") or "").strip()
    model_profile_id = str(data.get("model_profile_id") or data.get("model") or "").strip()
    model = str(data.get("model") or model_profile_id or "").strip()
    selected_tools = _string_list(data.get("selected_tools") if "selected_tools" in data else data.get("tools"))
    prompt_body = str(
        data.get("draft")
        if data.get("draft") is not None
        else _effective_prompt_body(profile_id, prompt_id) if prompt_id else ""
    )
    request_context = data.get("request_context") if isinstance(data.get("request_context"), dict) else {}
    active = active_prompt_summary(
        {
            "profile_id": profile_id,
            "conversation_id": conversation_id,
            "include_text": bool(data.get("include_text", False)),
            "request_context": {
                **request_context,
                "message": user_text,
                "user_text": user_text,
                **({"model": model} if model else {}),
                "studio_test": True,
            },
        }
    )
    usage = dict(active.get("summary") if isinstance(active.get("summary"), dict) else {})
    tool_catalog = _tool_catalog(data, usage.get("segments", []))
    selected_tool_records = _selected_tool_records(tool_catalog, selected_tools)
    skill_eval = _evaluate_studio_skills(data, user_text=user_text, selected_tools=selected_tools)
    matched_skills = skill_eval.get("matched", []) if isinstance(skill_eval, dict) else []
    skill_instructions = str(skill_eval.get("instructions") or "").strip() if isinstance(skill_eval, dict) else ""
    if skill_instructions:
        usage = append_runtime_prompt_segment(
            usage,
            {
                "id": "skill:studio.test.matched_instructions",
                "edge_id": "",
                "prompt_id": "studio.test.matched_instructions",
                "label": "Studio matched skill instructions",
                "kind": "skill",
                "port": "system",
                "status": "active",
                "source": "PromptStudioTestBench",
                "source_type": "skill",
                "tokens": int(estimate_tokens(skill_instructions)),
                "reason": "Studio test input matched skill trigger words, explicit skill mentions, or selected tool scope.",
                "allow_disable": False,
                "editable": False,
                "readonly_reason": "Studio test segments are generated for inspection only.",
                "preview": " ".join(skill_instructions.split())[:280],
                "text": skill_instructions,
                "metadata": {"matched_skills": matched_skills, "studio_test": True},
            },
        )
    tool_candidates = _tool_candidates(prompt_body=prompt_body, user_text=user_text, tools=tool_catalog)
    segments = usage.get("segments") if isinstance(usage.get("segments"), list) else []
    selected_tool_segments = _tool_segments_for_ids(segments, selected_tools)
    candidate_tool_segments = _tool_segments_for_ids(
        segments,
        [str(item.get("tool_id") or "") for item in tool_candidates.get("combined", []) if isinstance(item, dict)],
    )
    verdicts = _studio_test_verdicts(
        selected_tools=selected_tools,
        selected_tool_segments=selected_tool_segments,
        matched_skills=matched_skills,
        tool_candidates=tool_candidates,
    )
    return {
        "profile_id": profile_id,
        "prompt_id": prompt_id,
        "conversation_id": conversation_id,
        "model_profile_id": model_profile_id,
        "model": model,
        "input": {
            "user_text": user_text,
            "selected_tools": selected_tools,
            "model_profile_id": model_profile_id,
            "model": model,
        },
        "summary": usage,
        "segments": segments,
        "matched_skills": matched_skills,
        "skill_instructions": skill_instructions,
        "selected_tool_records": selected_tool_records,
        "selected_tool_segments": selected_tool_segments,
        "candidate_tool_segments": candidate_tool_segments,
        "tool_candidates": tool_candidates,
        "prompt_tool_analysis": {
            "prompt_can_call_tool": False,
            "prompt_can_grant_permission": False,
            "prompt_can_attach_tool_schema": False,
            "decision_boundary": (
                "Prompt text can make a tool look relevant, but it cannot attach, grant, or execute tools. "
                "Only the tool registry, model/provider support, profile policy, and approval/authority path can make a tool callable."
            ),
        },
        "safety_boundary": {
            "passive_text_only": True,
            "can_grant_permissions": False,
            "can_call_tools": False,
            "can_mutate_chat_state": False,
        },
        "verdicts": verdicts,
    }


def _prompt_records(profile_id: str) -> list[dict[str, Any]]:
    manager = get_manager()
    by_name: dict[str, dict[str, Any]] = {}
    for prompt in manager.list_prompts():
        if not isinstance(prompt, dict):
            continue
        record = _normalize_prompt_record(prompt)
        by_name[str(record.get("name") or record.get("id"))] = record
    for override in _profile_override_records(profile_id):
        by_name[str(override.get("name") or override.get("id"))] = override
    return sorted(by_name.values(), key=lambda item: (str(item.get("source_type") or ""), str(item.get("name") or item.get("id") or "")))


def _studio_active_summary(profile_id: str, data: dict[str, Any]) -> dict[str, Any]:
    active = active_prompt_summary(
        {
            "profile_id": profile_id,
            "conversation_id": data.get("conversation_id"),
            "include_text": False,
        }
    )
    trace_usage = _trace_usage_for_studio(profile_id, data)
    if not trace_usage:
        return active
    return {
        **active,
        "summary": trace_usage,
        "segments": trace_usage.get("segments", []),
        "active_segments": trace_usage.get("active_segments", []),
        "disabled_segments": trace_usage.get("disabled_segments", []),
        "token_estimate": trace_usage.get("token_estimate", {}),
    }


def _trace_usage_for_studio(profile_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    store = AiInputTraceStore()
    trace_id = str(data.get("trace_id") or "").strip()
    trace = store.get_trace(profile_id, trace_id) if trace_id else None
    conversation_id = str(data.get("conversation_id") or "").strip()
    if trace is None and conversation_id:
        for item in store.list_traces(profile_id, limit=100):
            if str(item.get("conversation_id") or "") != conversation_id:
                continue
            candidate_id = str(item.get("trace_id") or "").strip()
            if candidate_id:
                trace = store.get_trace(profile_id, candidate_id)
                break
    if not isinstance(trace, dict):
        return None
    return prompt_usage_from_trace(trace, include_text=False)


def _merge_prompt_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for record in records:
        key = str(record.get("prompt_id") or record.get("name") or record.get("id") or "").strip()
        if not key:
            anonymous.append(record)
            continue
        by_key[key] = record
    return sorted(
        [*anonymous, *by_key.values()],
        key=lambda item: (str(item.get("source_type") or ""), str(item.get("name") or item.get("id") or "")),
    )


def _segment_records_from_active(segments: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for segment in segments if isinstance(segments, list) else []:
        if not isinstance(segment, dict):
            continue
        kind = str(segment.get("kind") or "").strip()
        source_type = str(segment.get("source_type") or "").strip()
        if kind in {"", "prompt", "pack", "component", "extension"}:
            continue
        if kind == "profile" and source_type != "profile_snapshot":
            continue
        segment_id = str(segment.get("id") or segment.get("prompt_id") or "").strip()
        if not segment_id:
            continue
        name = str(segment.get("prompt_id") or segment_id).strip()
        label = str(segment.get("label") or name).strip()
        body = str(segment.get("text") or segment.get("preview") or "")
        if not body:
            body = json.dumps(
                {
                    "input_role": segment.get("input_role"),
                    "explanation": segment.get("explanation") or segment.get("reason"),
                    "tool_signal": segment.get("tool_signal"),
                    "skill_signal": segment.get("skill_signal"),
                    "safety_boundary": segment.get("safety_boundary"),
                },
                ensure_ascii=False,
                indent=2,
            )
        record_metadata = {"source": source_type or kind, "segment": segment}
        if source_type != "profile_snapshot":
            record_metadata["prompt_usage_segment"] = True
        if isinstance(segment.get("source_chain"), list):
            record_metadata["source_chain"] = segment.get("source_chain")
        records.append(
            {
                "id": name,
                "name": name,
                "prompt_id": name,
                "display_name": label,
                "description": str(segment.get("explanation") or segment.get("reason") or ""),
                "body": body,
                "content": body,
                "variables": [],
                "metadata": record_metadata,
                "source_type": source_type or kind,
                "source": str(segment.get("source") or segment.get("source_type") or ""),
                "read_only": True,
                "editable": False,
                "override_allowed": False,
                "tokens": int(segment.get("tokens") or 0),
                "preview": " ".join(body.split())[:220],
                "created_at": "",
                "updated_at": "",
                "activation_state": str(segment.get("status") or "available"),
                "active_edge_id": str(segment.get("edge_id") or ""),
                "active_reason": str(segment.get("explanation") or segment.get("reason") or ""),
                "allow_disable": bool(segment.get("allow_disable", True)),
                "input_role": segment.get("input_role"),
                "source_priority": segment.get("source_priority"),
                "activation_detail": segment.get("activation_detail"),
                "tool_signal": segment.get("tool_signal"),
                "skill_signal": segment.get("skill_signal"),
                "safety": segment.get("safety_boundary"),
            }
        )
    return records


def _normalize_prompt_record(prompt: dict[str, Any]) -> dict[str, Any]:
    metadata = prompt.get("metadata") if isinstance(prompt.get("metadata"), dict) else {}
    source_type = _source_type_for_prompt(prompt)
    body = str(prompt.get("body") or prompt.get("content") or "")
    prompt_id = str(prompt.get("name") or prompt.get("id") or "")
    return {
        "id": str(prompt.get("id") or prompt_id),
        "name": prompt_id,
        "prompt_id": prompt_id,
        "description": str(prompt.get("description") or ""),
        "body": body,
        "content": body,
        "variables": prompt.get("variables") if isinstance(prompt.get("variables"), list) else [],
        "metadata": metadata,
        "source_type": source_type,
        "source": str(metadata.get("path") or metadata.get("manifest_path") or metadata.get("source") or source_type),
        "read_only": bool(prompt.get("read_only") or source_type in {"pack_default", "component", "extension"}),
        "editable": not bool(prompt.get("read_only") or source_type in {"pack_default", "component", "extension"}),
        "tokens": _estimate_tokens(body),
        "preview": " ".join(body.split())[:220],
        "created_at": prompt.get("created_at") or "",
        "updated_at": prompt.get("updated_at") or "",
    }


def _source_type_for_prompt(prompt: dict[str, Any]) -> str:
    metadata = prompt.get("metadata") if isinstance(prompt.get("metadata"), dict) else {}
    source = str(metadata.get("source") or "").strip()
    if source == "pack":
        return "pack_default"
    if source in {"extension", "canonical_fallback"}:
        return "extension"
    if source == "component":
        return "component"
    if prompt.get("read_only") and prompt.get("source_pack_id"):
        return "pack_default"
    return "user_data"


def _profile_override_records(profile_id: str) -> list[dict[str, Any]]:
    paths = ProfileWorkspaceManager().paths_for_profile(profile_id)
    if not paths.prompts_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(paths.prompts_dir.glob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        records.append(_profile_override_record(profile_id, path))
    return records


def _profile_override_record(profile_id: str, path: Path) -> dict[str, Any]:
    body = path.read_text(encoding="utf-8") if path.is_file() else ""
    prompt_id = _prompt_id_from_override_path(path)
    return {
        "id": prompt_id,
        "name": prompt_id,
        "prompt_id": prompt_id,
        "description": "Profile override",
        "body": body,
        "content": body,
        "variables": [],
        "metadata": {"profile_id": profile_id, "path": str(path), "source": "profile_override"},
        "source_type": "profile_override",
        "source": str(path),
        "read_only": False,
        "editable": True,
        "tokens": _estimate_tokens(body),
        "preview": " ".join(body.split())[:220],
        "created_at": "",
        "updated_at": str(int(path.stat().st_mtime)) if path.is_file() else "",
    }


def _annotate_prompt_records(prompts: list[dict[str, Any]], segments: Any) -> list[dict[str, Any]]:
    active_by_prompt: dict[str, dict[str, Any]] = {}
    for segment in segments if isinstance(segments, list) else []:
        if not isinstance(segment, dict):
            continue
        key = str(segment.get("prompt_id") or segment.get("label") or "").strip()
        if key:
            active_by_prompt[key] = segment
    annotated = []
    for prompt in prompts:
        key = str(prompt.get("prompt_id") or prompt.get("name") or prompt.get("id") or "")
        segment = active_by_prompt.get(key)
        annotated.append(
            {
                **prompt,
                "activation_state": str(segment.get("status") if segment else "available"),
                "active_edge_id": segment.get("edge_id") if segment else "",
                "active_reason": segment.get("reason") if segment else "",
                "allow_disable": bool(segment.get("allow_disable", True)) if segment else True,
            }
        )
    return annotated


def _prompt_detail(profile_id: str, prompt_id: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    prompt = next((item for item in records if str(item.get("name") or item.get("id")) == prompt_id), None)
    effective = _resolve_effective_prompt_for(profile_id, prompt_id)
    if prompt is None:
        if str(effective.get("source_type") or "") not in {"profile_snapshot", "profile_override"}:
            return None
        prompt = _effective_prompt_record(profile_id, prompt_id, effective)
    metadata = prompt.get("metadata") if isinstance(prompt.get("metadata"), dict) else {}
    if metadata.get("prompt_usage_segment") is True:
        segment = metadata.get("segment") if isinstance(metadata.get("segment"), dict) else {}
        return {
            **prompt,
            "source_chain": segment.get("source_chain", []),
            "effective_source": prompt.get("source", ""),
            "effective_source_type": prompt.get("source_type", ""),
            "validation": {"valid": True, "warnings": []},
            "lint": {"warnings": [], "token_estimate": prompt.get("tokens", 0)},
            "versions": [],
            "safety": segment.get("safety_boundary") if isinstance(segment.get("safety_boundary"), dict) else {
                "passive_text_only": True,
                "can_grant_permissions": False,
                "can_call_tools": False,
                "can_mutate_chat_state": False,
            },
        }
    body = str(prompt.get("body") or prompt.get("content") or "")
    effective_source_type = str(effective.get("source_type") or "")
    effective_body = str(effective.get("final_content") or effective.get("content") or "")
    if effective_source_type in {"profile_snapshot", "profile_override"}:
        body = effective_body
        prompt = {
            **prompt,
            "body": body,
            "content": body,
            "source_type": effective_source_type,
            "source": str(effective.get("source") or prompt.get("source") or ""),
            "read_only": effective_source_type == "profile_snapshot",
            "editable": effective_source_type == "profile_override",
            "tokens": _estimate_tokens(body),
            "preview": " ".join(body.split())[:220],
        }
    validation = validate_prompt_template({"template": body, "variables": prompt.get("variables")})
    return {
        **prompt,
        "source_chain": effective.get("source_chain", []),
        "effective_source": effective.get("source", ""),
        "effective_source_type": effective_source_type,
        "validation": validation,
        "lint": lint_prompt(body),
        "versions": prompt_versions({"profile_id": profile_id, "prompt_id": prompt_id}).get("versions", []),
        "safety": {
            "passive_text_only": True,
            "can_grant_permissions": False,
            "can_call_tools": False,
            "can_mutate_chat_state": False,
        },
    }


def _base_prompt_body(prompt_id: str) -> str:
    prompt = get_manager().get_prompt_by_name(prompt_id) or get_manager().get_prompt(prompt_id)
    return str((prompt or {}).get("body") or (prompt or {}).get("content") or "")


def _effective_prompt_body(profile_id: str, prompt_id: str) -> str:
    effective = _resolve_effective_prompt_for(profile_id, prompt_id)
    source_type = str(effective.get("source_type") or "")
    if source_type and source_type != "empty":
        return str(effective.get("final_content") or effective.get("content") or "")
    return _base_prompt_body(prompt_id)


def _resolve_effective_prompt_for(profile_id: str, prompt_id: str) -> dict[str, Any]:
    workspace = profile_workspace_payload(ProfileWorkspaceManager().paths_for_profile(profile_id))
    return resolve_effective_prompt(
        {
            "profile_id": profile_id,
            "system_prompt_id": prompt_id,
            "default_prompt_id": prompt_id,
            "base_pack": "defaultspack",
            "workspace": workspace,
        }
    )


def _effective_prompt_record(profile_id: str, prompt_id: str, effective: dict[str, Any]) -> dict[str, Any]:
    body = str(effective.get("final_content") or effective.get("content") or "")
    source_type = str(effective.get("source_type") or "profile_snapshot")
    read_only = source_type != "profile_override"
    return {
        "id": prompt_id,
        "name": prompt_id,
        "prompt_id": prompt_id,
        "description": "Effective profile prompt",
        "body": body,
        "content": body,
        "variables": [],
        "metadata": {
            "profile_id": profile_id,
            "source": source_type,
            "source_chain": effective.get("source_chain") if isinstance(effective.get("source_chain"), list) else [],
        },
        "source_type": source_type,
        "source": str(effective.get("source") or source_type),
        "read_only": read_only,
        "editable": not read_only,
        "tokens": _estimate_tokens(body),
        "preview": " ".join(body.split())[:220],
        "created_at": "",
        "updated_at": "",
    }


def _record_version(
    *,
    profile_id: str,
    prompt_id: str,
    scope: str,
    previous_body: str,
    next_body: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    version_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{int(time.time() * 1000) % 1000:03d}"
    payload = {
        "version_id": version_id,
        "profile_id": profile_id,
        "prompt_id": prompt_id,
        "scope": scope,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "previous_body": previous_body,
        "next_body": next_body,
        "reason": reason,
        "metadata": dict(metadata or {}),
    }
    path = _version_dir(profile_id, prompt_id, scope) / f"{version_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _list_versions(profile_id: str, prompt_id: str, scope: str) -> list[dict[str, Any]]:
    root = _version_dir(profile_id, prompt_id, scope)
    if not root.is_dir():
        return []
    versions = []
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict):
            versions.append({key: value for key, value in raw.items() if key not in {"previous_body", "next_body"}})
    return versions


def _load_version(profile_id: str, prompt_id: str, version_id: str) -> dict[str, Any] | None:
    if "/" in version_id or "\\" in version_id:
        return None
    for scope in ("profile_override", "user_prompt"):
        path = _version_dir(profile_id, prompt_id, scope) / f"{version_id}.json"
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None
    return None


def _version_dir(profile_id: str, prompt_id: str, scope: str) -> Path:
    if scope == "profile_override":
        root = ProfileWorkspaceManager().paths_for_profile(profile_id).root / "prompt_versions"
    else:
        root = Path(__file__).resolve().parents[2] / "user_data" / "shared" / "prompt_versions"
    return root / _safe_name(prompt_id) / scope


def _profile_override_path(profile_id: str, prompt_id: str) -> Path:
    paths = ProfileWorkspaceManager().paths_for_profile(profile_id)
    return paths.prompts_dir / f"{_safe_name(prompt_id)}.system.md"


def _prompt_id_from_override_path(path: Path) -> str:
    name = path.name
    for suffix in (".system.md", ".prompt.md", ".md", ".txt"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _resolve_profile_id(value: Any = None) -> str:
    candidate = str(value or "").strip() or str(active_profile_id() or "").strip() or "defaultspack.startup"
    return validate_profile_id(candidate)


def _clean_prompt_id(value: Any) -> str:
    prompt_id = str(value or "").strip()
    if not prompt_id:
        raise ValueError("prompt_id is required")
    if not _SAFE_PROMPT_ID.match(prompt_id):
        raise ValueError("prompt_id contains unsupported characters")
    return prompt_id


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("._") or "prompt"


def _estimate_tokens(text: str) -> int:
    try:
        from core_runtime.ai_input_token_estimator import estimate_tokens

        return int(estimate_tokens(text))
    except Exception:
        return max(1, len(str(text or "")) // 4) if text else 0


def _tool_catalog(data: dict[str, Any], segments: list[Any]) -> list[dict[str, Any]]:
    tools_by_id: dict[str, dict[str, Any]] = {}
    for raw_tool in data.get("tools") or data.get("available_tools") or []:
        if not isinstance(raw_tool, dict):
            continue
        tool_id = str(raw_tool.get("tool_id") or raw_tool.get("name") or "").strip()
        if tool_id:
            tools_by_id[tool_id] = dict(raw_tool)
    for segment in segments:
        if not isinstance(segment, dict) or segment.get("kind") != "tool-schema":
            continue
        signal = segment.get("tool_signal") if isinstance(segment.get("tool_signal"), dict) else {}
        tool_id = str(signal.get("tool_id") or segment.get("prompt_id") or "").strip()
        if not tool_id:
            continue
        tools_by_id.setdefault(
            tool_id,
            {
                "tool_id": tool_id,
                "name": signal.get("tool_name") or tool_id,
                "display_name": signal.get("display_name") or signal.get("tool_name") or tool_id,
                "description": signal.get("description") or segment.get("description") or segment.get("explanation") or "",
                "metadata": {
                    "source_pack_id": signal.get("source_pack_id") or "",
                    "skills": signal.get("skills") or [],
                    "skill_triggers": signal.get("skill_triggers") or [],
                },
            },
        )
    return sorted(tools_by_id.values(), key=lambda item: str(item.get("tool_id") or item.get("name") or ""))


def _tool_candidates(*, prompt_body: str, user_text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    prompt_hits = _search_tools(prompt_body, tools, limit=8, threshold=0.05) if prompt_body.strip() else []
    input_hits = _search_tools(user_text, tools, limit=8, threshold=0.05) if user_text.strip() else []
    combined: dict[str, dict[str, Any]] = {}
    for source, items in (("prompt", prompt_hits), ("input", input_hits)):
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            tool_id = str(item.get("tool_id") or "").strip()
            if not tool_id:
                continue
            current = combined.get(tool_id)
            score = float(item.get("score") or 0)
            if current is None or score > float(current.get("score") or 0):
                combined[tool_id] = {**item, "matched_from": source}
            else:
                sources = _string_list(current.get("matched_from"))
                if source not in sources:
                    current["matched_from"] = [*sources, source]
    combined_items = sorted(combined.values(), key=lambda item: (-float(item.get("score") or 0), str(item.get("tool_id") or "")))
    return {
        "combined": combined_items[:8],
        "from_prompt": prompt_hits,
        "from_input": input_hits,
    }


def _evaluate_studio_skills(data: dict[str, Any], *, user_text: str, selected_tools: list[str]) -> dict[str, Any]:
    skills = data.get("skills") if "skills" in data and isinstance(data.get("skills"), list) else None
    context = data.get("request_context") if isinstance(data.get("request_context"), dict) else {}
    skill_context = {**context, "studio_test": True}
    forced_skills = _string_list(data.get("skills_forced") or data.get("selected_skills"))
    if forced_skills:
        skill_context["selected_skills"] = forced_skills
    return RuntimeSkillTriggerService(skills).evaluate(
        user_text=user_text,
        tool_names=selected_tools,
        context=skill_context,
    )


def _search_tools(
    text: str,
    tools: list[dict[str, Any]],
    *,
    limit: int,
    threshold: float,
) -> list[dict[str, Any]]:
    query_tokens = _match_tokens(text)
    if not query_tokens:
        return []
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for tool in tools:
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        if not tool_id:
            continue
        haystack = " ".join(
            [
                tool_id,
                str(tool.get("name") or ""),
                str(tool.get("display_name") or ""),
                str(tool.get("description") or ""),
                " ".join(_string_list(tool.get("skills"))),
                " ".join(_string_list((tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}).get("skill_triggers"))),
            ]
        )
        tool_tokens = _match_tokens(haystack)
        if not tool_tokens:
            continue
        overlap = query_tokens.intersection(tool_tokens)
        exact_boost = 0.25 if tool_id.casefold() in str(text or "").casefold() else 0.0
        score = (len(overlap) / max(len(query_tokens), 1)) + exact_boost
        if score >= threshold:
            scored.append((score, tool_id, tool))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        {
            "tool_id": tool_id,
            "name": str(tool.get("name") or tool_id),
            "display_name": str(tool.get("display_name") or tool.get("name") or tool_id),
            "description": str(tool.get("description") or ""),
            "score": score,
            "prompt_can_call_tool": False,
        }
        for score, tool_id, tool in scored[: max(1, limit)]
    ]


def _evaluate_inline_skills(
    skills: list[Any],
    *,
    user_text: str,
    selected_tools: list[str],
    forced_skills: list[str],
) -> dict[str, Any]:
    text = str(user_text or "").casefold()
    tool_set = {str(item or "").strip() for item in selected_tools if str(item or "").strip()}
    forced = {_normalize_skill_ref(item) for item in forced_skills}
    matched: list[dict[str, Any]] = []
    for raw_skill in skills:
        if not isinstance(raw_skill, dict):
            continue
        skill_id = str(raw_skill.get("id") or raw_skill.get("name") or "").strip()
        if not skill_id:
            continue
        aliases = {_normalize_skill_ref(value) for value in [skill_id, skill_id.rsplit("/", 1)[-1], raw_skill.get("display_name"), raw_skill.get("name")]}
        metadata = raw_skill.get("metadata") if isinstance(raw_skill.get("metadata"), dict) else {}
        aliases.update(_normalize_skill_ref(value) for value in _string_list(raw_skill.get("aliases") or metadata.get("aliases")))
        triggers = _string_list(raw_skill.get("triggers") or raw_skill.get("keywords") or metadata.get("triggers"))
        applies_to = _string_list(raw_skill.get("applies_to_tools") or raw_skill.get("tool_ids") or metadata.get("applies_to_tools"))
        forced_hit = bool(forced.intersection(aliases))
        trigger_hit = forced_hit or not triggers or any(str(trigger).casefold() in text for trigger in triggers)
        tool_hit = forced_hit or not applies_to or bool(tool_set.intersection(applies_to))
        if not (trigger_hit and tool_hit):
            continue
        instruction = _skill_instruction(raw_skill)
        if not instruction:
            continue
        matched.append(
            {
                "id": skill_id,
                "display_name": str(raw_skill.get("display_name") or skill_id),
                "triggers": triggers,
                "applies_to_tools": applies_to,
                "instruction": instruction,
            }
        )
    if not matched:
        return {"matched": [], "instructions": ""}
    lines = [
        "Runtime skill instructions matched this turn. These are active system-level instructions for this turn; follow them unless they conflict with higher-priority safety or user instructions:"
    ]
    lines.extend("- {}: {}".format(item.get("id"), str(item.get("instruction") or "").strip()) for item in matched)
    return {"matched": matched, "instructions": "\n".join(lines).strip()}


def _skill_instruction(skill: dict[str, Any]) -> str:
    for container in (skill, skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}, skill.get("config") if isinstance(skill.get("config"), dict) else {}):
        for key in ("instructions", "instruction", "system_prompt", "prompt", "feedback"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(skill.get("description") or "").strip()


def _normalize_skill_ref(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "-").replace("_", "-")


def _match_tokens(value: str) -> set[str]:
    return {part.casefold() for part in re.findall(r"[A-Za-z0-9_.:-]+|[\u3040-\u30ff\u3400-\u9fff]+", str(value or "")) if part.strip()}


def _selected_tool_records(tools: list[dict[str, Any]], selected_tools: list[str]) -> list[dict[str, Any]]:
    selected = set(selected_tools)
    records = []
    for tool in tools:
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        name = str(tool.get("name") or tool_id).strip()
        if tool_id not in selected and name not in selected:
            continue
        metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
        records.append(
            {
                "tool_id": tool_id or name,
                "name": name or tool_id,
                "display_name": str(tool.get("display_name") or metadata.get("display_name") or name or tool_id),
                "description": str(tool.get("description") or metadata.get("description") or ""),
                "skills": _string_list(tool.get("skills") or metadata.get("skills")),
                "skill_triggers": _string_list(metadata.get("skill_triggers")),
                "prompt_can_call_tool": False,
            }
        )
    return records


def _tool_segments_for_ids(segments: list[Any], tool_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(tool_ids)
    if not wanted:
        return []
    result = []
    for segment in segments:
        if not isinstance(segment, dict) or segment.get("kind") != "tool-schema":
            continue
        signal = segment.get("tool_signal") if isinstance(segment.get("tool_signal"), dict) else {}
        values = {
            str(segment.get("prompt_id") or "").strip(),
            str(segment.get("label") or "").strip(),
            str(signal.get("tool_id") or "").strip(),
            str(signal.get("tool_name") or "").strip(),
        }
        if values.intersection(wanted):
            result.append(segment)
    return result


def _studio_test_verdicts(
    *,
    selected_tools: list[str],
    selected_tool_segments: list[dict[str, Any]],
    matched_skills: list[Any],
    tool_candidates: dict[str, Any],
) -> list[dict[str, str]]:
    candidates = tool_candidates.get("combined") if isinstance(tool_candidates.get("combined"), list) else []
    return [
        {
            "id": "skill",
            "status": "matched" if matched_skills else "idle",
            "title": "Skill prompt",
            "detail": (
                f"{len(matched_skills)} skill prompt segment{'s' if len(matched_skills) != 1 else ''} matched this Studio input."
                if matched_skills
                else "No runtime skill prompt matched this Studio input."
            ),
        },
        {
            "id": "tool_schema",
            "status": "selected" if selected_tool_segments else "available" if selected_tools else "not-selected",
            "title": "Tool schema",
            "detail": (
                f"{len(selected_tool_segments)} selected tool schema segment{'s' if len(selected_tool_segments) != 1 else ''} found in the active graph."
                if selected_tool_segments
                else "No selected tool schema was found in the active graph."
                if selected_tools
                else "No selected tool was supplied for this Studio test."
            ),
        },
        {
            "id": "prompt_tool_judgement",
            "status": "candidate" if candidates else "none",
            "title": "Prompt to tool",
            "detail": (
                f"{len(candidates)} tool candidate{'s' if len(candidates) != 1 else ''} matched the prompt draft or test input."
                if candidates
                else "The prompt draft and test input did not produce a local tool candidate."
            ),
        },
        {
            "id": "safety",
            "status": "passive",
            "title": "Safety boundary",
            "detail": "Prompt text stayed passive: it did not grant permission, attach tools, call tools, or mutate chat state.",
        },
    ]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
