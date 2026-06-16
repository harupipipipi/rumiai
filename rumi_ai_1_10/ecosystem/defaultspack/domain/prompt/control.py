from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from .effective import validate_prompt_template
from .manager import _get_prompts_dir, _safe_filename, get_manager

_VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
_UNSAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def state_path() -> Path:
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "prompt_control" / "state.json"


def read_state() -> dict[str, Any]:
    path = state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    prompts = raw.get("prompts") if isinstance(raw, dict) and isinstance(raw.get("prompts"), dict) else {}
    return {"schema_version": 1, "prompts": dict(prompts), "updated_at": str(raw.get("updated_at") if isinstance(raw, dict) else "")}


def write_state(state: dict[str, Any]) -> dict[str, Any]:
    payload = {"schema_version": 1, "prompts": dict(state.get("prompts") or {}), "updated_at": now_iso()}
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def prompt_enabled(prompt_id: str, *, state: dict[str, Any] | None = None, default: bool = True) -> bool:
    state = state or read_state()
    entry = state.get("prompts", {}).get(str(prompt_id or "").strip())
    if not isinstance(entry, dict) or "enabled" not in entry:
        return default
    return bool(entry.get("enabled"))


def set_prompt_enabled(prompt_id: str, enabled: bool, *, actor: str = "ui") -> dict[str, Any]:
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        raise ValueError("prompt_id is required")
    state = read_state()
    state.setdefault("prompts", {})[prompt_id] = {"enabled": bool(enabled), "actor": str(actor or "ui"), "updated_at": now_iso()}
    return {"prompt_id": prompt_id, "enabled": bool(enabled), "state": write_state(state)}


def apply_control_to_segments(segments: list[Any]) -> list[Any]:
    state = read_state()
    patched: list[Any] = []
    for segment in segments:
        metadata = getattr(segment, "metadata", {})
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        segment_id = str(getattr(segment, "id", "") or "")
        prompt_id = str(metadata.get("prompt_id") or metadata.get("resolved_prompt_id") or "").strip()
        if not prompt_id and segment_id.startswith("prompt:"):
            prompt_id = segment_id.removeprefix("prompt:")
        aliases = [value for value in {prompt_id, str(metadata.get("resolved_prompt_id") or ""), segment_id.removeprefix("prompt:") if segment_id.startswith("prompt:") else ""} if value]
        if all(prompt_enabled(alias, state=state) for alias in aliases):
            patched.append(segment)
            continue
        metadata["disabled_by_prompt_control"] = True
        try:
            patched.append(replace(segment, text="", enabled=False, reason="disabled_by_prompt_control", metadata=metadata))
        except Exception:
            patched.append(segment)
    return patched


