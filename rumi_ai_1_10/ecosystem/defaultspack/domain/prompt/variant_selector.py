from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


_TAG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_MAX_TAGS = 64
_MAX_CANDIDATES = 64
_MAX_WEIGHT = 10_000
_DEFAULT_PREFER_WEIGHT = 100
_DEFAULT_AVOID_WEIGHT = 100
_ADDITIVE_MODES = {"all", "additive"}


@dataclass(frozen=True)
class PromptVariantCandidate:
    """Resolved prompt variant ready for deterministic selection."""

    prompt_id: str
    slot: str
    tags: tuple[str, ...]
    priority: int
    fallback: bool
    explicit: bool
    selection_mode: str
    text: str
    source: str
    source_type: str
    metadata: dict[str, Any]
    slot_priority: int = 100


@dataclass(frozen=True)
class PromptVariantScore:
    """Score details for one candidate in a model prompt slot."""

    candidate: PromptVariantCandidate
    matched_prefer: tuple[str, ...]
    matched_avoid: tuple[str, ...]
    preference_score: int
    total_score: int
    positive_match: bool


def normalize_model_prompt_preferences(value: Any) -> dict[str, dict[str, int]]:
    """Normalize model prompt preferences into positive weighted tag maps."""

    raw = value if isinstance(value, Mapping) else {}
    prefer_value = raw.get("prefer", raw.get("preferred", raw.get("tags")))
    avoid_value = raw.get("avoid", raw.get("avoided"))
    return {
        "prefer": _normalize_weighted_tags(
            prefer_value,
            default_weight=_DEFAULT_PREFER_WEIGHT,
        ),
        "avoid": _normalize_weighted_tags(
            avoid_value,
            default_weight=_DEFAULT_AVOID_WEIGHT,
        ),
    }


def merge_model_prompt_preferences(*values: Any) -> dict[str, dict[str, int]]:
    """Merge preference layers from broad defaults to exact overrides."""

    prefer: dict[str, int] = {}
    avoid: dict[str, int] = {}
    for value in values:
        normalized = normalize_model_prompt_preferences(value)
        prefer.update(normalized["prefer"])
        avoid.update(normalized["avoid"])
    return {"prefer": prefer, "avoid": avoid}


def normalize_prompt_variant_metadata(
    value: Any,
    *,
    prompt_id: str = "",
    slot_hint: str = "",
    fallback_hint: bool = False,
    explicit_hint: bool = False,
    selection_mode_hint: str = "",
    slot_priority_hint: int = 100,
) -> dict[str, Any]:
    """Normalize namespaced metadata for one prompt variant.

    Generic aliases are accepted only inside ``prompt_selection``. Top-level
    fields must use ``prompt_*`` names, preventing unrelated component metadata
    from opting into model routing accidentally.
    """

    raw = dict(value) if isinstance(value, Mapping) else {}
    nested = (
        dict(raw.get("prompt_selection"))
        if isinstance(raw.get("prompt_selection"), Mapping)
        else {}
    )
    tags = raw.get("prompt_tags", nested.get("tags"))
    slot = raw.get("prompt_slot", nested.get("slot", slot_hint))
    priority = raw.get("prompt_priority", nested.get("priority"))
    fallback = raw.get("prompt_fallback", nested.get("fallback"))
    explicit = raw.get("prompt_explicit", nested.get("explicit"))
    mode = raw.get(
        "prompt_selection_mode",
        nested.get("selection_mode", nested.get("mode", selection_mode_hint)),
    )
    slot_priority = raw.get(
        "prompt_slot_priority",
        nested.get("slot_priority", slot_priority_hint),
    )
    return {
        "prompt_id": str(prompt_id or "").strip(),
        "tags": _normalize_tags(tags),
        "slot": _normalize_tag(slot),
        "priority": _bounded_int(priority, default=0),
        "fallback": _coerce_bool(fallback, default=fallback_hint),
        "explicit": _coerce_bool(explicit, default=explicit_hint),
        "selection_mode": _normalize_selection_mode(mode),
        "slot_priority": _bounded_int(
            slot_priority,
            default=slot_priority_hint,
        ),
    }


