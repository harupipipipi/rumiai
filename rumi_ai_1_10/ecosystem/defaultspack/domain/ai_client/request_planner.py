from __future__ import annotations

from typing import Any

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.degradation import degrade_request
from domain.chat.ir import RumiChatIR
from domain.prompt.model_variants import apply_model_prompt_variants


def plan_model_request(
    ir: RumiChatIR,
    model: str,
    provider_capabilities: dict[str, Any],
    tools: list[dict[str, Any]] | None,
    params: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> PlannedProviderRequest:
    runtime_context = context if isinstance(context, dict) else {}
    adapted_ir, _ = apply_model_prompt_variants(
        ir,
        model,
        runtime_context,
    )
    return degrade_request(
        adapted_ir,
        model=model,
        provider_capabilities=provider_capabilities,
        tools=list(tools or []),
        params=dict(params or {}),
        context=runtime_context if isinstance(context, dict) else context,
    )
