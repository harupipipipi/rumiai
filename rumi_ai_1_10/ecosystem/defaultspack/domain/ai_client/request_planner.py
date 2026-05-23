from __future__ import annotations

from typing import Any

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.degradation import degrade_request
from domain.chat.ir import RumiChatIR


def plan_model_request(
    ir: RumiChatIR,
    model: str,
    provider_capabilities: dict[str, Any],
    tools: list[dict[str, Any]] | None,
    params: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> PlannedProviderRequest:
    return degrade_request(
        ir,
        model=model,
        provider_capabilities=provider_capabilities,
        tools=list(tools or []),
        params=dict(params or {}),
        context=context,
    )
