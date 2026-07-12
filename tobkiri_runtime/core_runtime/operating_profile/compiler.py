from __future__ import annotations

from typing import Any, Mapping

from .constants import ACTION_IDS, BUILTIN_PRESET_POLICIES, OCCUPATION_CEILINGS
from .lattice import meet_policy
from .models import ActionPolicy, OperatingProfile
from .pack_contract import validate_pack_recommendations
from .provenance import provenance_event
from .questionnaire import normalize_questionnaire


def compile_operating_profile(
    answers: Mapping[str, Any] | None,
    *,
    pack_recommendations: Any = None,
    system_ceiling: ActionPolicy | Mapping[str, Any] | None = None,
    parent_profile: OperatingProfile | Mapping[str, Any] | None = None,
) -> OperatingProfile:
    normalized = normalize_questionnaire(answers)
    policy = _preset_policy(normalized.preset_id)
    provenance: list[dict[str, Any]] = [
        provenance_event("questionnaire", normalized.to_dict()),
        provenance_event("preset", {"preset_id": normalized.preset_id}),
    ]

    if normalized.explicit_actions:
        policy = _apply_selected(policy, normalized.explicit_actions)
        provenance.append(
            provenance_event(
                "explicit_answers",
                {"actions": {key: normalized.explicit_actions[key].value for key in sorted(normalized.explicit_actions)}},
            )
        )

    if normalized.occupation:
        ceiling = OCCUPATION_CEILINGS.get(normalized.occupation)
        if ceiling:
            policy = meet_policy(policy, _partial_ceiling(ceiling))
        provenance.append(provenance_event("occupation", {"occupation": normalized.occupation}))

    validation = validate_pack_recommendations(pack_recommendations)
    recommended_pack_ids: list[str] = []
    for recommendation in validation.recommendations:
        recommended_pack_ids.append(recommendation.pack_id)
        if recommendation.recommended_preset:
            policy = meet_policy(policy, _preset_policy(recommendation.recommended_preset))
        policy = meet_policy(policy, recommendation.action_overrides)
    if validation.recommendations or validation.diagnostics:
        provenance.append(
            provenance_event(
                "pack_contract",
                {
                    "recommended_packs": sorted(recommended_pack_ids),
                    "diagnostics": validation.diagnostics,
                },
            )
        )

    if system_ceiling is not None:
        policy = meet_policy(policy, system_ceiling if isinstance(system_ceiling, ActionPolicy) else _partial_ceiling(system_ceiling))
        provenance.append(provenance_event("system_ceiling", {}))

    parent = _coerce_profile(parent_profile)
    if parent is not None:
        policy = meet_policy(policy, parent.policy)
        provenance.append(provenance_event("parent_profile", {"profile_id": parent.profile_id}))

    return OperatingProfile(
        profile_id=normalized.profile_id,
        preset_id=normalized.preset_id,
        policy=policy,
        answers=normalized.to_dict(),
        recommended_packs=recommended_pack_ids,
        provenance=provenance,
        use_cases=normalized.use_cases,
        phase_autonomy=normalized.phase_autonomy,
        responsibility_matrix=normalized.responsibility_matrix,
        review_topology=normalized.review_topology,
        privacy_policy=normalized.privacy_policy,
        memory_policy=normalized.memory_policy,
        skill_learning_policy=normalized.skill_learning_policy,
        budget_policy=normalized.budget_policy,
        project_overrides=normalized.project_overrides,
    )


def get_builtin_operating_profiles() -> dict[str, OperatingProfile]:
    return {
        preset_id: OperatingProfile(
            profile_id=preset_id,
            preset_id=preset_id,
            policy=_preset_policy(preset_id),
            answers={"preset_id": preset_id},
            provenance=[provenance_event("builtin_preset", {"preset_id": preset_id})],
        )
        for preset_id in sorted(BUILTIN_PRESET_POLICIES)
    }


def _preset_policy(preset_id: str) -> ActionPolicy:
    return ActionPolicy.from_mapping(BUILTIN_PRESET_POLICIES[preset_id])


def _partial_ceiling(raw: Mapping[str, Any]) -> ActionPolicy:
    levels = {action_id: "allow" for action_id in ACTION_IDS}
    levels.update(dict(raw))
    return ActionPolicy.from_mapping(levels)


def _apply_selected(policy: ActionPolicy, selected: Mapping[str, Any]) -> ActionPolicy:
    levels = policy.to_dict()
    levels.update(dict(selected))
    return ActionPolicy.from_mapping(levels)


def _coerce_profile(raw: OperatingProfile | Mapping[str, Any] | None) -> OperatingProfile | None:
    if raw is None:
        return None
    if isinstance(raw, OperatingProfile):
        return raw
    return OperatingProfile.from_dict(raw)
