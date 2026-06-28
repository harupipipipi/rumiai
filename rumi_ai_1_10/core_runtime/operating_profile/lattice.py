from __future__ import annotations

from typing import Any, Mapping

from .constants import ACTION_IDS, LEVEL_ALIASES
from .models import ActionPolicy, LEVEL_RANK, PermissionLevel


def normalize_level(value: Any) -> PermissionLevel:
    if isinstance(value, PermissionLevel):
        return value
    if isinstance(value, bool):
        return PermissionLevel.ALLOW if value else PermissionLevel.DENY
    normalized = str(value or "").strip().lower().replace("-", "_")
    normalized = LEVEL_ALIASES.get(normalized, normalized)
    try:
        return PermissionLevel(normalized)
    except ValueError as exc:
        raise ValueError(f"unsupported permission level: {value!r}") from exc


def meet_level(left: Any, right: Any) -> PermissionLevel:
    left_level = normalize_level(left)
    right_level = normalize_level(right)
    return left_level if LEVEL_RANK[left_level] <= LEVEL_RANK[right_level] else right_level


def meet_policy(left: ActionPolicy | Mapping[str, Any], right: ActionPolicy | Mapping[str, Any]) -> ActionPolicy:
    left_policy = left if isinstance(left, ActionPolicy) else ActionPolicy.from_mapping(left)
    right_policy = right if isinstance(right, ActionPolicy) else ActionPolicy.from_mapping(right)
    action_ids = set(ACTION_IDS) | set(left_policy.levels) | set(right_policy.levels)
    return ActionPolicy(
        {action_id: meet_level(left_policy.level_for(action_id), right_policy.level_for(action_id)) for action_id in action_ids}
    )


def policy_within(child: ActionPolicy | Mapping[str, Any], parent: ActionPolicy | Mapping[str, Any]) -> bool:
    child_policy = child if isinstance(child, ActionPolicy) else ActionPolicy.from_mapping(child)
    parent_policy = parent if isinstance(parent, ActionPolicy) else ActionPolicy.from_mapping(parent)
    action_ids = set(ACTION_IDS) | set(child_policy.levels) | set(parent_policy.levels)
    return all(
        LEVEL_RANK[child_policy.level_for(action_id)] <= LEVEL_RANK[parent_policy.level_for(action_id)]
        for action_id in action_ids
    )
