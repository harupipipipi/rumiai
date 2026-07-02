from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.ai_client.model_metadata_schema import context_window_value, normalize_capability_map


@dataclass
class ProviderCapabilities:
    provider_id: str = "unknown"
    api_family: str = "unknown"
    api_surface: dict[str, Any] = field(default_factory=dict)
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
        has_api_surface = isinstance(raw.get("api_surface"), dict)
        api_surface = raw.get("api_surface") if has_api_surface else {}
        schema_support = raw.get("schema_support", api_surface.get("schema_support", {}))
        params = raw.get("params", api_surface.get("params", {}))
        api_accepts_content_blocks = (
            api_surface.get("accepts_content_blocks")
            or api_surface.get("supported_content_blocks")
            or raw.get("supported_content_blocks")
            or ["text"]
        )
        supported_content_blocks = raw.get("supported_content_blocks") or api_accepts_content_blocks
        tool_choice_modes = raw.get("tool_choice_modes") or api_surface.get("tool_choice_modes") or ["auto", "none"]
        if has_api_surface:
            supports_tool_shape = bool(
                api_surface.get("supports_tool_call_shape", api_surface.get("supports_tool_calling", False))
            )
            supports_parallel_shape = bool(
                api_surface.get(
                    "supports_parallel_tool_call_shape",
                    api_surface.get("supports_parallel_tool_calls", False),
                )
            )
        else:
            supports_tool_shape = bool(raw.get("supports_tool_call_shape", raw.get("supports_tool_calling", False)))
            supports_parallel_shape = bool(
                raw.get("supports_parallel_tool_call_shape", raw.get("supports_parallel_tool_calls", False))
            )
        api_family = str(raw.get("api_family") or api_surface.get("api_family") or "unknown")
        return cls(
            provider_id=str(raw.get("provider_id") or raw.get("id") or "unknown"),
            api_family=api_family,
            api_surface={
                "api_family": api_family,
                "supports_stream": bool(raw.get("supports_stream", api_surface.get("supports_stream", True))),
                "accepts_content_blocks": list(api_accepts_content_blocks),
                "supports_tool_call_shape": supports_tool_shape,
                "supports_parallel_tool_call_shape": supports_parallel_shape,
                "tool_choice_modes": list(tool_choice_modes),
                "schema_support": dict(schema_support or {}),
                "params": dict(params or {}),
            },
            supports_stream=bool(raw.get("supports_stream", api_surface.get("supports_stream", True))),
            supports_tool_calling=bool(raw.get("supports_tool_calling", False)),
            supports_parallel_tool_calls=bool(raw.get("supports_parallel_tool_calls", False)),
            supports_vision=bool(raw.get("supports_vision", False)),
            supports_audio=bool(raw.get("supports_audio", False)),
            supports_pdf=bool(raw.get("supports_pdf", False)),
            supports_file_upload=bool(raw.get("supports_file_upload", False)),
            supports_reasoning=bool(raw.get("supports_reasoning", False)),
            supported_roles=list(raw.get("supported_roles") or ["system", "user", "assistant", "tool"]),
            supported_content_blocks=list(supported_content_blocks),
            max_context_tokens=int(raw.get("max_context_tokens") or raw.get("max_context") or 0),
            max_output_tokens=int(raw.get("max_output_tokens") or 0),
            tool_choice_modes=list(tool_choice_modes),
            schema_support=dict(schema_support or {}),
            params=dict(params or {}),
            quirks=dict(raw.get("quirks") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "api_family": self.api_family,
            "api_surface": dict(self.api_surface),
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
    api_surface = dict(merged.get("api_surface") or {})
    provider_accepts_tool_calls = bool(api_surface.get("supports_tool_call_shape"))
    provider_content_blocks = list(api_surface.get("accepts_content_blocks") or merged.get("supported_content_blocks") or ["text"])
    for model_key in (
        "supports_tool_calling",
        "supports_parallel_tool_calls",
        "supports_vision",
        "supports_audio",
        "supports_pdf",
        "supports_file_upload",
        "supports_reasoning",
        "max_context_tokens",
    ):
        merged[model_key] = False if model_key != "max_context_tokens" else 0
    merged["supported_content_blocks"] = list(provider_content_blocks)
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
    if not provider_accepts_tool_calls:
        merged["supports_tool_calling"] = False
    if not merged.get("supports_tool_calling"):
        merged["supports_parallel_tool_calls"] = False
    if not merged.get("supports_vision"):
        merged["supported_content_blocks"] = [
            block for block in list(merged.get("supported_content_blocks") or []) if block not in {"image", "image_url"}
        ]
    return ProviderCapabilities.from_dict(merged)


def _normalize_model_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    capabilities = data.get("capabilities", metadata.get("capabilities", {}))
    capability_map = normalize_capability_map(capabilities)
    if isinstance(metadata.get("capabilities"), dict):
        capability_map.update(normalize_capability_map(metadata.get("capabilities")))
    normalized: dict[str, Any] = {}
    if "context_window" in data or "max_context" in data or "max_context_tokens" in data:
        normalized["max_context_tokens"] = context_window_value(data, default=0)
    if "max_output_tokens" in data:
        normalized["max_output_tokens"] = int(data.get("max_output_tokens") or 0)
    thinking = data.get("thinking") if isinstance(data.get("thinking"), dict) else {}
    modalities = data.get("modalities") if isinstance(data.get("modalities"), dict) else {}
    input_modalities = modalities.get("input") if isinstance(modalities.get("input"), list) else []
    if capability_map or "supports_tool_calling" in data:
        normalized["supports_tool_calling"] = bool(capability_map.get("tool_calling") or data.get("supports_tool_calling"))
    if capability_map:
        normalized["supports_parallel_tool_calls"] = bool(capability_map.get("parallel_tool_calls"))
    if capability_map or "supports_vision" in data:
        normalized["supports_vision"] = bool(
            capability_map.get("image_input")
            or data.get("supports_vision")
            or data.get("supports_image_input")
            or "image" in {str(item) for item in input_modalities}
        )
    if capability_map or "supports_audio" in data:
        normalized["supports_audio"] = bool(capability_map.get("audio_input") or data.get("supports_audio") or data.get("supports_audio_input"))
    if capability_map or "supports_pdf" in data:
        normalized["supports_pdf"] = bool(capability_map.get("pdf") or capability_map.get("supports_pdf") or data.get("supports_pdf"))
    if capability_map or "supports_file_upload" in data:
        normalized["supports_file_upload"] = bool(capability_map.get("file_upload") or capability_map.get("supports_file_upload") or data.get("supports_file_upload"))
    if capability_map or thinking or "supports_thinking" in data or "supports_reasoning" in data:
        normalized["supports_reasoning"] = bool(
            capability_map.get("thinking")
            or thinking.get("supported")
            or data.get("supports_thinking")
            or data.get("supports_reasoning")
        )
    if normalized.get("supports_vision"):
        normalized["supported_content_blocks"] = ["image", "image_url"]
    return normalized
