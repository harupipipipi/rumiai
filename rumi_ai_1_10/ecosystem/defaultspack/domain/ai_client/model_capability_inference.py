from __future__ import annotations

import re
from typing import Any

from domain.ai_client.model_capability_schema import (
    ModelCapabilityFlags,
    ModelCapabilityRecord,
    ModalityCapability,
    RoleCapability,
    RoutingCapability,
    ThinkingCapability,
    knowledge_band_for_level,
)


LOCAL_PROVIDERS = {"ollama", "lmstudio", "vllm", "llamacpp"}
TOOL_CAPABLE_PROVIDERS = {
    "openai",
    "anthropic",
    "google",
    "genspark",
    "groq",
    "together",
    "fireworks",
    "glm",
    "deepseek",
    "openai_compatible",
}
VISION_CAPABLE_PROVIDERS = {"openai", "anthropic", "google", "genspark", "fireworks", "xai"}
AUDIO_CAPABLE_PROVIDERS = {"openai", "google"}
STRUCTURED_OUTPUT_PROVIDERS = {"openai", "google", "genspark", "openai_compatible"}
FAST_MODEL_RE = re.compile(r"(flash|flash-lite|mini|nano|lite|turbo|fast|hy3|free|groq)", re.IGNORECASE)
SLOW_MODEL_RE = re.compile(r"(pro|opus|large|reason|thinking|r1|o3|o4|gpt-5\.5)", re.IGNORECASE)
VISION_MODEL_RE = re.compile(r"(vision|gpt-4o|gpt-5|gemini|claude|grok|pixtral|vl|omni)", re.IGNORECASE)
AUDIO_MODEL_RE = re.compile(r"(audio|omni|gpt-4o|gpt-5|gemini)", re.IGNORECASE)
TOOL_MODEL_RE = re.compile(r"(gpt-|gemini|claude|command|llama-3\.3|mistral-large|deepseek|glm)", re.IGNORECASE)
THINKING_MODEL_RE = re.compile(r"(gpt-5|claude|gemini|deepseek|reason|thinking|r1|o3|o4)", re.IGNORECASE)


def infer_model_capabilities(model: dict[str, Any]) -> ModelCapabilityRecord:
    item = dict(model or {})
    provider_id, model_id, qualified = _model_identity(item)
    supports_thinking = _supports_thinking(item)
    thinking_levels = _thinking_levels(item, supports_thinking)
    supports_vision = _supports_vision(item)
    supports_audio = _supports_audio_input(item)
    supports_tool_calling = _supports_tool_calling(item)
    if provider_id == "stub":
        supports_vision = False
        supports_audio = False
        supports_tool_calling = True
        supports_thinking = True
        thinking_levels = ["low", "medium", "high", "xhigh"]
    supports_fast = _supports_fast_mode(item)
    structured_output = _supports_structured_output(item)
    knowledge_level = _knowledge_level(item)
    speed_tier = _speed_tier(item)
    quality_tier = _quality_tier(item, knowledge_level)
    cost_tier = _cost_tier(item)
    tags = _capability_tags(
        {
            "supports_vision": supports_vision,
            "supports_audio": supports_audio,
            "supports_tool_calling": supports_tool_calling,
            "supports_thinking": supports_thinking,
            "supports_fast": supports_fast,
            "structured_output": structured_output,
            "max_context": _int(item.get("max_context", item.get("context_window", -1)), -1),
        }
    )
    input_modalities = ["text"] + (["image"] if supports_vision else []) + (["audio"] if supports_audio else [])
    roles_allowed = _allowed_roles(item, supports_vision, supports_tool_calling, supports_thinking, supports_fast, knowledge_level)
    roles_recommended = _recommended_roles(roles_allowed, supports_vision, supports_thinking, supports_fast, knowledge_level)
    return ModelCapabilityRecord(
        qualified_model_id=qualified,
        provider_id=provider_id,
        model_id=model_id,
        capabilities=ModelCapabilityFlags(
            text=True,
            vision=supports_vision,
            image_input=supports_vision,
            audio_input=supports_audio,
            tool_calling=supports_tool_calling,
            json_schema=structured_output,
            structured_output=structured_output,
            thinking=supports_thinking,
            parallel_tool_calls=_supports_parallel_tool_calls(item, supports_tool_calling, provider_id),
            streaming=_capability_truthy(item, "streaming", default=True),
        ),
        thinking=ThinkingCapability(
            supported=supports_thinking,
            levels=thinking_levels,
            default_level=str(item.get("default_thinking_level") or ("medium" if supports_thinking else "")) or None,
        ),
        routing=RoutingCapability(
            speed_tier=speed_tier,
            quality_tier=quality_tier,
            knowledge_level=knowledge_level,
            knowledge_band=knowledge_band_for_level(knowledge_level),
            cost_tier=cost_tier,
            latency_tier="low" if speed_tier == "fast" else "high" if speed_tier == "slow" else "medium",
        ),
        modalities=ModalityCapability(input=input_modalities, output=["text"]),
        roles=RoleCapability(allowed=roles_allowed, recommended=roles_recommended),
        capability_tags=tags,
    )


