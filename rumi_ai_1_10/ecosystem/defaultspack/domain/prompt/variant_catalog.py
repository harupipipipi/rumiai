from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from domain.prompt.variant_selector import (
    PromptVariantCandidate,
    merge_model_prompt_preferences,
    normalize_prompt_variant_metadata,
)


_MAX_CANDIDATES = 64
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


def resolve_model_prompt_preferences(model: str) -> dict[str, Any]:
    """Resolve provider and exact-model prompt preference declarations."""

    model_record, provider_record = _model_catalog_records(model)
    provider_preferences = _preference_declaration(provider_record)
    model_preferences = _preference_declaration(model_record)
    merged = merge_model_prompt_preferences(
        provider_preferences,
        model_preferences,
    )
    provider_id = str(
        (model_record or {}).get("provider_id")
        or (provider_record or {}).get("provider_id")
        or _provider_from_model(model)
    ).strip()
    return {
        **merged,
        "model": str(model or "").strip(),
        "provider_id": provider_id,
        "source_chain": [
            source
            for source, declaration in (
                ("provider", provider_preferences),
                ("model", model_preferences),
            )
            if declaration
        ],
    }


def resolve_profile_prompt_candidates(
    profile: Mapping[str, Any],
    context: Mapping[str, Any],
) -> tuple[list[PromptVariantCandidate], list[dict[str, Any]]]:
    """Resolve trusted prompt-variant candidates declared by a profile."""

    selection_config = _profile_selection_config(profile)
    active_prompt_ids = _active_prompt_ids(context)
    if not selection_config and not active_prompt_ids:
        return [], []

    declarations = [
        {
            "prompt_id": prompt_id,
            "explicit": True,
            "already_active": True,
        }
        for prompt_id in sorted(active_prompt_ids)
    ]
    declarations.extend(_candidate_declarations(selection_config))
    if not declarations:
        return [], []

    profile_id = str(profile.get("profile_id") or "").strip()
    base_pack = (
        str(profile.get("base_pack") or "defaultspack").strip()
        or "defaultspack"
    )
    workspace = _profile_workspace(profile_id)
    prompt_overrides = (
        selection_config.get("prompts")
        if isinstance(selection_config.get("prompts"), Mapping)
        else {}
    )
    diagnostics: list[dict[str, Any]] = []
    resolved_cache: dict[tuple[str, str], dict[str, Any]] = {}
    candidates: dict[tuple[str, str], PromptVariantCandidate] = {}

    for declaration in declarations[:_MAX_CANDIDATES]:
        prompt_id = str(declaration.get("prompt_id") or "").strip()
        if not prompt_id:
            continue
        source_pack_id = str(
            declaration.get("source_pack_id")
            or declaration.get("pack_id")
            or ""
        ).strip()
        cache_key = (prompt_id, source_pack_id)
        if cache_key not in resolved_cache:
            resolved_cache[cache_key] = _resolve_effective_candidate(
                profile_id=profile_id,
                base_pack=base_pack,
                source_pack_id=source_pack_id,
                prompt_id=prompt_id,
                workspace=workspace,
            )
        effective = resolved_cache[cache_key]
        text = str(
            effective.get("final_content") or effective.get("content") or ""
        )
        if not text:
            if not declaration.get("already_active"):
                diagnostics.append(
                    {
                        "severity": "warning",
                        "code": "prompt_variant_unresolved",
                        "prompt_id": prompt_id,
                        "source_type": effective.get("source_type"),
                    }
                )
            continue

        effective_metadata = (
            effective.get("metadata")
            if isinstance(effective.get("metadata"), Mapping)
            else {}
        )
        profile_metadata = (
            prompt_overrides.get(prompt_id)
            if isinstance(prompt_overrides.get(prompt_id), Mapping)
            else {}
        )
        merged_metadata = _merge_selection_metadata(
            (effective_metadata, False),
            (profile_metadata, True),
            (declaration, True),
        )
        normalized = normalize_prompt_variant_metadata(
            merged_metadata,
            prompt_id=prompt_id,
            slot_hint=str(declaration.get("slot") or ""),
            fallback_hint=bool(declaration.get("fallback")),
            explicit_hint=bool(declaration.get("explicit")),
            selection_mode_hint=str(
                declaration.get("selection_mode") or "best_match"
            ),
            slot_priority_hint=_int_value(
                declaration.get("slot_priority"),
                default=100,
            ),
        )
        if not normalized["slot"]:
            if not declaration.get("already_active"):
                diagnostics.append(
                    {
                        "severity": "warning",
                        "code": "prompt_variant_missing_slot",
                        "prompt_id": prompt_id,
                    }
                )
            continue

        candidate = PromptVariantCandidate(
            prompt_id=prompt_id,
            slot=normalized["slot"],
            tags=tuple(normalized["tags"]),
            priority=int(normalized["priority"]),
            fallback=bool(normalized["fallback"]),
            explicit=bool(normalized["explicit"]),
            selection_mode=str(normalized["selection_mode"]),
            text=text,
            source=str(effective.get("source") or ""),
            source_type=str(effective.get("source_type") or ""),
            metadata={
                "already_active": bool(declaration.get("already_active")),
                "source_chain": (
                    effective.get("source_chain")
                    if isinstance(effective.get("source_chain"), list)
                    else []
                ),
                "source_pack_id": effective.get("source_pack_id"),
                "source_pack_trusted": effective.get(
                    "source_pack_trusted"
                ),
            },
            slot_priority=int(normalized["slot_priority"]),
        )
        key = (candidate.slot, candidate.prompt_id)
        candidates[key] = _merge_duplicate_candidate(
            candidates.get(key),
            candidate,
        )

    if len(declarations) > _MAX_CANDIDATES:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "prompt_variant_candidate_limit_applied",
                "candidate_count": len(declarations),
                "limit": _MAX_CANDIDATES,
            }
        )
    return (
        sorted(
            candidates.values(),
            key=lambda item: (
                item.slot_priority,
                item.slot,
                item.prompt_id,
            ),
        ),
        diagnostics,
    )


