from __future__ import annotations

from typing import Any


MODEL_CAPABILITY_FIELDS = {
    "model.text": ("supports_text",),
    "model.image_input": ("supports_image_input", "supports_vision"),
    "model.vision": ("supports_image_input", "supports_vision"),
    "model.tool_calling": ("supports_tool_calling",),
    "model.tools": ("supports_tool_calling",),
    "model.thinking": ("supports_thinking",),
    "model.fast": ("supports_fast",),
}


def normalize_capability_tokens(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        values = [str(item).strip() for item in value if str(item or "").strip()]
    else:
        values = []
    output: list[str] = []
    for token in values:
        if token and token not in output:
            output.append(token)
    return output


def model_requirements_from_tokens(tokens: list[str]) -> dict[str, bool]:
    token_set = set(normalize_capability_tokens(tokens))
    return {
        "image_input": bool({"model.image_input", "model.vision"} & token_set),
        "tool_calling": bool({"model.tool_calling", "model.tools"} & token_set),
        "thinking": "model.thinking" in token_set,
        "fast": "model.fast" in token_set,
    }


def missing_model_capabilities(required_tokens: list[str], model_capabilities: dict[str, Any] | None) -> list[str]:
    caps = model_capabilities if isinstance(model_capabilities, dict) else {}
    missing: list[str] = []
    for token in normalize_capability_tokens(required_tokens):
        if not token.startswith("model."):
            continue
        fields = MODEL_CAPABILITY_FIELDS.get(token)
        if fields is None:
            continue
        if token == "model.text":
            continue
        if not any(bool(caps.get(field)) for field in fields):
            missing.append(token)
    return missing
