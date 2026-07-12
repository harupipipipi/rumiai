from __future__ import annotations

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler


class OpenAICompatibleCompiler(OpenAIChatCompiler):
    api_family = "openai_compatible"
    _OPENROUTER_BODY_PARAMS = {
        "reasoning",
        "include_reasoning",
        "provider",
        "models",
        "web_search_options",
        "structured_outputs",
    }

    def compile_complete(self, planned: PlannedProviderRequest):
        compiled = super().compile_complete(planned)
        quirks = planned.provider_capabilities.get("quirks") if isinstance(planned.provider_capabilities.get("quirks"), dict) else {}
        if quirks.get("omit_tool_message_name"):
            for message in compiled.body.get("messages") or []:
                if isinstance(message, dict) and message.get("role") == "tool":
                    message.pop("name", None)
        return compiled

    def _translate_params(self, planned: PlannedProviderRequest) -> dict:
        params = super()._translate_params(planned)
        quirks = planned.provider_capabilities.get("quirks") if isinstance(planned.provider_capabilities.get("quirks"), dict) else {}
        provider_id = str(planned.provider_capabilities.get("provider_id") or "").strip()
        if quirks.get("max_tokens_name") == "max_completion_tokens" and "max_tokens" in params:
            params.setdefault("max_completion_tokens", params.pop("max_tokens"))
        if str(params.get("reasoning_effort") or params.get("thinking_level") or "").lower() == "none":
            params.pop("reasoning_effort", None)
            if quirks.get("drop_reasoning_when_none", True):
                params.pop("thinking_level", None)
        if provider_id == "openrouter":
            extra_body = dict(params.get("extra_body", {})) if isinstance(params.get("extra_body"), dict) else {}
            for key in self._OPENROUTER_BODY_PARAMS:
                if key in params:
                    extra_body[key] = params[key]
            if extra_body:
                params["extra_body"] = extra_body
        for key in quirks.get("unsupported_params") or []:
            params.pop(str(key), None)
        return params
