from __future__ import annotations


HUMAN_OPERATOR_PROVIDER_ID = "human-operator"
HUMAN_OPERATOR_MODEL_ID = "command-canvas"
HUMAN_OPERATOR_MODEL = f"{HUMAN_OPERATOR_PROVIDER_ID}/{HUMAN_OPERATOR_MODEL_ID}"
HUMAN_OPERATOR_TOOL_NAME = "human_operator_canvas_open"
HUMAN_OPERATOR_SESSION_DIRNAME = "human_operator"


def is_human_operator_model(model: str | None) -> bool:
    normalized = str(model or "").strip().lower()
    return normalized == HUMAN_OPERATOR_MODEL or normalized.startswith(HUMAN_OPERATOR_PROVIDER_ID + "/")
