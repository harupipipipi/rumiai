from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderCapabilities:
    provider_id: str = "unknown"
    api_family: str = "unknown"
    supports_stream: bool = True
    supports_tool_calling: bool = False
    supports_parallel_tool_calls: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    supports_pdf: bool = False
    supports_file_upload: bool = False
    supports_reasoning: bool = False
    supported_roles: list[str] = field(default_factory=lambda: ["system", "user", "assistant", "tool"])
    supported_content_blocks: list[str] = field(default_factory=lambda: ["text"])
    max_context_tokens: int = 0
    max_output_tokens: int = 0
    tool_choice_modes: list[str] = field(default_factory=lambda: ["auto", "none"])
    schema_support: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    quirks: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ProviderCapabilities":
        raw = dict(raw or {})
        return cls(
            provider_id=str(raw.get("provider_id") or raw.get("id") or "unknown"),
            api_family=str(raw.get("api_family") or "unknown"),
            supports_stream=bool(raw.get("supports_stream", True)),
            supports_tool_calling=bool(raw.get("supports_tool_calling", False)),
            supports_parallel_tool_calls=bool(raw.get("supports_parallel_tool_calls", False)),
            supports_vision=bool(raw.get("supports_vision", False)),
            supports_audio=bool(raw.get("supports_audio", False)),
            supports_pdf=bool(raw.get("supports_pdf", False)),
            supports_file_upload=bool(raw.get("supports_file_upload", False)),
            supports_reasoning=bool(raw.get("supports_reasoning", False)),
            supported_roles=list(raw.get("supported_roles") or ["system", "user", "assistant", "tool"]),
            supported_content_blocks=list(raw.get("supported_content_blocks") or ["text"]),
            max_context_tokens=int(raw.get("max_context_tokens") or raw.get("max_context") or 0),
            max_output_tokens=int(raw.get("max_output_tokens") or 0),
            tool_choice_modes=list(raw.get("tool_choice_modes") or ["auto", "none"]),
            schema_support=dict(raw.get("schema_support") or {}),
            params=dict(raw.get("params") or {}),
            quirks=dict(raw.get("quirks") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "api_family": self.api_family,
            "supports_stream": self.supports_stream,
            "supports_tool_calling": self.supports_tool_calling,
            "supports_parallel_tool_calls": self.supports_parallel_tool_calls,
            "supports_vision": self.supports_vision,
            "supports_audio": self.supports_audio,
            "supports_pdf": self.supports_pdf,
            "supports_file_upload": self.supports_file_upload,
            "supports_reasoning": self.supports_reasoning,
            "supported_roles": list(self.supported_roles),
            "supported_content_blocks": list(self.supported_content_blocks),
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "tool_choice_modes": list(self.tool_choice_modes),
            "schema_support": dict(self.schema_support),
            "params": dict(self.params),
            "quirks": dict(self.quirks),
        }


def merge_capabilities(base: ProviderCapabilities, *overrides: dict[str, Any] | None) -> ProviderCapabilities:
    merged = base.to_dict()
    for raw in overrides:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_model_metadata(raw)
        for key, value in normalized.items():
            if value in (None, "", [], {}):
                continue
            if key in {"schema_support", "params", "quirks"}:
                merged[key] = {**dict(merged.get(key) or {}), **dict(value)}
            elif key in {"supported_roles", "supported_content_blocks", "tool_choice_modes"}:
                values = list(merged.get(key) or [])
                for item in list(value or []):
                    if item not in values:
                        values.append(item)
                merged[key] = values
            else:
                merged[key] = value
    return ProviderCapabilities.from_dict(merged)


def _normalize_model_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    capabilities = data.get("capabilities", metadata.get("capabilities", {}))
    if isinstance(capabilities, list):
        capability_map = {str(item): True for item in capabilities if str(item or "").strip()}
    elif isinstance(capabilities, dict):
        capability_map = dict(capabilities)
    else:
        capability_map = {}
    normalized: dict[str, Any] = {}
    if "context_window" in data or "max_context" in data or "max_context_tokens" in data:
        normalized["max_context_tokens"] = int(
            data.get("max_context_tokens", data.get("max_context", data.get("context_window", 0))) or 0
        )
    if "max_output_tokens" in data:
        normalized["max_output_tokens"] = int(data.get("max_output_tokens") or 0)
    if capability_map or "supports_tool_calling" in data:
        normalized["supports_tool_calling"] = bool(
            capability_map.get("tool_calls")
            or capability_map.get("tool_calling")
            or capability_map.get("supports_tool_calling")
            or capability_map.get("tools")
            or data.get("supports_tool_calling")
        )
    if capability_map or "supports_vision" in data:
        normalized["supports_vision"] = bool(capability_map.get("vision") or capability_map.get("image") or capability_map.get("supports_vision") or data.get("supports_vision"))
    if capability_map or "supports_audio" in data:
        normalized["supports_audio"] = bool(capability_map.get("audio") or capability_map.get("supports_audio") or data.get("supports_audio"))
    if capability_map or "supports_pdf" in data:
        normalized["supports_pdf"] = bool(capability_map.get("pdf") or capability_map.get("supports_pdf") or data.get("supports_pdf"))
    if capability_map or "supports_file_upload" in data:
        normalized["supports_file_upload"] = bool(capability_map.get("file_upload") or capability_map.get("supports_file_upload") or data.get("supports_file_upload"))
    if capability_map or "supports_thinking" in data or "supports_reasoning" in data:
        normalized["supports_reasoning"] = bool(
            capability_map.get("reasoning")
            or capability_map.get("thinking")
            or capability_map.get("supports_thinking")
            or capability_map.get("supports_reasoning")
            or data.get("supports_thinking")
            or data.get("supports_reasoning")
        )
    if normalized.get("supports_vision"):
        normalized["supported_content_blocks"] = ["image", "image_url"]
    return normalized
