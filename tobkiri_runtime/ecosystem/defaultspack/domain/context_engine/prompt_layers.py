from __future__ import annotations

import hashlib
from typing import Any

from .models import PromptLayer
from .token_estimator import estimate_tokens


def build_system_layers(
    *,
    system_prompt: str | None = None,
    runtime_profile: dict[str, Any] | None = None,
    memory_snapshot: str | None = None,
    user_snapshot: str | None = None,
    project_context: str | None = None,
    tool_index: str | None = None,
    runtime_line: str | None = None,
) -> list[PromptLayer]:
    layers = [
        PromptLayer("base_identity", "You are the defaultspack durable agent runtime.", True),
    ]
    if system_prompt:
        layers.append(PromptLayer("selected_system_prompt", system_prompt, True))
    if runtime_profile:
        layers.append(PromptLayer("runtime_profile", runtime_profile, True))
    if memory_snapshot:
        layers.append(PromptLayer("memory_snapshot", memory_snapshot, True))
    if user_snapshot:
        layers.append(PromptLayer("user_snapshot", user_snapshot, True))
    if project_context:
        layers.append(PromptLayer("project_context", project_context, True))
    if tool_index:
        layers.append(PromptLayer("tool_index", tool_index, True))
    if runtime_line:
        layers.append(PromptLayer("runtime_line", runtime_line, True))
    for layer in layers:
        layer.token_estimate = estimate_tokens(layer.content)
    return layers


def render_system_prompt(layers: list[PromptLayer]) -> str:
    parts = []
    for layer in layers:
        parts.append(f"[{layer.name}]\n{layer.content}")
    return "\n\n".join(parts)


def stable_prompt_hash(layers: list[PromptLayer]) -> str:
    stable_text = render_system_prompt([layer for layer in layers if layer.stable])
    return hashlib.sha256(stable_text.encode("utf-8")).hexdigest()
