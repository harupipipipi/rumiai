from __future__ import annotations

import json

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.base import CompiledProviderRequest, ProviderCompiler, standard_response_to_ir
from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages


class BedrockConverseCompiler(ProviderCompiler):
    api_family = "bedrock_converse"

    def compile_complete(self, planned: PlannedProviderRequest):
        legacy = ir_to_legacy_standard_messages(planned.ir)
        messages = []
        system = []
        for message in legacy:
            role = message.get("role", "user")
            if role == "system":
                system.append({"text": str(message.get("content") or "")})
                continue
            messages.append({"role": "assistant" if role == "assistant" else "user", "content": _bedrock_content(message)})
        tool_specs = []
        for tool in planned.provider_tools:
            function_def = tool.get("function") if isinstance(tool.get("function"), dict) else {}
            if function_def:
                tool_specs.append(
                    {
                        "toolSpec": {
                            "name": function_def.get("name", ""),
                            "description": function_def.get("description", ""),
                            "inputSchema": {"json": function_def.get("parameters", {"type": "object"})},
                        }
                    }
                )
        body = {"modelId": planned.model, "messages": messages}
        if system:
            body["system"] = system
        if tool_specs:
            body["toolConfig"] = {"tools": tool_specs}
            if planned.params.get("tool_choice"):
                body["toolConfig"]["toolChoice"] = {"auto": {}} if planned.params.get("tool_choice") == "auto" else planned.params.get("tool_choice")
        inference = {}
        for source, target in (("temperature", "temperature"), ("max_tokens", "maxTokens"), ("top_p", "topP")):
            if source in planned.params:
                inference[target] = planned.params[source]
        if inference:
            body["inferenceConfig"] = inference
        return CompiledProviderRequest(
            api_family=self.api_family,
            provider_id=str(planned.provider_capabilities.get("provider_id") or "bedrock"),
            model=planned.model,
            path="/model/{}/converse".format(planned.model),
            body=body,
            warnings=[item.to_dict() for item in planned.warnings],
            dropped_features=[item.to_dict() for item in planned.dropped_features],
            trace={"planner": planned.to_dict()},
            legacy_messages=legacy,
            metadata=dict(planned.metadata or {}),
        )

    def parse_response(self, raw, compiled):
        content = []
        output = raw.get("output") if isinstance(raw, dict) else {}
        message = output.get("message") if isinstance(output, dict) else {}
        for part in message.get("content", []) if isinstance(message, dict) else []:
            if not isinstance(part, dict):
                continue
            if "text" in part:
                content.append({"type": "text", "text": part.get("text", "")})
            elif "toolUse" in part:
                tool = part["toolUse"]
                content.append({"type": "tool_use", "id": tool.get("toolUseId", ""), "name": tool.get("name", ""), "input": tool.get("input", {})})
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        return standard_response_to_ir(
            {
                "content": content,
                "finish_reason": raw.get("stopReason") or "stop",
                "usage": {
                    "input_tokens": usage.get("inputTokens", 0),
                    "output_tokens": usage.get("outputTokens", 0),
                    "total_tokens": usage.get("totalTokens", usage.get("inputTokens", 0) + usage.get("outputTokens", 0)),
                },
                "metadata": {"api_family": compiled.api_family},
            }
        )


def _bedrock_content(message):
    if message.get("role") == "tool":
        return [{"toolResult": {"toolUseId": message.get("tool_call_id", ""), "content": [{"text": str(message.get("content") or "")}]}}]
    parts = []
    content = message.get("content", "")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append({"text": part.get("text", "")})
            elif isinstance(part, str):
                parts.append({"text": part})
    elif content:
        parts.append({"text": str(content)})
    for tool_call in message.get("tool_calls", []) or []:
        function_def = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        args = function_def.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"value": args}
        parts.append({"toolUse": {"toolUseId": tool_call.get("id", ""), "name": function_def.get("name", ""), "input": args}})
    return parts or [{"text": ""}]