def _merge_duplicate_candidate(
    current: PromptVariantCandidate | None,
    incoming: PromptVariantCandidate,
) -> PromptVariantCandidate:
    if current is None:
        return incoming
    metadata = {**current.metadata, **incoming.metadata}
    metadata["already_active"] = bool(
        current.metadata.get("already_active")
        or incoming.metadata.get("already_active")
    )
    return replace(
        incoming,
        explicit=current.explicit or incoming.explicit,
        metadata=metadata,
    )


def _profile_selection_config(profile: Mapping[str, Any]) -> dict[str, Any]:
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


def _candidate_declarations(config: Mapping[str, Any]) -> list[dict[str, Any]]:
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
    slot_priority = _int_value(
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
        declaration["slot_priority"] = _int_value(
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


def _resolve_effective_candidate(
    *,
    profile_id: str,
    base_pack: str,
    source_pack_id: str,
    prompt_id: str,
    workspace: Mapping[str, Any],
) -> dict[str, Any]:
    from domain.prompt.effective import resolve_effective_prompt

    return resolve_effective_prompt(
        {
            "profile_id": profile_id,
            "base_pack": source_pack_id or base_pack,
            "source_pack_id": source_pack_id,
            "system_prompt_id": prompt_id,
            "workspace": dict(workspace),
        }
    )


def _merge_selection_metadata(
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


def _active_prompt_ids(context: Mapping[str, Any]) -> set[str]:
    usage = context.get("prompt_usage")
    segments = usage.get("segments") if isinstance(usage, Mapping) else None
    if not isinstance(segments, list):
        return set()
    output: set[str] = set()
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        if str(segment.get("status") or "") != "active":
            continue
        if str(segment.get("kind") or "") == "model_prompt_variant":
            continue
        prompt_id = str(segment.get("prompt_id") or "").strip()
        if prompt_id:
            output.add(prompt_id)
    return output


def _profile_workspace(profile_id: str) -> dict[str, Any]:
    if not profile_id:
        return {}
    try:
        from core_runtime.profile_workspace import (
            ProfileWorkspaceManager,
            profile_workspace_payload,
        )

        return profile_workspace_payload(
            ProfileWorkspaceManager().paths_for_profile(profile_id)
        )
    except Exception:
        return {}


def _model_catalog_records(
    model: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_ref = str(model or "").strip()
    try:
        from domain.ai_client.model_search import get_model_capabilities
        from domain.ai_client.providers import get_provider_catalog_map

        model_record = get_model_capabilities(model_ref) or {}
        providers = get_provider_catalog_map()
    except Exception:
        return {}, {}
    provider_id = str(
        model_record.get("provider_id") or _provider_from_model(model_ref)
    ).strip()
    provider_record = (
        dict(providers.get(provider_id))
        if isinstance(providers, Mapping)
        and isinstance(providers.get(provider_id), Mapping)
        else {}
    )
    return dict(model_record), provider_record


def _preference_declaration(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    direct = value.get("prompt_preferences")
    if isinstance(direct, Mapping):
        return dict(direct)
    for container_key in ("metadata", "config"):
        container = value.get(container_key)
        if not isinstance(container, Mapping):
            continue
        direct = container.get("prompt_preferences")
        if isinstance(direct, Mapping):
            return dict(direct)
        nested_config = container.get("config")
        if isinstance(nested_config, Mapping):
            direct = nested_config.get("prompt_preferences")
            if isinstance(direct, Mapping):
                return dict(direct)
    return {}


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [
            item.strip()
            for item in value.replace("\n", ",").split(",")
            if item.strip()
        ]
    return list(value) if isinstance(value, (list, tuple, set)) else []


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _provider_from_model(model: Any) -> str:
    value = str(model or "").strip()
    return value.split("/", 1)[0] if "/" in value else ""
