from __future__ import annotations

from typing import Any, Mapping

from .constants import ACTION_IDS, BUILTIN_PRESET_IDS, PRESET_ALIASES
from .lattice import normalize_level
from .models import NormalizedQuestionnaire, PermissionLevel


def normalize_questionnaire(raw: Mapping[str, Any] | None) -> NormalizedQuestionnaire:
    data = dict(raw or {})
    profile_id = _clean_profile_id(data.get("profile_id") or data.get("id") or "default")
    preset_id = _normalize_preset(data.get("preset") or data.get("preset_id") or "balanced_local")
    occupation = _optional_slug(data.get("occupation") or data.get("role"))
    explicit_actions = _normalize_actions(data)
    use_cases = _normalize_use_cases(data.get("use_cases") or data.get("uses"))
    phase_autonomy = _normalize_string_mapping(
        data.get("phase_autonomy") or data.get("workflow_autonomy") or data.get("autonomy_by_phase"),
        default={
            "plan": "allow",
            "implement": "ask",
            "verify": "allow",
            "publish": "ask",
        },
    )
    responsibility_matrix = _normalize_object(
        data.get("responsibility_matrix") or data.get("responsibilities"),
        default={
            "frontend": {"owner": "user", "assistant": "implement_with_review"},
            "backend": {"owner": "user", "assistant": "implement_with_review"},
            "security": {"owner": "user", "assistant": "never_bypass_policy"},
        },
    )
    review_topology = _normalize_object(
        data.get("review_topology") or data.get("review"),
        default={
            "required_for": ["git_push", "external_send", "secrets_access", "computer_control"],
            "reviewers": ["local_user"],
            "mode": "local_review",
        },
    )
    privacy_policy = _normalize_object(
        data.get("privacy_policy") or data.get("privacy"),
        default={"mode": "local_first", "redact_secrets": True, "external_training": False},
    )
    memory_policy = _normalize_object(
        data.get("memory_policy") or data.get("memory"),
        default={"mode": str(data.get("memory_mode") or "explicit"), "retention": "profile_scoped"},
    )
    skill_learning_policy = _normalize_object(
        data.get("skill_learning_policy") or data.get("skill_learning"),
        default={
            "enabled": bool(data.get("skill_learning_enabled", False)),
            "review_required": data.get("skill_learning_review_required", True) is not False,
            "source": "failure_to_verified_success",
        },
    )
    budget_policy = _normalize_object(
        data.get("budget_policy") or data.get("budget"),
        default={"context_tokens": 0, "max_parallel_actions": 1, "spend_limit": 0},
    )
    project_overrides = _normalize_object(
        data.get("project_overrides") or data.get("project_override"),
        default={},
    )
    return NormalizedQuestionnaire(
        profile_id=profile_id,
        preset_id=preset_id,
        occupation=occupation,
        explicit_actions=explicit_actions,
        use_cases=use_cases,
        phase_autonomy=phase_autonomy,
        responsibility_matrix=responsibility_matrix,
        review_topology=review_topology,
        privacy_policy=privacy_policy,
        memory_policy=memory_policy,
        skill_learning_policy=skill_learning_policy,
        budget_policy=budget_policy,
        project_overrides=project_overrides,
        raw=data,
    )


def _normalize_preset(value: Any) -> str:
    candidate = str(value or "").strip().lower().replace(" ", "_")
    candidate = PRESET_ALIASES.get(candidate, candidate)
    if candidate not in BUILTIN_PRESET_IDS:
        raise ValueError(f"unknown operating profile preset: {value!r}")
    return candidate


def _normalize_actions(data: Mapping[str, Any]) -> dict[str, PermissionLevel]:
    raw_actions = data.get("actions")
    actions: dict[str, PermissionLevel] = {}
    if isinstance(raw_actions, Mapping):
        for action_id, level in raw_actions.items():
            if isinstance(action_id, str) and action_id in ACTION_IDS:
                actions[action_id] = normalize_level(level)
    for action_id in ACTION_IDS:
        if action_id in data and action_id not in actions:
            actions[action_id] = normalize_level(data[action_id])
    if "allow_external_send" in data and "external_send" not in actions:
        actions["external_send"] = normalize_level(data["allow_external_send"])
    return actions


def _clean_profile_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("profile_id must not be empty")
    if "/" in candidate or "\\" in candidate or ".." in candidate:
        raise ValueError("profile_id must not contain path separators or traversal")
    return candidate


def _optional_slug(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return candidate or None


def _normalize_use_cases(value: Any) -> dict[str, bool]:
    if isinstance(value, Mapping):
        return {str(key): bool(value[key]) for key in sorted(value, key=str) if str(key)}
    if isinstance(value, list):
        result: dict[str, bool] = {}
        for item in value:
            if isinstance(item, Mapping):
                key = str(item.get("id") or item.get("use_case") or "").strip()
                enabled = item.get("enabled", True) is not False
            else:
                key = str(item or "").strip()
                enabled = True
            if key:
                result[key] = enabled
        return result
    return {"coding": True, "research": True}


def _normalize_string_mapping(value: Any, *, default: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {str(key): str(default[key]) for key in sorted(default, key=str)}
    result = {str(key): str(value[key]) for key in sorted(value, key=str) if str(key)}
    return result or {str(key): str(default[key]) for key in sorted(default, key=str)}


def _normalize_object(value: Any, *, default: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return dict(default)
    return {str(key): value[key] for key in sorted(value, key=str) if str(key)}
