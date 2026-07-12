from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeCapabilitySnapshot:
    input_traits: list[str] = field(default_factory=list)
    model_capabilities: list[str] = field(default_factory=list)
    runtime_capabilities: list[str] = field(default_factory=list)
    policy_capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_traits": list(self.input_traits),
            "model_capabilities": list(self.model_capabilities),
            "runtime_capabilities": list(self.runtime_capabilities),
            "policy_capabilities": list(self.policy_capabilities),
            "tags": list(self.tags),
        }


def build_runtime_capability_snapshot(
    *,
    user_text: str = "",
    modalities: dict[str, Any] | None = None,
    model_capabilities: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> RuntimeCapabilitySnapshot:
    modalities = modalities if isinstance(modalities, dict) else {}
    model_capabilities = model_capabilities if isinstance(model_capabilities, dict) else {}
    context = context if isinstance(context, dict) else {}
    policy = policy if isinstance(policy, dict) else {}

    input_traits = ["input.text"]
    if bool(modalities.get("has_images")):
        input_traits.append("input.image")
    if bool(modalities.get("has_files")):
        input_traits.append("input.file")
    if not str(user_text or "").strip() and "input.text" in input_traits:
        input_traits.remove("input.text")

    model_tokens = ["model.text"]
    if bool(model_capabilities.get("supports_image_input") or model_capabilities.get("supports_vision")):
        model_tokens.append("model.image_input")
    if bool(model_capabilities.get("supports_tool_calling")):
        model_tokens.append("model.tool_calling")
    if bool(model_capabilities.get("supports_thinking")):
        model_tokens.append("model.thinking")
    if bool(model_capabilities.get("supports_fast")):
        model_tokens.append("model.fast")

    runtime_tokens: list[str] = []
    runtime_profile = context.get("runtime_profile") if isinstance(context.get("runtime_profile"), dict) else {}
    if runtime_profile:
        runtime_tokens.append("runtime.profile")
    capability_graph = context.get("capability_graph") if isinstance(context.get("capability_graph"), dict) else {}
    connected_tools = capability_graph.get("connected_tools") if isinstance(capability_graph.get("connected_tools"), list) else []
    if connected_tools:
        runtime_tokens.append("runtime.connected_tools")
    if bool(context.get("user_requested_computer_use")):
        runtime_tokens.append("runtime.user_requested_computer_use")
    if bool(context.get("workspace_root") or context.get("conversation_workspace_dir")):
        runtime_tokens.append("runtime.workspace")

    policy_tokens: list[str] = []
    if policy.get("allow_shell") is not False:
        policy_tokens.append("policy.allow_shell")
    if policy.get("allow_file_write") is not False:
        policy_tokens.append("policy.allow_file_write")
    if policy.get("write_actions_require_approval") is True:
        policy_tokens.append("policy.requires_approval")
    if bool(policy.get("yolo_mode")):
        policy_tokens.append("policy.yolo_mode")

    tags = _dedupe(input_traits + model_tokens + runtime_tokens + policy_tokens)
    return RuntimeCapabilitySnapshot(
        input_traits=_dedupe(input_traits),
        model_capabilities=_dedupe(model_tokens),
        runtime_capabilities=_dedupe(runtime_tokens),
        policy_capabilities=_dedupe(policy_tokens),
        tags=tags,
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