def _model_identity(model: dict[str, Any]) -> tuple[str, str, str]:
    qualified = str(model.get("qualified_model_id") or model.get("id") or "").strip()
    provider_id = str(model.get("provider_id") or model.get("provider") or "").strip()
    model_id = str(model.get("model_id") or model.get("model") or model.get("model_name") or "").strip()
    if not provider_id and qualified and "/" in qualified:
        provider_id, remainder = qualified.split("/", 1)
        model_id = model_id or remainder
    if not model_id and qualified and "/" in qualified:
        _, model_id = qualified.split("/", 1)
    if not qualified and provider_id and model_id:
        qualified = f"{provider_id}/{model_id}"
    if not provider_id:
        provider_id = "stub" if qualified == "stub/default" else ""
    if not model_id and qualified:
        model_id = qualified
    return provider_id, model_id, qualified or f"{provider_id}/{model_id}".strip("/")


def _supports_vision(model: dict[str, Any]) -> bool:
    explicit = _explicit_bool(model, "supports_vision", "supports_image_input", "image_input")
    if explicit is not None:
        return explicit
    provider_id, model_id, qualified = _model_identity(model)
    if _capability_truthy(model, "vision", "image", "images", "multimodal"):
        return True
    if provider_id == "stub":
        return True
    if provider_id in VISION_CAPABLE_PROVIDERS and VISION_MODEL_RE.search(f"{model_id} {qualified}"):
        return True
    return False


def _supports_audio_input(model: dict[str, Any]) -> bool:
    explicit = _explicit_bool(model, "supports_audio", "supports_audio_input", "audio_input", "input_audio")
    if explicit is not None:
        return explicit
    provider_id, model_id, qualified = _model_identity(model)
    model_type = str(model.get("type") or "chat").lower()
    if model_type not in {"chat", "reasoning", "vision"}:
        return False
    if _capability_truthy(model, "audio", "audio_input", "input_audio"):
        return True
    return provider_id in AUDIO_CAPABLE_PROVIDERS and bool(AUDIO_MODEL_RE.search(f"{model_id} {qualified}"))


def _supports_tool_calling(model: dict[str, Any]) -> bool:
    explicit = _explicit_bool(model, "supports_tool_calling", "tool_calling", "native_tool_calling", "tool_calls")
    if explicit is not None:
        return explicit
    provider_id, model_id, _qualified = _model_identity(model)
    if provider_id == "stub":
        return False
    if _capability_truthy(model, "tool_calling", "tool_calls", "native_tool_calling", "tools"):
        return True
    return provider_id in TOOL_CAPABLE_PROVIDERS and bool(TOOL_MODEL_RE.search(model_id))


def _supports_parallel_tool_calls(model: dict[str, Any], supports_tool_calling: bool, provider_id: str) -> bool:
    if not supports_tool_calling:
        return False
    explicit = _explicit_bool(model, "parallel_tool_calls")
    if explicit is not None:
        return explicit
    return provider_id in {"openai", "google", "openai_compatible", "genspark"}


