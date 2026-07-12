from __future__ import annotations

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.base import standard_response_to_ir
from domain.ai_client.provider_compiler.openai_compatible import OpenAICompatibleCompiler
from domain.ai_client.providers.google_provider import GoogleProvider
from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages


class GoogleOpenAICompiler(OpenAICompatibleCompiler):
    api_family = "google_openai"

    def compile_complete(self, planned: PlannedProviderRequest):
        params = GoogleProvider._translate_params(dict(planned.params or {}), planned.model)
        name_map, reverse_name_map = GoogleProvider._tool_name_maps(planned.provider_tools)
        messages = ir_to_legacy_standard_messages(planned.ir)
        provider = GoogleProvider()
        body = {"model": planned.model, "messages": provider._build_request_with_tool_name_map(messages, name_map)}
        sanitized_tools = GoogleProvider._sanitize_tools(planned.provider_tools, name_map)
        if sanitized_tools:
            body["tools"] = sanitized_tools
        GoogleProvider._copy_chat_params(body, params)
        compiled = super().compile_complete(planned)
        compiled.api_family = self.api_family
        compiled.provider_id = "google"
        compiled.body = body
        compiled.legacy_messages = messages
        compiled.metadata = {**compiled.metadata, "tool_name_map": name_map, "reverse_tool_name_map": reverse_name_map}
        return compiled

    def parse_response(self, raw, compiled):
        provider = GoogleProvider()
        return standard_response_to_ir(provider._parse_response_with_tool_name_map(raw, compiled.metadata.get("reverse_tool_name_map")))
