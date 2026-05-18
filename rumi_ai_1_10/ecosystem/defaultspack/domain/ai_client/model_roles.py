from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


UTILITY_MODEL_ROLES = (
    "tool_selector",
    "vision_ocr",
    "prompt_compactor",
    "context_summarizer",
    "model_router",
    "subagent_default",
    "fast_reply",
)

DEFAULT_UTILITY_MODELS = {role: "" for role in UTILITY_MODEL_ROLES}

DEFAULT_UTILITY_MODEL_POLICY: dict[str, Any] = {
    "allow_auto_select": True,
    "prefer_fast_for_utility": True,
    "min_knowledge_level": {
        "tool_selector": 60,
        "vision_ocr": 75,
        "prompt_compactor": 65,
        "context_summarizer": 65,
        "model_router": 70,
    },
}


def normalize_utility_models(value: Any) -> dict[str, str]:
    models = dict(DEFAULT_UTILITY_MODELS)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if isinstance(value, dict):
        for role in UTILITY_MODEL_ROLES:
            models[role] = str(value.get(role) or "").strip()
    return models


def normalize_utility_model_policy(value: Any) -> dict[str, Any]:
    policy = deepcopy(DEFAULT_UTILITY_MODEL_POLICY)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if isinstance(value, dict):
        policy.update(deepcopy(value))
    policy["allow_auto_select"] = bool(policy.get("allow_auto_select", True))
    policy["prefer_fast_for_utility"] = bool(policy.get("prefer_fast_for_utility", True))
    min_levels = policy.get("min_knowledge_level")
    if not isinstance(min_levels, dict):
        min_levels = {}
    normalized_levels: dict[str, int] = {}
    defaults = DEFAULT_UTILITY_MODEL_POLICY["min_knowledge_level"]
    for role, default_level in defaults.items():
        try:
            normalized_levels[role] = int(min_levels.get(role, default_level))
        except (TypeError, ValueError):
            normalized_levels[role] = int(default_level)
    policy["min_knowledge_level"] = normalized_levels
    return policy
