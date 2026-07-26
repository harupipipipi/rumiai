from __future__ import annotations

import json

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.provider_compiler.base import CompiledProviderRequest, ProviderCompiler, standard_response_to_ir
from domain.chat.ir import RumiStreamEventIR
from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages


class AnthropicMessagesCompiler(ProviderCompiler):
    api_family = "anthropic_messages"

    def compile_complete(self, planned: PlannedProviderRequest):
        legacy = ir_to_legacy_standard_messages(planned.ir)
        messages = []
        system_parts = []
        for message in legacy:
            role = message.get("role", "user")
            if role == "system":
                system_parts.append(str(message.get("content") or ""))
                continue
            content = _anthropic_content(message)
            messages.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        tools = []
        for tool in planned.provider_tools:
            function_def = tool.get("function") if isinstance(tool.get("function"), dict) else {}
            if function_def:
                tools.append(
                    {
                        "name": function_def.get("name", ""),
                        "description": function_def.get("description", ""),
                        "input_schema": function_def.get("parameters", {"type": "object", "properties": {}}),
                    }
                )
        body = {"model": planned.model, "messages": messages, "max_tokens": planned.params.get("max_tokens", planned.params.get("max_completion_tokens", 1024))}
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if tools:
            body["tools"] = tools
        return CompiledProviderRequest(
            api_family=self.api_family,
            provider_id=str(planned.provider_capabilities.get("provider_id") or "anthropic"),
            model=planned.model,
            path="/v1/messages",
            body=body,
            warnings=[item.to_dict() for item in planned.warnings],
            dropped_features=[item.to_dict() for item in planned.dropped_features],
            trace={"planner": planned.to_dict()},
            legacy_messages=legacy,
            metadata={**dict(planned.metadata or {}), "tool_runtime": "client"},
        )

    def parse_response(self, raw, compiled):
        blocks = []
        for part in raw.get("content", []) if isinstance(raw, dict) else []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                blocks.append({"type": "text", "text": part.get("text", "")})
            elif part.get("type") == "tool_use":
                blocks.append({"type": "tool_use", "id": part.get("id", ""), "name": part.get("name", ""), "input": part.get("input", {})})
        return standard_response_to_ir(
            {
                "content": blocks,
                "finish_reason": raw.get("stop_reason") or "stop",
                "usage": {
                    "input_tokens": (raw.get("usage") or {}).get("input_tokens", 0),
                    "output_tokens": (raw.get("usage") or {}).get("output_tokens", 0),
                    "total_tokens": (raw.get("usage") or {}).get("input_tokens", 0) + (raw.get("usage") or {}).get("output_tokens", 0),
                },
                "metadata": {"api_family": compiled.api_family, "tool_runtime": compiled.metadata.get("tool_runtime")},
            }
        )

    def parse_stream_chunk(self, raw, compiled):
        del compiled
        if not isinstance(raw, dict):
            return []
        event_type = str(raw.get("type") or "")
        events = []
        state = raw.setdefault("_compiler_state", {})
        if event_type == "content_block_start":
            block = raw.get("content_block") if isinstance(raw.get("content_block"), dict) else {}
            if block.get("type") == "tool_use":
                events.append(
                    RumiStreamEventIR(
                        type="tool_call_start",
                        metadata={
                            "id": str(block.get("id") or raw.get("index") or ""),
                            "name": str(block.get("name") or ""),
                        },
                    )
                )
        elif event_type == "content_block_delta":
            delta = raw.get("delta") if isinstance(raw.get("delta"), dict) else {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                events.append(
                    RumiStreamEventIR(
                        type="content_delta",
                        delta={"type": "text", "text": str(delta["text"])},
                    )
                )
            elif delta.get("type") in {"thinking_delta", "signature_delta"}:
                text = delta.get("thinking") or delta.get("text")
                if text:
                    events.append(
                        RumiStreamEventIR(
                            type="reasoning_delta",
                            delta={"type": "text", "text": str(text)},
                        )
                    )
            elif delta.get("type") == "input_json_delta":
                events.append(
                    RumiStreamEventIR(
                        type="tool_call_delta",
                        metadata={
                            "id": str(state.get("id") or raw.get("index") or ""),
                            "name": str(state.get("name") or ""),
                            "arguments_chunk": str(delta.get("partial_json") or ""),
                        },
                    )
                )
        elif event_type == "content_block_stop":
            if state.get("id") or state.get("name"):
                events.append(
                    RumiStreamEventIR(
                        type="tool_call_end",
                        metadata={
                            "id": str(state.get("id") or raw.get("index") or ""),
                            "name": str(state.get("name") or ""),
                        },
                    )
                )
        elif event_type == "message_delta":
            delta = raw.get("delta") if isinstance(raw.get("delta"), dict) else {}
            usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
            events.append(
                RumiStreamEventIR(
                    type="stream_end",
                    finish_reason=str(delta.get("stop_reason") or "stop"),
                    usage={
                        "input_tokens": int(usage.get("input_tokens") or 0),
                        "output_tokens": int(usage.get("output_tokens") or 0),
                        "total_tokens": int(usage.get("input_tokens") or 0)
                        + int(usage.get("output_tokens") or 0),
                    },
                )
            )
        return events


def _anthropic_content(message):
    content = message.get("content", "")
    if message.get("tool_calls"):
        parts = []
        if content:
            parts.append({"type": "text", "text": str(content)})
        for tool_call in message.get("tool_calls", []) or []:
            function_def = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
            args = function_def.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"value": args}
            parts.append({"type": "tool_use", "id": tool_call.get("id", ""), "name": function_def.get("name", ""), "input": args})
        return parts
    if message.get("role") == "tool":
        return [{"type": "tool_result", "tool_use_id": message.get("tool_call_id", ""), "content": str(content or "")}]
    if isinstance(content, list):
        return [{"type": "text", "text": str(part.get("text") or part)} for part in content]
    return str(content or "")