def _supports_fast_mode(model: dict[str, Any]) -> bool:
    explicit = _explicit_bool(model, "supports_fast", "fast")
    if explicit is not None:
        return explicit
    defaults = model.get("defaults") if isinstance(model.get("defaults"), dict) else {}
    provider_id, model_id, qualified = _model_identity(model)
    return bool(defaults.get("fast") or FAST_MODEL_RE.search(f"{provider_id} {model_id} {qualified}"))


def _supports_thinking(model: dict[str, Any]) -> bool:
    explicit = _explicit_bool(model, "supports_thinking", "thinking", "reasoning")
    if explicit is not None:
        return explicit
    model_type = str(model.get("type") or "chat").lower()
    if model_type not in {"chat", "reasoning"}:
        return False
    provider_id, model_id, qualified = _model_identity(model)
    if provider_id == "stub":
        return True
    return bool(THINKING_MODEL_RE.search(f"{model_id} {qualified}"))


def _thinking_levels(model: dict[str, Any], supported: bool) -> list[str]:
    raw = model.get("thinking_levels")
    if isinstance(raw, list):
        levels = [str(item) for item in raw if str(item or "").strip()]
        return levels if supported else []
    return ["low", "medium", "high", "xhigh"] if supported else []


def _supports_structured_output(model: dict[str, Any]) -> bool:
    explicit = _explicit_bool(model, "structured_output", "json_schema", "response_format")
    if explicit is not None:
        return explicit
    provider_id, _model_id, _qualified = _model_identity(model)
    return provider_id in STRUCTURED_OUTPUT_PROVIDERS or _capability_truthy(model, "structured_output", "json_schema")


def _knowledge_level(model: dict[str, Any]) -> int:
    explicit = model.get("knowledge_level")
    if explicit is not None:
        return max(0, min(100, _int(explicit, 0)))
    provider_id, model_id, qualified = _model_identity(model)
    haystack = f"{provider_id}/{model_id} {qualified}".lower()
    if provider_id == "stub":
        return 0
    if "gpt-5.5" in haystack and "pro" in haystack:
        return 96
    if any(token in haystack for token in ("gpt-5", "claude-opus", "gemini-3-pro", "gemini-2.5-pro", "o3", "o4")):
        return 92
    if any(token in haystack for token in ("gpt-4", "claude-sonnet", "gemini-3-flash", "gemini-2.5-flash", "grok-3", "mistral-large")):
        return 85
    size_match = re.search(r"(\d+(?:\.\d+)?)\s*b", haystack)
    if size_match:
        size = float(size_match.group(1))
        if size >= 70:
            return 65
        if size >= 30:
            return 55
        if size >= 13:
            return 40
        if size >= 7:
            return 30
        if size >= 3:
            return 20
        return 10
    if provider_id in LOCAL_PROVIDERS:
        return 30
    return 75 if provider_id else 0


def _speed_tier(model: dict[str, Any]) -> str:
    explicit = str(model.get("speed_tier") or "").strip().lower()
    if explicit in {"fast", "balanced", "slow"}:
        return explicit
    provider_id, model_id, qualified = _model_identity(model)
    haystack = f"{provider_id} {model_id} {qualified}"
    if FAST_MODEL_RE.search(haystack):
        return "fast"
    if SLOW_MODEL_RE.search(haystack):
        return "slow"
    return "balanced"


def _quality_tier(model: dict[str, Any], knowledge_level: int) -> str:
    explicit = str(model.get("quality_tier") or "").strip().lower()
    if explicit:
        return explicit
    provider_id, _model_id, _qualified = _model_identity(model)
    if knowledge_level >= 92:
        return "frontier"
    if knowledge_level >= 85:
        return "high"
    if provider_id in LOCAL_PROVIDERS:
        return "local"
    if knowledge_level > 0:
        return "mid"
    return "unknown"


