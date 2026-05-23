from __future__ import annotations

from domain.ai_client.provider_compiler.base import CompiledProviderRequest
from domain.ai_client.provider_compiler.openai_chat import OpenAIChatCompiler
from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages


class OpenAIResponsesCompiler(OpenAIChatCompiler):
    api_family = "openai_responses"

    def compile_complete(self, planned):
        legacy = ir_to_legacy_standard_messages(planned.ir)
        input_items = []
        for message in legacy:
            input_items.append({"role": message.get("role", "user"), "content": message.get("content", "")})
            if message.get("tool_calls"):
                input_items[-1]["tool_calls"] = message.get("tool_calls")
            if message.get("role") == "tool":
                input_items[-1]["tool_call_id"] = message.get("tool_call_id")
        body = {"model": planned.model, "input": input_items}
        if planned.provider_tools:
            body["tools"] = planned.provider_tools
        for key in ("temperature", "max_output_tokens", "reasoning", "tool_choice", "parallel_tool_calls"):
            if key in planned.params:
                body[key] = planned.params[key]
        return CompiledProviderRequest(
            api_family=self.api_family,
            provider_id="openai",
            model=planned.model,
            path="/responses",
            body=body,
            warnings=[item.to_dict() for item in planned.warnings],
            dropped_features=[item.to_dict() for item in planned.dropped_features],
            trace={"planner": planned.to_dict()},
            legacy_messages=legacy,
            metadata=dict(planned.metadata or {}),
        )
