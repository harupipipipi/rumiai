from __future__ import annotations

import json

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.base import CompiledProviderRequest, ProviderCompiler, standard_response_to_ir
from domain.ai_client.providers.google_provider import GoogleProvider
from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages


class GoogleNativeCompiler(ProviderCompiler):
    api_family = "google_native"

    def compile_complete(self, planned: PlannedProviderRequest):
        name_map, reverse_name_map = GoogleProvider._tool_name_maps(planned.provider_tools)
        messages = ir_to_legacy_standard_messages(planned.ir)
        params = GoogleProvider._translate_params(dict(planned.params or {}), planned.model)
        body = GoogleProvider()._native_body(planned.model, messages, planned.provider_tools, params, name_map)
        return CompiledProviderRequest(
            api_family=self.api_family,
            provider_id="google",
            model=planned.model,
            path=f"/v1beta/models/{planned.model}:generateContent",
            body=body,
            warnings=[item.to_dict() for item in planned.warnings],
            dropped_features=[item.to_dict() for item in planned.dropped_features],
            trace={"planner": planned.to_dict()},
            legacy_messages=messages,
            metadata={**dict(planned.metadata or {}), "tool_name_map": name_map, "reverse_tool_name_map": reverse_name_map},
        )

    def compile_stream(self, planned: PlannedProviderRequest):
        compiled = self.compile_complete(planned)
        compiled.path = f"/v1beta/models/{planned.model}:streamGenerateContent"
        return compiled

    def parse_response(self, raw, compiled):
        provider = GoogleProvider()
        text, thought, finish_reason, tool_uses = provider._native_extract_parts(raw, compiled.metadata.get("reverse_tool_name_map"))
        response = {
            "content": [{"type": "text", "text": text}] + tool_uses,
            "finish_reason": finish_reason,
            "usage": provider._native_usage(raw),
            "metadata": {},
        }
        if thought:
            response["metadata"]["thinking"] = {"state": "completed", "transcript": thought, "source": "google_native_thought"}
        return standard_response_to_ir(response)

    def parse_stream_chunk(self, raw, compiled):
        parsed = self.parse_response(raw, compiled)
        events = []
        text = "".join(block.text for block in parsed.content if block.type == "text")
        if text:
            from domain.chat.ir import RumiStreamEventIR

            events.append(RumiStreamEventIR(type="content_delta", delta={"type": "text", "text": text}))
        for block in parsed.content:
            if block.type == "tool_call" and block.tool_call is not None:
                from domain.chat.ir import RumiStreamEventIR

                events.append(RumiStreamEventIR(type="tool_call_start", metadata={"id": block.tool_call.id, "name": block.tool_call.name}))
                events.append(
                    RumiStreamEventIR(
                        type="tool_call_delta",
                        metadata={"id": block.tool_call.id, "name": block.tool_call.name, "arguments_chunk": json.dumps(block.tool_call.arguments, ensure_ascii=False)},
                    )
                )
                events.append(RumiStreamEventIR(type="tool_call_end", metadata={"id": block.tool_call.id, "name": block.tool_call.name}))
        return events
