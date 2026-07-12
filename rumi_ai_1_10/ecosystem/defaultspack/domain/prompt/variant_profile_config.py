from __future__ import annotations

from typing import Any, Mapping


_NAMESPACED_SELECTION_KEYS = (
    "prompt_tags",
    "prompt_slot",
    "prompt_priority",
    "prompt_fallback",
    "prompt_explicit",
    "prompt_selection_mode",
    "prompt_slot_priority",
)
_SELECTION_ALIASES = (
    "tags",
    "slot",
    "priority",
    "fallback",
    "explicit",
    "selection_mode",
    "mode",
    "slot_priority",
)


def profile_selection_config(profile: Mapping[str, Any]) -> dict[str, Any]:
    metadata = (
        profile.get("metadata")
        if isinstance(profile.get("metadata"), Mapping)
        else {}
    )
    for key in ("prompt_selection", "model_prompt_selection"):
        value = metadata.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def candidate_declarations(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for item in _list_value(config.get("candidates")):
        declaration = _candidate_declaration(item)
        if declaration:
            declarations.append(declaration)
    for item in _list_value(config.get("selected_prompt_ids")):
        declaration = _candidate_declaration(item)
        if declaration:
            declaration["explicit"] = True
            declarations.append(declaration)

    slots = config.get("slots") if isinstance(config.get("slots"), Mapping) else {}
    for slot_id in sorted(slots):
        raw_slot = slots.get(slot_id)
        if not isinstance(raw_slot, Mapping):
            continue
        declarations.extend(
            _slot_candidate_declarations(str(slot_id), raw_slot)
        )

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for declaration in declarations:
        key = (
            str(declaration.get("slot") or ""),
            str(declaration.get("prompt_id") or ""),
        )
        current = deduped.get(key, {})
        deduped[key] = {
            **current,
            **declaration,
            "explicit": bool(
                current.get("explicit") or declaration.get("explicit")
            ),
            "already_active": bool(
                current.get("already_active")
                or declaration.get("already_active")
            ),
        }
    return [deduped[key] for key in sorted(deduped)]


def merge_selection_metadata(
    *layers: tuple[Any, bool],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    nested: dict[str, Any] = {}
    for layer, allow_aliases in layers:
        if not isinstance(layer, Mapping):
            continue
        for key in _NAMESPACED_SELECTION_KEYS:
            if key in layer:
                merged[key] = layer[key]
        selection = layer.get("prompt_selection")
        if isinstance(selection, Mapping):
            nested.update(selection)
        if allow_aliases:
            for key in _SELECTION_ALIASES:
                if key in layer:
                    nested[key] = layer[key]
    if nested:
        merged["prompt_selection"] = nested
    return merged


def prompt_usage_states(
    context: Mapping[str, Any],
) -> tuple[set[str], dict[str, tuple[str, ...]]]:
    """Return active and blocked prompt IDs from the compiled AI input."""

    usage = context.get("prompt_usage")
    segments = usage.get("segments") if isinstance(usage, Mapping) else None
    if not isinstance(segments, list):
        return set(), {}
    active: set[str] = set()
    blocked: dict[str, set[str]] = {}
    for segment in segments:
        if not _is_prompt_usage_segment(segment):
            continue
        prompt_id = str(segment.get("prompt_id") or "").strip()
        if not prompt_id:
            continue
        status = str(segment.get("status") or "").strip() or "unknown"
        if status == "active":
            active.add(prompt_id)
        else:
            blocked.setdefault(prompt_id, set()).add(status)
    for prompt_id in active:
        blocked.pop(prompt_id, None)
    return active, {
        prompt_id: tuple(sorted(states))
        for prompt_id, states in blocked.items()
    }


def prompt_ids_match(requested: str, resolved: str) -> bool:
    requested_id = str(requested or "").strip()
    resolved_id = str(resolved or "").strip()
    if not requested_id or not resolved_id:
        return False
    aliases = {requested_id}
    if "." in requested_id:
        aliases.add(requested_id.rsplit(".", 1)[-1])
    return resolved_id in aliases


def int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _slot_candidate_declarations(
    slot_id: str,
    raw_slot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    fallback_id = str(raw_slot.get("fallback_prompt_id") or "").strip()
    pinned_id = str(
        raw_slot.get("selected_prompt_id")
        or raw_slot.get("pinned_prompt_id")
        or ""
    ).strip()
    mode = str(
        raw_slot.get("selection_mode")
        or raw_slot.get("mode")
        or "best_match"
    )
    slot_priority = int_value(
        raw_slot.get("slot_priority", raw_slot.get("priority")),
        default=100,
    )
    slot_items = list(_list_value(raw_slot.get("candidates")))
    listed_ids = {
        str(_candidate_declaration(item).get("prompt_id") or "")
        for item in slot_items
    }
    for prompt_id in (fallback_id, pinned_id):
        if prompt_id and prompt_id not in listed_ids:
            slot_items.append(prompt_id)
            listed_ids.add(prompt_id)

    declarations: list[dict[str, Any]] = []
    for item in slot_items:
        declaration = _candidate_declaration(item)
        if not declaration:
            continue
        declaration["slot"] = str(declaration.get("slot") or slot_id)
        declaration["selection_mode"] = str(
            declaration.get("selection_mode") or mode
        )
        declaration["slot_priority"] = int_value(
            declaration.get("slot_priority"),
            default=slot_priority,
        )
        if declaration["prompt_id"] == fallback_id:
            declaration["fallback"] = True
        if declaration["prompt_id"] == pinned_id:
            declaration["explicit"] = True
        declarations.append(declaration)
    return declarations


def _candidate_declaration(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        prompt_id = value.strip()
        return {"prompt_id": prompt_id} if prompt_id else {}
    if not isinstance(value, Mapping):
        return {}
    prompt_id = str(
        value.get("prompt_id")
        or value.get("id")
        or value.get("prompt")
        or ""
    ).strip()
    return {**dict(value), "prompt_id": prompt_id} if prompt_id else {}


def _is_prompt_usage_segment(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if str(value.get("kind") or "") in {"skill", "model_prompt_variant"}:
        return False
    return str(value.get("port") or "") in {"system", "developer"}


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [
            item.strip()
            for item in value.replace("\n", ",").split(",")
            if item.strip()
        ]
    return list(value) if isinstance(value, (list, tuple, set)) else []