def _cost_tier(model: dict[str, Any]) -> str:
    explicit = str(model.get("cost_tier") or "").strip().lower()
    if explicit:
        return explicit
    pricing = model.get("pricing") if isinstance(model.get("pricing"), dict) else {}
    defaults = model.get("defaults") if isinstance(model.get("defaults"), dict) else {}
    text = " ".join(str(pricing.get(key) or defaults.get(key) or "") for key in ("tier", "price_tier", "price", "cost"))
    _provider_id, model_id, qualified = _model_identity(model)
    haystack = f"{text} {model_id} {qualified}".lower()
    if "free" in haystack:
        return "free"
    if any(token in haystack for token in ("low", "cheap", "mini", "nano", "lite", "flash")):
        return "low"
    if any(token in haystack for token in ("high", "expensive", "pro", "opus")):
        return "high"
    return "medium"


def _allowed_roles(
    model: dict[str, Any],
    supports_vision: bool,
    supports_tool_calling: bool,
    supports_thinking: bool,
    supports_fast: bool,
    knowledge_level: int,
) -> list[str]:
    roles = {"primary_chat", "subagent_default"}
    if supports_fast:
        roles.add("fast_reply")
    if supports_thinking or knowledge_level >= 85:
        roles.add("deep_reasoning")
    if supports_vision:
        roles.add("vision_ocr")
    if supports_tool_calling:
        roles.add("tool_selector")
    if knowledge_level >= 65:
        roles.update({"coding", "model_router", "prompt_compactor", "context_summarizer"})
    raw = model.get("model_roles")
    if isinstance(raw, list):
        roles.update(str(role) for role in raw if str(role or "").strip())
    return sorted(roles)


def _recommended_roles(
    allowed: list[str],
    supports_vision: bool,
    supports_thinking: bool,
    supports_fast: bool,
    knowledge_level: int,
) -> list[str]:
    recommended = ["primary_chat"]
    if supports_fast and "fast_reply" in allowed:
        recommended.append("fast_reply")
    if supports_thinking and "deep_reasoning" in allowed:
        recommended.append("deep_reasoning")
    if supports_vision and "vision_ocr" in allowed:
        recommended.append("vision_ocr")
    if knowledge_level >= 85 and "coding" in allowed:
        recommended.append("coding")
    return recommended


def _capability_tags(values: dict[str, Any]) -> list[str]:
    tags = []
    if values.get("supports_vision"):
        tags.append("vision")
    if values.get("supports_audio"):
        tags.append("audio")
    if values.get("supports_tool_calling"):
        tags.append("tools")
    if values.get("supports_thinking"):
        tags.append("thinking")
    if values.get("supports_fast"):
        tags.append("fast")
    if values.get("structured_output"):
        tags.append("structured_output")
    if _int(values.get("max_context"), -1) >= 100_000:
        tags.append("long_context")
    return tags


def _capability_container(model: dict[str, Any]) -> tuple[set[str], dict[str, Any]]:
    raw = model.get("capabilities")
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    meta_raw = metadata.get("capabilities")
    names: set[str] = set()
    values: dict[str, Any] = {}
    for candidate in (raw, meta_raw):
        if isinstance(candidate, dict):
            values.update(candidate)
            names.update(str(key).lower() for key, value in candidate.items() if bool(value))
        elif isinstance(candidate, list):
            names.update(str(item).lower() for item in candidate if str(item or "").strip())
    return names, values


def _capability_truthy(model: dict[str, Any], *names: str, default: bool = False) -> bool:
    capability_names, capability_values = _capability_container(model)
    normalized = {name.lower() for name in names}
    for name in normalized:
        if name in model:
            return bool(model.get(name))
        if name in capability_values:
            return bool(capability_values.get(name))
    return bool(capability_names.intersection(normalized)) or default


def _explicit_bool(model: dict[str, Any], *names: str) -> bool | None:
    _capability_names, capability_values = _capability_container(model)
    for name in names:
        if name in model and model.get(name) is not None:
            return bool(model.get(name))
        if name in capability_values:
            return bool(capability_values.get(name))
    return None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