def score_prompt_variant(
    candidate: PromptVariantCandidate,
    preferences: Any,
) -> PromptVariantScore:
    """Score one variant against normalized model prompt preferences."""

    normalized = normalize_model_prompt_preferences(preferences)
    preferred = normalized["prefer"]
    avoided = normalized["avoid"]
    matched_prefer = tuple(tag for tag in candidate.tags if tag in preferred)
    matched_avoid = tuple(tag for tag in candidate.tags if tag in avoided)
    preference_score = sum(preferred[tag] for tag in matched_prefer) - sum(
        avoided[tag] for tag in matched_avoid
    )
    return PromptVariantScore(
        candidate=candidate,
        matched_prefer=matched_prefer,
        matched_avoid=matched_avoid,
        preference_score=preference_score,
        total_score=preference_score + candidate.priority,
        positive_match=bool(matched_prefer) and preference_score > 0,
    )


def select_prompt_variants(
    candidates: Sequence[PromptVariantCandidate],
    preferences: Any,
    *,
    model: str = "",
    provider_id: str = "",
) -> dict[str, Any]:
    """Select variants deterministically, one winner per best-match slot."""

    normalized = normalize_model_prompt_preferences(preferences)
    grouped: dict[str, list[PromptVariantCandidate]] = {}
    diagnostics: list[dict[str, Any]] = []
    if len(candidates) > _MAX_CANDIDATES:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "prompt_variant_candidate_limit_applied",
                "candidate_count": len(candidates),
                "limit": _MAX_CANDIDATES,
            }
        )
    for candidate in candidates[:_MAX_CANDIDATES]:
        if not candidate.slot:
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "prompt_variant_missing_slot",
                    "prompt_id": candidate.prompt_id,
                }
            )
            continue
        grouped.setdefault(candidate.slot, []).append(candidate)

    selected: list[dict[str, Any]] = []
    disabled: list[dict[str, Any]] = []
    for slot in sorted(grouped):
        slot_candidates = grouped[slot]
        scored = [
            score_prompt_variant(candidate, normalized)
            for candidate in slot_candidates
        ]
        mode, mode_diagnostic = _slot_selection_mode(slot_candidates)
        if mode_diagnostic:
            diagnostics.append({**mode_diagnostic, "slot": slot})
        if mode == "all":
            winners = sorted(scored, key=_score_sort_key)
            reason = "additive_slot"
        else:
            explicit = [score for score in scored if score.candidate.explicit]
            positive = [score for score in scored if score.positive_match]
            fallbacks = [score for score in scored if score.candidate.fallback]
            pool = explicit or positive or fallbacks or scored
            winners = sorted(pool, key=_score_sort_key)[:1]
            reason = (
                "explicit_profile_selection"
                if explicit
                else "positive_trait_match"
                if positive
                else "fallback_no_positive_match"
                if fallbacks
                else "priority_no_trait_match"
            )
        winner_ids = {
            (score.candidate.slot, score.candidate.prompt_id) for score in winners
        }
        for score in sorted(scored, key=_score_sort_key):
            payload = _score_payload(
                score,
                model=model,
                provider_id=provider_id,
            )
            key = (score.candidate.slot, score.candidate.prompt_id)
            if key in winner_ids:
                payload.update(status="selected", reason=reason)
                selected.append(payload)
            else:
                payload.update(
                    status="disabled",
                    reason=(
                        "explicit_candidate_selected"
                        if reason == "explicit_profile_selection"
                        else "lower_ranked_in_slot"
                    ),
                )
                disabled.append(payload)
        diagnostics.append(
            {
                "severity": "info",
                "code": "prompt_variant_slot_selected",
                "slot": slot,
                "selection_mode": mode,
                "selected_prompt_ids": [
                    score.candidate.prompt_id for score in winners
                ],
                "candidate_count": len(scored),
                "model": model,
            }
        )

    selected.sort(
        key=lambda item: (
            int(item.get("slot_priority") or 100),
            str(item.get("slot") or ""),
            -int(item.get("score") or 0),
            str(item.get("prompt_id") or ""),
        )
    )
    disabled.sort(
        key=lambda item: (
            int(item.get("slot_priority") or 100),
            str(item.get("slot") or ""),
            -int(item.get("score") or 0),
            str(item.get("prompt_id") or ""),
        )
    )
    return {
        "model": model,
        "provider_id": provider_id,
        "preferences": normalized,
        "selected": selected,
        "disabled": disabled,
        "diagnostics": diagnostics,
    }


