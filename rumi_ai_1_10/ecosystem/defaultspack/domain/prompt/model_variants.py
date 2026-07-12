from __future__ import annotations

import copy
from typing import Any, Mapping

from domain.prompt.variant_catalog import (
    resolve_model_prompt_preferences,
    resolve_profile_prompt_candidates,
)
from domain.prompt.variant_selector import select_prompt_variants


def apply_model_prompt_variants(
    ir: Any,
    model: str,
    context: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Append prompt variants selected for the final routed model.

    Prompt bodies still resolve through the trusted effective-prompt resolver.
    The optional selector is fail-soft and never grants tools, permissions,
    provider access, or policy exceptions.
    """

    runtime_context = context if isinstance(context, dict) else {}
    try:
        profile = _load_active_profile(runtime_context)
        if not profile:
            return ir, _store_result(
                runtime_context,
                _empty_result(model, "no_active_profile"),
            )
        preferences = resolve_model_prompt_preferences(model)
        candidates, candidate_diagnostics = resolve_profile_prompt_candidates(
            profile,
            runtime_context,
        )
        if not candidates:
            result = _empty_result(model, "no_prompt_variant_candidates")
            result["diagnostics"] = candidate_diagnostics
            return ir, _store_result(runtime_context, result)

        selection = select_prompt_variants(
            candidates,
            preferences,
            model=model,
            provider_id=str(preferences.get("provider_id") or ""),
        )
        selection["original_model"] = _original_model(runtime_context, model)
        selection["preference_sources"] = list(
            preferences.get("source_chain") or []
        )
        selection["diagnostics"] = [
            *candidate_diagnostics,
            *selection.get("diagnostics", []),
        ]
        selected_text = _selected_prompt_text(selection)
        if selected_text:
            adapted = _append_system_text(ir, selected_text)
            selection["status"] = "applied"
        elif selection.get("selected"):
            adapted = ir
            selection["status"] = "selected_existing"
        else:
            adapted = ir
            selection["status"] = "no_selection"
        _store_result(runtime_context, selection)
        _record_prompt_selection(runtime_context, selection)
        return adapted, selection
    except Exception as exc:
        result = _empty_result(model, "selection_error")
        result["diagnostics"] = [
            {
                "severity": "warning",
                "code": "model_prompt_selection_error",
                "error_type": exc.__class__.__name__,
            }
        ]
        return ir, _store_result(runtime_context, result)


def _load_active_profile(context: Mapping[str, Any]) -> dict[str, Any]:
    active = context.get("active_startup_profile")
    profile_id = str(
        context.get("active_startup_profile_id")
        or (active.get("profile_id") if isinstance(active, Mapping) else "")
        or context.get("profile_id")
        or ""
    ).strip()
    if not profile_id:
        return {}
    try:
        from core_runtime.profile_runtime_selection import (
            apply_profile_graph_selection,
        )
        from core_runtime.profile_workspace import ProfileWorkspaceManager

        profile = ProfileWorkspaceManager().load_profile_yaml(profile_id)
    except Exception:
        return {}
    if not isinstance(profile, Mapping):
        return {}
    normalized = dict(profile)
    normalized.setdefault("profile_id", profile_id)
    try:
        return apply_profile_graph_selection(normalized)
    except Exception:
        return normalized


def _append_system_text(ir: Any, text: str) -> Any:
    from domain.chat.ir import RumiIRMessage
    from domain.chat.ir_blocks import RumiIRBlock

    adapted = copy.deepcopy(ir)
    messages = getattr(adapted, "messages", None)
    if not isinstance(messages, list):
        return ir
    system_message = next(
        (
            message
            for message in messages
            if str(getattr(message, "role", "") or "") == "system"
        ),
        None,
    )
    if system_message is None:
        messages.insert(
            0,
            RumiIRMessage(
                conversation_id=str(
                    getattr(adapted, "conversation_id", "") or ""
                ),
                role="system",
                content=[RumiIRBlock(type="text", text=text)],
            ),
        )
        return adapted
    blocks = getattr(system_message, "content", None)
    if not isinstance(blocks, list):
        system_message.content = [RumiIRBlock(type="text", text=text)]
        return adapted
    text_block = next(
        (
            block
            for block in blocks
            if str(getattr(block, "type", "") or "") == "text"
            and bool(getattr(block, "model_visible", True))
        ),
        None,
    )
    if text_block is None:
        blocks.append(RumiIRBlock(type="text", text=text))
        return adapted
    existing = str(getattr(text_block, "text", "") or "").rstrip()
    text_block.text = f"{existing}\n\n{text}" if existing else text
    return adapted


def _record_prompt_selection(
    context: dict[str, Any],
    selection: Mapping[str, Any],
) -> None:
    segments = _selection_usage_segments(selection)
    if not segments:
        return
    try:
        from domain.prompt.usage import (
            append_runtime_prompt_segment,
            compact_prompt_usage_for_metadata,
        )

        usage = context.get("prompt_usage")
        existing_ids = {
            str(item.get("id") or "")
            for item in (
                usage.get("segments")
                if isinstance(usage, Mapping)
                and isinstance(usage.get("segments"), list)
                else []
            )
            if isinstance(item, Mapping)
        }
        for segment in segments:
            if segment["id"] not in existing_ids:
                usage = append_runtime_prompt_segment(usage, segment)
        context["prompt_usage"] = compact_prompt_usage_for_metadata(usage)
    except Exception:
        pass
    _record_trace_segments(context, selection, segments)


def _record_trace_segments(
    context: Mapping[str, Any],
    selection: Mapping[str, Any],
    segments: list[dict[str, Any]],
) -> None:
    trace_info = context.get("ai_input_trace")
    if not isinstance(trace_info, Mapping):
        return
    trace_id = str(trace_info.get("trace_id") or "").strip()
    profile_id = str(
        trace_info.get("profile_id")
        or context.get("active_startup_profile_id")
        or context.get("profile_id")
        or ""
    ).strip()
    if not trace_id or not profile_id:
        return
    try:
        from core_runtime.ai_input_trace_store import AiInputTraceStore

        store = AiInputTraceStore()
        trace = store.get_trace(profile_id, trace_id)
        if not isinstance(trace, dict):
            return
        existing = (
            trace.get("runtime_prompt_segments")
            if isinstance(trace.get("runtime_prompt_segments"), list)
            else []
        )
        ids = {
            str(item.get("id") or "")
            for item in existing
            if isinstance(item, Mapping)
        }
        existing.extend(
            segment for segment in segments if segment["id"] not in ids
        )
        trace["runtime_prompt_segments"] = existing
        trace["model_prompt_selection"] = _compact_selection(selection)
        provider_summary = (
            dict(trace.get("provider_payload_summary"))
            if isinstance(trace.get("provider_payload_summary"), Mapping)
            else {}
        )
        provider_summary["model_prompt_variant_count"] = len(
            selection.get("selected", [])
        )
        provider_summary["model_prompt_variant_ids"] = [
            str(item.get("prompt_id") or "")
            for item in selection.get("selected", [])
            if isinstance(item, Mapping)
        ]
        trace["provider_payload_summary"] = provider_summary
        store.save_trace(profile_id, trace)
    except Exception:
        return


def _selection_usage_segments(
    selection: Mapping[str, Any],
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for key, status in (("selected", "active"), ("disabled", "disabled")):
        entries = selection.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            prompt_id = str(entry.get("prompt_id") or "").strip()
            if not prompt_id:
                continue
            candidate_tokens = _estimate_tokens(str(entry.get("text") or ""))
            already_active = bool(entry.get("already_active"))
            counted_tokens = (
                candidate_tokens
                if status == "active" and not already_active
                else 0
            )
            segments.append(
                _usage_segment(
                    selection,
                    entry,
                    prompt_id=prompt_id,
                    status=status,
                    counted_tokens=counted_tokens,
                    candidate_tokens=candidate_tokens,
                    already_active=already_active,
                )
            )
    return segments


def _usage_segment(
    selection: Mapping[str, Any],
    entry: Mapping[str, Any],
    *,
    prompt_id: str,
    status: str,
    counted_tokens: int,
    candidate_tokens: int,
    already_active: bool,
) -> dict[str, Any]:
    return {
        "id": f"model_prompt_variant:{entry.get('slot')}:{prompt_id}",
        "edge_id": "",
        "prompt_id": prompt_id,
        "label": prompt_id,
        "kind": "model_prompt_variant",
        "port": "system",
        "status": status,
        "enabled": status == "active",
        "source": f"{entry.get('source_type') or 'prompt'}:{prompt_id}",
        "source_type": "model_prompt_variant",
        "tokens": counted_tokens,
        "reason": entry.get("reason"),
        "allow_disable": False,
        "editable": False,
        "readonly_reason": (
            "Selected from trusted model and prompt declarations."
        ),
        "preview": str(entry.get("preview") or ""),
        "metadata": {
            "slot": entry.get("slot"),
            "tags": entry.get("tags", []),
            "score": entry.get("score"),
            "preference_score": entry.get("preference_score"),
            "matched_prefer": entry.get("matched_prefer", []),
            "matched_avoid": entry.get("matched_avoid", []),
            "explicit": bool(entry.get("explicit")),
            "already_active": already_active,
            "candidate_tokens": candidate_tokens,
            "model": selection.get("model"),
            "original_model": selection.get("original_model"),
        },
    }


def _selected_prompt_text(selection: Mapping[str, Any]) -> str:
    return "\n\n".join(
        str(item.get("text") or "").strip()
        for item in selection.get("selected", [])
        if isinstance(item, Mapping)
        and not bool(item.get("already_active"))
        and str(item.get("text") or "").strip()
    )


def _store_result(
    context: dict[str, Any],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    context["model_prompt_selection"] = _compact_selection(selection)
    return dict(selection)


def _compact_selection(selection: Mapping[str, Any]) -> dict[str, Any]:
    def compact_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value)
            for key, value in entry.items()
            if key not in {"text", "metadata", "source"}
        }

    return {
        "status": selection.get("status"),
        "model": selection.get("model"),
        "original_model": selection.get("original_model"),
        "provider_id": selection.get("provider_id"),
        "preferences": copy.deepcopy(selection.get("preferences", {})),
        "preference_sources": copy.deepcopy(
            selection.get("preference_sources", [])
        ),
        "selected": [
            compact_entry(item)
            for item in selection.get("selected", [])
            if isinstance(item, Mapping)
        ],
        "disabled": [
            compact_entry(item)
            for item in selection.get("disabled", [])
            if isinstance(item, Mapping)
        ],
        "diagnostics": copy.deepcopy(selection.get("diagnostics", [])),
    }


def _empty_result(model: str, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "model": str(model or "").strip(),
        "original_model": str(model or "").strip(),
        "provider_id": _provider_from_model(model),
        "preferences": {"prefer": {}, "avoid": {}},
        "preference_sources": [],
        "selected": [],
        "disabled": [],
        "diagnostics": [],
    }


def _original_model(context: Mapping[str, Any], fallback: str) -> str:
    routing = context.get("model_routing")
    if isinstance(routing, Mapping):
        original = str(routing.get("original_model") or "").strip()
        if original:
            return original
    return str(fallback or "").strip()


def _provider_from_model(model: Any) -> str:
    value = str(model or "").strip()
    return value.split("/", 1)[0] if "/" in value else ""


def _estimate_tokens(text: str) -> int:
    try:
        from core_runtime.ai_input_token_estimator import estimate_tokens

        return int(estimate_tokens(text))
    except Exception:
        return max(0, (len(text) + 3) // 4)
