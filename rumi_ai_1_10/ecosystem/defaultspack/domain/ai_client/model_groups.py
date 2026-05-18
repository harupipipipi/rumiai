from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


DEFAULT_MODEL_GROUPS: dict[str, dict[str, Any]] = {
    "default": {
        "label": "標準",
        "routing_policy": "balanced",
        "allowed_models": [],
    },
    "fast": {
        "label": "高速",
        "routing_policy": "prefer_fast",
        "min_speed_tier": "fast",
        "max_knowledge_level": 85,
        "allowed_models": [],
    },
    "deep": {
        "label": "深く考える",
        "routing_policy": "prefer_thinking",
        "require_thinking": True,
        "min_knowledge_level": 85,
        "allowed_models": [],
    },
    "vision": {
        "label": "画像対応",
        "routing_policy": "prefer_vision",
        "require_vision": True,
        "allowed_models": [],
    },
    "cheap": {
        "label": "節約",
        "routing_policy": "prefer_low_cost",
        "allowed_models": [],
    },
    "local": {
        "label": "ローカル",
        "routing_policy": "prefer_local",
        "allowed_models": [],
    },
    "custom": {
        "label": "カスタム",
        "routing_policy": "custom",
        "allowed_models": [],
    },
}


def default_model_groups() -> dict[str, dict[str, Any]]:
    return deepcopy(DEFAULT_MODEL_GROUPS)


def normalize_model_groups(value: Any) -> dict[str, dict[str, Any]]:
    groups = default_model_groups()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        return groups
    for group_id, raw_group in value.items():
        if not isinstance(raw_group, dict):
            continue
        normalized_id = str(group_id or "").strip() or "custom"
        base = groups.get(normalized_id, {})
        group = {**base, **deepcopy(raw_group)}
        allowed = group.get("allowed_models")
        if isinstance(allowed, str):
            allowed = [line.strip() for line in allowed.splitlines() if line.strip()]
        group["allowed_models"] = [str(item).strip() for item in allowed] if isinstance(allowed, list) else []
        group["label"] = str(group.get("label") or normalized_id)
        group["routing_policy"] = str(group.get("routing_policy") or "balanced")
        groups[normalized_id] = group
    return groups


def group_label(group_id: str, groups: dict[str, dict[str, Any]] | None = None) -> str:
    values = groups if isinstance(groups, dict) else default_model_groups()
    group = values.get(str(group_id or "default"), {})
    return str(group.get("label") or group_id or "default")
