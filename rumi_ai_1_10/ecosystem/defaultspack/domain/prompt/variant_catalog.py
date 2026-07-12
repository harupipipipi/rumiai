from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from domain.prompt.variant_profile_config import (
    candidate_declarations as _candidate_declarations,
    int_value as _int_value,
    merge_selection_metadata as _merge_selection_metadata,
    profile_selection_config as _profile_selection_config,
    prompt_ids_match as _prompt_ids_match,
    prompt_usage_states as _prompt_usage_states,
)
from domain.prompt.variant_selector import (
    PromptVariantCandidate,
    merge_model_prompt_preferences,
    normalize_prompt_variant_metadata,
)


_MAX_CANDIDATES = 64


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
    active_prompt_ids, blocked_prompt_states = _prompt_usage_states(context)
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
        blocked_states = blocked_prompt_states.get(prompt_id, ())
        if blocked_states and not declaration.get("already_active"):
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "prompt_variant_blocked_by_existing_prompt_state",
                    "prompt_id": prompt_id,
                    "states": list(blocked_states),
                }
            )
            continue
        source_pack_id = str(
            declaration.get("source_pack_id")
            or declaration.get("pack_id")
            or ""
        ).strip()
        cache_key = (prompt_id, source_pack_id)
        if cache_key not in resolved_cache:
            resolved = _resolve_candidate_safely(
                diagnostics,
                profile_id=profile_id,
                base_pack=base_pack,
                source_pack_id=source_pack_id,
                prompt_id=prompt_id,
                workspace=workspace,
            )
            if resolved is None:
                continue
            resolved_cache[cache_key] = resolved
        effective = resolved_cache[cache_key]
        resolved_prompt_id = str(
            effective.get("prompt_id") or prompt_id
        ).strip()
        if not _prompt_ids_match(prompt_id, resolved_prompt_id):
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "prompt_variant_resolved_unexpected_prompt",
                    "prompt_id": prompt_id,
                    "resolved_prompt_id": resolved_prompt_id,
                }
            )
            continue
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

        candidate = _candidate_from_resolution(
            declaration,
            effective,
            prompt_id=prompt_id,
            profile_metadata=prompt_overrides.get(prompt_id),
            text=text,
        )
        if candidate is None:
            if not declaration.get("already_active"):
                diagnostics.append(
                    {
                        "severity": "warning",
                        "code": "prompt_variant_missing_slot",
                        "prompt_id": prompt_id,
                    }
                )
            continue
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


def _resolve_candidate_safely(
    diagnostics: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any] | None:
    prompt_id = str(kwargs.get("prompt_id") or "")
    try:
        resolved = _resolve_effective_candidate(**kwargs)
    except Exception as exc:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "prompt_variant_resolution_error",
                "prompt_id": prompt_id,
                "error_type": exc.__class__.__name__,
            }
        )
        return None
    if not isinstance(resolved, Mapping):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "prompt_variant_invalid_resolution",
                "prompt_id": prompt_id,
            }
        )
        return None
    return dict(resolved)


def _candidate_from_resolution(
    declaration: Mapping[str, Any],
    effective: Mapping[str, Any],
    *,
    prompt_id: str,
    profile_metadata: Any,
    text: str,
) -> PromptVariantCandidate | None:
    effective_metadata = (
        effective.get("metadata")
        if isinstance(effective.get("metadata"), Mapping)
        else {}
    )
    profile_layer = profile_metadata if isinstance(profile_metadata, Mapping) else {}
    merged_metadata = _merge_selection_metadata(
        (effective_metadata, False),
        (profile_layer, True),
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
        return None
    return PromptVariantCandidate(
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
            "source_pack_trusted": effective.get("source_pack_trusted"),
        },
        slot_priority=int(normalized["slot_priority"]),
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


def _provider_from_model(model: Any) -> str:
    value = str(model or "").strip()
    return value.split("/", 1)[0] if "/" in value else ""
