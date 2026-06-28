from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .constants import ACTION_IDS, PROFILE_SPEC_VERSION


class PermissionLevel(str, Enum):
    DENY = "deny"
    ASK = "ask"
    ALLOW = "allow"


LEVEL_RANK: dict[PermissionLevel, int] = {
    PermissionLevel.DENY: 0,
    PermissionLevel.ASK: 1,
    PermissionLevel.ALLOW: 2,
}


@dataclass(frozen=True)
class ActionPolicy:
    levels: dict[str, PermissionLevel] = field(default_factory=dict)

    def level_for(self, action_id: str) -> PermissionLevel:
        return self.levels.get(action_id, PermissionLevel.DENY)

    def to_dict(self) -> dict[str, str]:
        ordered: dict[str, str] = {}
        for action_id in ACTION_IDS:
            ordered[action_id] = self.level_for(action_id).value
        for action_id in sorted(set(self.levels) - set(ACTION_IDS)):
            ordered[action_id] = self.level_for(action_id).value
        return ordered

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "ActionPolicy":
        from .lattice import normalize_level

        result: dict[str, PermissionLevel] = {}
        for action_id in ACTION_IDS:
            result[action_id] = PermissionLevel.DENY
        if raw:
            for action_id, value in raw.items():
                if isinstance(action_id, str) and action_id:
                    result[action_id] = normalize_level(value)
        return cls(result)


@dataclass(frozen=True)
class NormalizedQuestionnaire:
    profile_id: str
    preset_id: str
    occupation: str | None
    explicit_actions: dict[str, PermissionLevel]
    use_cases: dict[str, bool] = field(default_factory=dict)
    phase_autonomy: dict[str, str] = field(default_factory=dict)
    responsibility_matrix: dict[str, Any] = field(default_factory=dict)
    review_topology: dict[str, Any] = field(default_factory=dict)
    privacy_policy: dict[str, Any] = field(default_factory=dict)
    memory_policy: dict[str, Any] = field(default_factory=dict)
    skill_learning_policy: dict[str, Any] = field(default_factory=dict)
    budget_policy: dict[str, Any] = field(default_factory=dict)
    project_overrides: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "preset_id": self.preset_id,
            "occupation": self.occupation,
            "explicit_actions": {
                key: self.explicit_actions[key].value for key in sorted(self.explicit_actions)
            },
            "use_cases": _stable_value(self.use_cases),
            "phase_autonomy": _stable_value(self.phase_autonomy),
            "responsibility_matrix": _stable_value(self.responsibility_matrix),
            "review_topology": _stable_value(self.review_topology),
            "privacy_policy": _stable_value(self.privacy_policy),
            "memory_policy": _stable_value(self.memory_policy),
            "skill_learning_policy": _stable_value(self.skill_learning_policy),
            "budget_policy": _stable_value(self.budget_policy),
            "project_overrides": _stable_value(self.project_overrides),
        }


@dataclass(frozen=True)
class PackRecommendation:
    pack_id: str
    action_overrides: ActionPolicy = field(default_factory=ActionPolicy)
    recommended_preset: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "action_overrides": self.action_overrides.to_dict(),
            "recommended_preset": self.recommended_preset,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OperatingProfile:
    profile_id: str
    preset_id: str
    policy: ActionPolicy
    answers: dict[str, Any] = field(default_factory=dict)
    recommended_packs: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    use_cases: dict[str, bool] = field(default_factory=dict)
    phase_autonomy: dict[str, str] = field(default_factory=dict)
    responsibility_matrix: dict[str, Any] = field(default_factory=dict)
    review_topology: dict[str, Any] = field(default_factory=dict)
    privacy_policy: dict[str, Any] = field(default_factory=dict)
    memory_policy: dict[str, Any] = field(default_factory=dict)
    skill_learning_policy: dict[str, Any] = field(default_factory=dict)
    budget_policy: dict[str, Any] = field(default_factory=dict)
    project_overrides: dict[str, Any] = field(default_factory=dict)
    version: str = PROFILE_SPEC_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile_id": self.profile_id,
            "preset_id": self.preset_id,
            "policy": self.policy.to_dict(),
            "side_effect_policy": self.policy.to_dict(),
            "answers": _stable_value(self.answers),
            "recommended_packs": sorted(self.recommended_packs),
            "provenance": [_stable_value(item) for item in self.provenance],
            "use_cases": _stable_value(self.use_cases),
            "uses": [
                {"id": key, "enabled": self.use_cases[key]}
                for key in sorted(self.use_cases)
            ],
            "phase_autonomy": _stable_value(self.phase_autonomy),
            "responsibility_matrix": _stable_value(self.responsibility_matrix),
            "review_topology": _stable_value(self.review_topology),
            "review_policy": _stable_value(self.review_topology),
            "privacy_policy": _stable_value(self.privacy_policy),
            "memory_policy": _stable_value(self.memory_policy),
            "skill_learning_policy": _stable_value(self.skill_learning_policy),
            "budget_policy": _stable_value(self.budget_policy),
            "project_overrides": _stable_value(self.project_overrides),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OperatingProfile":
        policy_raw = raw.get("policy") if isinstance(raw.get("policy"), Mapping) else raw.get("side_effect_policy")
        if not isinstance(policy_raw, Mapping):
            policy_raw = {}
        return cls(
            profile_id=str(raw.get("profile_id") or "default"),
            preset_id=str(raw.get("preset_id") or "discussion_only"),
            policy=ActionPolicy.from_mapping(policy_raw),
            answers=dict(raw.get("answers") or {}),
            recommended_packs=[str(item) for item in raw.get("recommended_packs") or []],
            provenance=[dict(item) for item in raw.get("provenance") or [] if isinstance(item, Mapping)],
            use_cases=_bool_mapping(raw.get("use_cases")),
            phase_autonomy=_str_mapping(raw.get("phase_autonomy")),
            responsibility_matrix=dict(raw.get("responsibility_matrix") or {}),
            review_topology=dict(raw.get("review_topology") or raw.get("review_policy") or {}),
            privacy_policy=dict(raw.get("privacy_policy") or {}),
            memory_policy=dict(raw.get("memory_policy") or {}),
            skill_learning_policy=dict(raw.get("skill_learning_policy") or {}),
            budget_policy=dict(raw.get("budget_policy") or {}),
            project_overrides=dict(raw.get("project_overrides") or {}),
            version=str(raw.get("version") or PROFILE_SPEC_VERSION),
        )


def _stable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _bool_mapping(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): bool(value[key]) for key in sorted(value, key=str) if str(key)}


def _str_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(value[key]) for key in sorted(value, key=str) if str(key)}