def digest(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def preview(text: Any, limit: int = 360) -> str:
    compact = " ".join(str(text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def prompt_text(record: dict[str, Any]) -> str:
    return str(record.get("body") or record.get("content") or record.get("template") or record.get("system_prompt") or "")


def prompt_source(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    return str(metadata.get("source") or record.get("source_pack_id") or "user")


def normalize_prompt(record: dict[str, Any], state: dict[str, Any], active_ids: set[str]) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    prompt_id = str(record.get("id") or record.get("prompt_id") or record.get("name") or "").strip()
    name = str(record.get("name") or prompt_id).strip()
    aliases = [value for value in {prompt_id, name, str(metadata.get("resolved_prompt_id") or "")} if value]
    text = prompt_text(record)
    return {
        "id": prompt_id,
        "prompt_id": prompt_id,
        "name": name or prompt_id,
        "description": str(record.get("description") or ""),
        "source": prompt_source(record),
        "source_pack_id": str(record.get("source_pack_id") or metadata.get("source_pack_id") or ""),
        "read_only": bool(record.get("read_only")),
        "editable": True,
        "can_override": True,
        "enabled": all(prompt_enabled(alias, state=state) for alias in aliases),
        "active": any(alias in active_ids for alias in aliases),
        "tokens_estimate": max(1, len(text) // 4) if text else 0,
        "char_count": len(text),
        "digest": digest(text),
        "preview": preview(text),
        "variables": record.get("variables") if isinstance(record.get("variables"), list) else [],
        "metadata": dict(metadata),
        "updated_at": str(record.get("updated_at") or ""),
    }


def active_profile_id() -> str:
    try:
        from core_runtime.profile_paths import active_profile_id as _active_profile_id
        return str(_active_profile_id() or "").strip()
    except Exception:
        return ""


def trace_for_profile(profile_id: str, conversation_id: str = "") -> dict[str, Any] | None:
    try:
        from core_runtime.ai_input_trace_store import AiInputTraceStore
        store = AiInputTraceStore()
        if conversation_id:
            for summary in store.list_traces(profile_id, limit=40):
                if str(summary.get("conversation_id") or "") == conversation_id:
                    return store.get_trace(profile_id, str(summary.get("trace_id") or ""))
        latest_path = store.trace_dir(profile_id) / "latest_ai_input.json"
        if latest_path.is_file():
            raw = json.loads(latest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and (not conversation_id or str(raw.get("conversation_id") or "") == conversation_id):
                return raw
    except Exception:
        return None
    return None


def runtime_snapshot_from_trace(trace: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(trace, dict):
        return {"schema_version": 1, "source": "none", "prompts": [], "active_prompt_ids": [], "disabled_prompt_ids": [], "context_segments": []}
    effective = trace.get("effective_input") if isinstance(trace.get("effective_input"), dict) else {}
    system_segments = effective.get("system_segments") if isinstance(effective.get("system_segments"), list) else []
    disabled_segments = effective.get("disabled_segments") if isinstance(effective.get("disabled_segments"), list) else []
    prompts = []
    for segment in system_segments:
        if not isinstance(segment, dict):
            continue
        metadata = segment.get("metadata") if isinstance(segment.get("metadata"), dict) else {}
        prompt_id = str(metadata.get("prompt_id") or metadata.get("resolved_prompt_id") or str(segment.get("id") or "").removeprefix("prompt:")).strip()
        text = str(segment.get("text") or segment.get("preview") or "")
        prompts.append({
            "id": str(segment.get("id") or prompt_id),
            "prompt_id": prompt_id,
            "name": prompt_id,
            "source": str(segment.get("source") or ""),
            "source_type": str(segment.get("source_type") or ""),
            "enabled": bool(segment.get("enabled", True)),
            "reason": str(segment.get("reason") or ""),
            "tokens": int(segment.get("tokens") or 0),
            "priority": int(segment.get("priority") or 0),
            "digest": digest(text),
            "preview": preview(text),
            "metadata": dict(metadata),
        })
    disabled_prompt_ids = [item["prompt_id"] for item in prompts if not item.get("enabled") and item.get("prompt_id")]
    for item in disabled_segments:
        if isinstance(item, dict):
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            candidate = str(metadata.get("prompt_id") or str(item.get("id") or "").removeprefix("prompt:")).strip()
            if candidate and candidate not in disabled_prompt_ids:
                disabled_prompt_ids.append(candidate)
    return {
        "schema_version": 1,
        "source": "ai_input_trace",
        "trace_id": str(trace.get("trace_id") or ""),
        "created_at": trace.get("created_at"),
        "profile_id": str(trace.get("profile_id") or effective.get("profile_id") or ""),
        "conversation_id": str(trace.get("conversation_id") or ""),
        "run_id": str(trace.get("run_id") or ""),
        "prompts": prompts,
        "active_prompt_ids": [item["prompt_id"] for item in prompts if item.get("enabled") and item.get("prompt_id")],
        "disabled_prompt_ids": disabled_prompt_ids,
        "context_segments": effective.get("context_segments") if isinstance(effective.get("context_segments"), list) else [],
        "token_estimate": trace.get("token_estimate") if isinstance(trace.get("token_estimate"), dict) else {},
        "provider_payload_summary": trace.get("provider_payload_summary") if isinstance(trace.get("provider_payload_summary"), dict) else {},
        "gate_decisions": trace.get("gate_decisions") if isinstance(trace.get("gate_decisions"), list) else [],
        "diagnostics": trace.get("diagnostics") if isinstance(trace.get("diagnostics"), list) else [],
    }


def active_runtime_snapshot(conversation_id: str = "", profile_id: str = "") -> dict[str, Any]:
    profile_id = str(profile_id or "").strip() or active_profile_id()
    trace = trace_for_profile(profile_id, str(conversation_id or "").strip()) if profile_id else None
    return runtime_snapshot_from_trace(trace)


def prompt_inventory(conversation_id: str = "", profile_id: str = "") -> dict[str, Any]:
    state = read_state()
    active = active_runtime_snapshot(conversation_id, profile_id)
    active_ids = {str(item) for item in active.get("active_prompt_ids", []) if item}
    prompts = [normalize_prompt(record, state, active_ids) for record in get_manager().list_prompts() if isinstance(record, dict)]
    prompts.sort(key=lambda item: (not item.get("active"), not item.get("enabled"), str(item.get("source")), str(item.get("name"))))
    return {"schema_version": 1, "prompts": prompts, "active": active, "state": state, "counts": {"total": len(prompts), "enabled": sum(1 for item in prompts if item.get("enabled")), "disabled": sum(1 for item in prompts if not item.get("enabled")), "active": sum(1 for item in prompts if item.get("active"))}, "functions": prompt_function_catalog()}


def prompt_function_catalog() -> list[dict[str, Any]]:
    return [
        {"id": "defaults.prompt.list", "risk": "low", "endpoint": "GET/POST /api/prompts", "use": "Prompt library inventory."},
        {"id": "defaults.prompt.render", "risk": "low", "endpoint": "POST /api/prompts/render", "use": "Render prompt text with variables."},
        {"id": "defaults.prompt.load_effective", "risk": "low", "endpoint": "function", "use": "Resolve profile override, snapshot, then pack default."},
        {"id": "defaults.prompt.validate_template", "risk": "low", "endpoint": "function", "use": "Validate {{variable}} syntax before save."},
        {"id": "defaults.prompt.lint_prompt", "risk": "low", "endpoint": "POST /api/prompts/lint", "use": "Find redundancy and budget risk."},
        {"id": "defaults.prompt.compact_prompt", "risk": "medium", "endpoint": "POST /api/prompts/compact", "use": "Suggest a shorter safe prompt."},
        {"id": "defaults.prompt.control", "risk": "medium", "endpoint": "POST /api/prompts/control", "use": "Inspect active prompts and toggle next-run participation."},
        {"id": "defaults.prompt.editor", "risk": "medium", "endpoint": "POST /api/prompts/editor", "use": "Save user overrides and duplicate prompts."},
    ]


def variables_from_text(text: str) -> list[dict[str, Any]]:
    names: list[str] = []
    for match in _VAR_RE.finditer(text or ""):
        name = match.group(1).strip()
        if name and name not in names:
            names.append(name)
    return [{"name": name, "type": "string", "default": None, "required": not name.startswith("context.")} for name in names]


def safe_prompt_id(value: Any) -> str:
    text = _UNSAFE_ID_RE.sub("_", str(value or "").strip()).strip("._:-")
    if not text:
        text = f"prompt_{uuid.uuid4().hex[:8]}"
    if not text[0].isalpha():
        text = "prompt_" + text
    return text[:96]


def upsert_user_prompt(prompt_id: str, *, name: str, body: str, description: str, variables: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    prompt_id = safe_prompt_id(prompt_id)
    now = now_iso()
    prompt = {"id": prompt_id, "name": name or prompt_id, "content": body, "body": body, "description": description, "variables": variables, "metadata": {"source": "user_override", **dict(metadata or {})}, "created_at": now, "updated_at": now, "read_only": False}
    prompts_dir = Path(_get_prompts_dir())
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / (_safe_filename(prompt["name"]) + ".json")).write_text(json.dumps(prompt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manager = get_manager()
    try:
        manager._ensure_loaded()  # type: ignore[attr-defined]
        manager._prompts[prompt_id] = prompt  # type: ignore[attr-defined]
        manager._name_index[prompt["name"]] = prompt_id  # type: ignore[attr-defined]
    except Exception:
        pass
    return prompt


def prompt_editor_draft(prompt_id: str) -> dict[str, Any]:
    record = get_manager().get_prompt(prompt_id) or get_manager().get_prompt_by_name(prompt_id)
    if record is None:
        raise KeyError(f"Prompt not found: {prompt_id}")
    text = prompt_text(record)
    variables = record.get("variables") if isinstance(record.get("variables"), list) else variables_from_text(text)
    return {"prompt": normalize_prompt(record, read_state(), set()), "content": text, "validation": validate_prompt_template(text, variables), "mode_hint": "user_override" if record.get("read_only") else "edit"}


def save_prompt_edit(payload: dict[str, Any]) -> dict[str, Any]:
    prompt_id = str(payload.get("prompt_id") or payload.get("id") or payload.get("name") or "").strip()
    if not prompt_id:
        raise ValueError("prompt_id is required")
    existing = get_manager().get_prompt(prompt_id) or get_manager().get_prompt_by_name(prompt_id) or {}
    mode = str(payload.get("mode") or "override")
    target_id = prompt_id
    if mode in {"duplicate", "fork"}:
        target_id = safe_prompt_id(payload.get("new_prompt_id") or payload.get("new_name") or f"{prompt_id}_copy")
    body = str(payload.get("content") if "content" in payload else payload.get("body") or prompt_text(existing))
    name = str(payload.get("new_name") or payload.get("name") or existing.get("name") or target_id).strip() or target_id
    description = str(payload.get("description") if "description" in payload else existing.get("description") or "")
    variables = payload.get("variables") if isinstance(payload.get("variables"), list) else variables_from_text(body)
    metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
    prompt = upsert_user_prompt(target_id, name=name, body=body, description=description, variables=variables, metadata={**dict(metadata), "edited_via": "prompt_control_center", "overrides_prompt_id": prompt_id if target_id == prompt_id else ""})
    return {"prompt": normalize_prompt(prompt, read_state(), set()), "validation": validate_prompt_template(body, variables), "mode": mode}


def duplicate_prompt(prompt_id: str, new_prompt_id: str = "") -> dict[str, Any]:
    draft = prompt_editor_draft(prompt_id)
    source = draft.get("prompt") if isinstance(draft.get("prompt"), dict) else {}
    return save_prompt_edit({"prompt_id": prompt_id, "new_prompt_id": new_prompt_id or f"{prompt_id}_copy_{uuid.uuid4().hex[:6]}", "content": draft.get("content", ""), "description": source.get("description", ""), "mode": "duplicate"})
