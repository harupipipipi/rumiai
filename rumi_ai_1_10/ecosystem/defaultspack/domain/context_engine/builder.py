from __future__ import annotations

from typing import Any

from .models import ContextBuildResult
from .prompt_layers import build_system_layers, render_system_prompt, stable_prompt_hash
from .token_estimator import estimate_messages_tokens


class ContextBuilder:
    def build(self, run: dict[str, Any] | None, new_input: dict[str, Any] | None = None) -> ContextBuildResult:
        run = run if isinstance(run, dict) else {}
        new_input = new_input if isinstance(new_input, dict) else {}
        execution = run.get("execution_json") if isinstance(run.get("execution_json"), dict) else {}
        messages = list(execution.get("messages") or [])
        task = new_input.get("task") or run.get("task")
        if task and not messages:
            messages.append({"role": "user", "content": task})

        layers = build_system_layers(
            system_prompt=execution.get("system_prompt") or new_input.get("system_prompt"),
            runtime_profile=run.get("runtime_profile_json") if isinstance(run.get("runtime_profile_json"), dict) else None,
            memory_snapshot=new_input.get("memory_snapshot"),
            user_snapshot=new_input.get("user_snapshot"),
            project_context=new_input.get("project_context"),
            tool_index=new_input.get("tool_index"),
            runtime_line=new_input.get("runtime_line"),
        )
        system_prompt = render_system_prompt(layers)
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + [
                message for message in messages if message.get("role") != "system"
            ]
        token_estimate = estimate_messages_tokens(messages)
        return ContextBuildResult(
            messages=messages,
            system_prompt_hash=stable_prompt_hash(layers),
            token_estimate=token_estimate,
            attached_tools=list(execution.get("tools") or []),
            pinned_context=list(new_input.get("pinned_context") or []),
            ephemeral_context=list(new_input.get("ephemeral_context") or []),
        )
