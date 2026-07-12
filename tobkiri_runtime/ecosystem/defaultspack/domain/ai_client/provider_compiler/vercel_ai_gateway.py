from __future__ import annotations

from typing import Any

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler


class VercelAIGatewayCompiler(OpenAICompatibleCompiler):
    api_family = "vercel_ai_gateway"

    _BODY_PARAMS = {
        "models",
        "providerOptions",
        "reasoning",
        "service_tier",
        "web_search_options",
    }

    def _translate_params(self, planned: PlannedProviderRequest) -> dict[str, Any]:
        params = super()._translate_params(planned)
        extra_body = dict(params.get("extra_body", {})) if isinstance(params.get("extra_body"), dict) else {}

        reasoning_effort = str(params.pop("reasoning_effort", "") or "").strip().lower()
        if reasoning_effort:
            if reasoning_effort == "none":
                extra_body.setdefault("reasoning", {"effort": "none"})
            else:
                extra_body.setdefault("reasoning", {"effort": reasoning_effort})

        for key in self._BODY_PARAMS:
            if key in params:
                extra_body[key] = params.pop(key)

        if extra_body:
            params["extra_body"] = extra_body
        return params