def _score_payload(
    score: PromptVariantScore,
    *,
    model: str,
    provider_id: str,
) -> dict[str, Any]:
    candidate = score.candidate
    already_active = bool(candidate.metadata.get("already_active"))
    return {
        "prompt_id": candidate.prompt_id,
        "slot": candidate.slot,
        "slot_priority": candidate.slot_priority,
        "tags": list(candidate.tags),
        "priority": candidate.priority,
        "fallback": candidate.fallback,
        "explicit": candidate.explicit,
        "already_active": already_active,
        "selection_mode": candidate.selection_mode,
        "matched_prefer": list(score.matched_prefer),
        "matched_avoid": list(score.matched_avoid),
        "preference_score": score.preference_score,
        "score": score.total_score,
        "positive_match": score.positive_match,
        "source": candidate.source,
        "source_type": candidate.source_type,
        "text": candidate.text,
        "preview": " ".join(candidate.text.split())[:280],
        "model": model,
        "provider_id": provider_id,
        "metadata": dict(candidate.metadata),
    }


def _score_sort_key(score: PromptVariantScore) -> tuple[Any, ...]:
    return (
        -int(score.candidate.explicit),
        -score.total_score,
        -score.preference_score,
        -score.candidate.priority,
        -len(score.matched_prefer),
        len(score.matched_avoid),
        score.candidate.prompt_id.casefold(),
    )


def _slot_selection_mode(
    candidates: Sequence[PromptVariantCandidate],
) -> tuple[str, dict[str, Any] | None]:
    modes = {_normalize_selection_mode(item.selection_mode) for item in candidates}
    if modes and modes.issubset(_ADDITIVE_MODES):
        return "all", None
    if len(modes) > 1:
        return (
            "best_match",
            {
                "severity": "warning",
                "code": "prompt_variant_mixed_selection_modes",
                "modes": sorted(modes),
                "resolved_mode": "best_match",
            },
        )
    return "best_match", None


def _normalize_selection_mode(value: Any) -> str:
    normalized = str(value or "best_match").strip().lower()
    return "all" if normalized in _ADDITIVE_MODES else "best_match"


def _normalize_weighted_tags(
    value: Any,
    *,
    default_weight: int,
) -> dict[str, int]:
    output: dict[str, int] = {}
    if isinstance(value, Mapping):
        items: Iterable[tuple[Any, Any]] = value.items()
    else:
        items = ((tag, default_weight) for tag in _list_value(value))
    for raw_tag, raw_weight in items:
        tag = _normalize_tag(raw_tag)
        if not tag or tag in output:
            continue
        if raw_weight is False or raw_weight is None:
            continue
        weight = (
            default_weight
            if raw_weight is True
            else _positive_bounded_int(raw_weight, default=default_weight)
        )
        if weight <= 0:
            continue
        output[tag] = weight
        if len(output) >= _MAX_TAGS:
            break
    return output


def _normalize_tags(value: Any) -> list[str]:
    output: list[str] = []
    for raw_tag in _list_value(value):
        tag = _normalize_tag(raw_tag)
        if not tag or tag in output:
            continue
        output.append(tag)
        if len(output) >= _MAX_TAGS:
            break
    return output


def _normalize_tag(value: Any) -> str:
    tag = str(value or "").strip().lower()
    return tag if _TAG_PATTERN.fullmatch(tag) else ""


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [
            item.strip()
            for item in value.replace("\n", ",").split(",")
            if item.strip()
        ]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return []


def _bounded_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(-_MAX_WEIGHT, min(_MAX_WEIGHT, parsed))


def _positive_bounded_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(_MAX_WEIGHT, parsed))


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)
