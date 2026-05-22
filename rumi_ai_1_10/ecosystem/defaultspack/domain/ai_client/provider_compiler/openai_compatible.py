from __future__ import annotations

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler


class OpenAICompatibleCompiler(OpenAIChatCompiler):
    api_family = "openai_compatible"

    def _translate_params(self, planned: PlannedProviderRequest) -> dict:
        params = super()._translate_params(planned)
        quirks = planned.provider_capabilities.get("quirks") if isinstance(planned.provider_capabilities.get("quirks"), dict) else {}
        if quirks.get("max_tokens_name") == "max_completion_tokens" and "max_tokens" in params:
            params.setdefault("max_completion_tokens", params.pop("max_tokens"))
        if str(params.get("reasoning_effort") or params.get("thinking_level") or "").lower() == "none":
            params.pop("reasoning_effort", None)
            if quirks.get("drop_reasoning_when_none", True):
                params.pop("thinking_level", None)
        for key in quirks.get("unsupported_params") or []:
            params.pop(str(key), None)
        return params
