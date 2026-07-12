from __future__ import annotations

from copy import deepcopy
from typing import Any


SUBAGENT_ROLES: dict[str, dict[str, Any]] = {
    "vision_ocr": {
        "model_role": "vision_ocr",
        "allowed_modalities": ["text", "image"],
        "output_schema": "image_understanding",
        "max_tokens": 1200,
    },
    "tool_selector": {
        "model_role": "tool_selector",
        "allowed_modalities": ["text"],
        "output_schema": "tool_recommendation",
        "max_tokens": 800,
    },
    "prompt_compactor": {
        "model_role": "prompt_compactor",
        "allowed_modalities": ["text"],
        "output_schema": "compact_prompt",
        "max_tokens": 1500,
    },
    "context_summarizer": {
        "model_role": "context_summarizer",
        "allowed_modalities": ["text"],
        "output_schema": "conversation_summary",
        "max_tokens": 1200,
    },
    "model_router": {
        "model_role": "model_router",
        "allowed_modalities": ["text"],
        "output_schema": "model_routing_decision",
        "max_tokens": 800,
    },
}


def get_subagent_role(role_id: str) -> dict[str, Any] | None:
    role = SUBAGENT_ROLES.get(str(role_id or "").strip())
    return deepcopy(role) if role is not None else None


def list_subagent_roles() -> dict[str, dict[str, Any]]:
    return deepcopy(SUBAGENT_ROLES)
