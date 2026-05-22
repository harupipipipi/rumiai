from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.chat.ir import RumiResponseIR, RumiStreamEventIR, RumiUsageIR
from domain.chat.ir_blocks import RumiIRBlock


@dataclass
class CompiledProviderRequest:
    api_family: str
    provider_id: str
    model: str
    path: str
    method: str = "POST"
    body: dict[str, Any] = field(default_factory=dict)
    headers_extra: dict[str, str] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    dropped_features: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    legacy_messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_family": self.api_family,
            "provider_id": self.provider_id,
            "model": self.model,
            "path": self.path,
            "method": self.method,
            "body": self.body,
            "headers_extra": self.headers_extra,
            "warnings": self.warnings,
            "dropped_features": self.dropped_features,
            "trace": self.trace,
            "legacy_messages": self.legacy_messages,
            "metadata": self.metadata,
        }


class ProviderCompiler:
    api_family = "unknown"

    def compile_complete(self, planned: PlannedProviderRequest) -> CompiledProviderRequest:
        raise NotImplementedError

    def compile_stream(self, planned: PlannedProviderRequest) -> CompiledProviderRequest:
        compiled = self.compile_complete(planned)
        compiled.body["stream"] = True
        return compiled

    def parse_response(self, raw: dict[str, Any], compiled: CompiledProviderRequest) -> RumiResponseIR:
        raise NotImplementedError

    def parse_stream_chunk(self, raw: dict[str, Any], compiled: CompiledProviderRequest) -> list[RumiStreamEventIR]:
        del raw, compiled
        return []


def standard_response_to_ir(response: dict[str, Any]) -> RumiResponseIR:
    content = response.get("content", []) if isinstance(response, dict) else []
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    blocks: list[RumiIRBlock] = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, str):
            blocks.append(RumiIRBlock(type="text", text=block))
        elif isinstance(block, dict):
            block_type = str(block.get("type") or "text")
            if block_type == "tool_use":
                from domain.chat.ir_blocks import RumiToolCallIR

                blocks.append(
                    RumiIRBlock(
                        type="tool_call",
                        tool_call=RumiToolCallIR(
                            id=str(block.get("id") or ""),
                            name=str(block.get("name") or ""),
                            arguments=block.get("input", "{}"),
                        ),
                        original=dict(block),
                    )
                )
            else:
                blocks.append(
                    RumiIRBlock(
                        type=block_type,
                        text=str(block.get("text") or ""),
                        data={key: value for key, value in block.items() if key not in {"type", "text"}},
                        original=dict(block),
                    )
                )
    usage_raw = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    usage = RumiUsageIR(
        input_tokens=int(usage_raw.get("input_tokens", usage_raw.get("prompt_tokens", 0)) or 0),
        output_tokens=int(usage_raw.get("output_tokens", usage_raw.get("completion_tokens", 0)) or 0),
        total_tokens=int(usage_raw.get("total_tokens", 0) or 0),
    )
    return RumiResponseIR(
        content=blocks,
        finish_reason=str(response.get("finish_reason") or "stop"),
        usage=usage,
        metadata=dict(response.get("metadata") or {}),
        raw_extra=dict(response.get("raw_extra") or {}),
    )
