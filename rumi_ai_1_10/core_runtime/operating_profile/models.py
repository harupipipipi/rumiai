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
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "preset_id": self.preset_id,
            "occupation": self.occupation,
            "explicit_actions": {
                key: self.explicit_actions[key].value for key in sorted(self.explicit_actions)
            },
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
    version: str = PROFILE_SPEC_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile_id": self.profile_id,
            "preset_id": self.preset_id,
            "policy": self.policy.to_dict(),
            "answers": _stable_value(self.answers),
            "recommended_packs": sorted(self.recommended_packs),
            "provenance": [_stable_value(item) for item in self.provenance],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OperatingProfile":
        policy_raw = raw.get("policy") if isinstance(raw.get("policy"), Mapping) else {}
        return cls(
            profile_id=str(raw.get("profile_id") or "default"),
            preset_id=str(raw.get("preset_id") or "discussion_only"),
            policy=ActionPolicy.from_mapping(policy_raw),
            answers=dict(raw.get("answers") or {}),
            recommended_packs=[str(item) for item in raw.get("recommended_packs") or []],
            provenance=[dict(item) for item in raw.get("provenance") or [] if isinstance(item, Mapping)],
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
