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
    return NormalizedQuestionnaire(
        profile_id=profile_id,
        preset_id=preset_id,
        occupation=occupation,
        explicit_actions=explicit_actions,
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
