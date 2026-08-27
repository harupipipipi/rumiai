from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


MODEL_POLICY_MODES = {
    "inherit_conversation",
    "fixed",
    "snapshot",
    "auto_route",
}
THINKING_POLICY_MODES = {
    "inherit_conversation",
    "fixed",
    "model_default",
}
THINKING_LEVELS = {"none", "low", "medium", "high", "xhigh"}
INHERIT_CONVERSATION_MODEL = "@inherit_conversation"


class ModelPolicyResolutionError(ValueError):
    """Raised when a secondary runtime model policy cannot fail safely."""

    def __init__(self, code: str, message: str, receipt: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.receipt = receipt


def normalize_model_policy(
    value: Any,
    *,
    legacy_model: str = "",
    required_capabilities: Any = None,
) -> dict[str, Any]:
    """Normalize a secondary-runtime model policy without resolving it."""

    structured_policy = isinstance(value, dict)
    raw = dict(value) if structured_policy else {}
    legacy = str(legacy_model or "").strip()
    if legacy == INHERIT_CONVERSATION_MODEL:
        legacy = ""
        raw.setdefault("mode", "inherit_conversation")
    mode = str(raw.get("mode") or ("fixed" if legacy else "auto_route")).strip()
    if mode not in MODEL_POLICY_MODES:
        raise ValueError(
            "model policy mode must be inherit_conversation, fixed, snapshot, or auto_route"
        )
    profile_id = str(
        raw.get("profile_id") or raw.get("model_profile_id") or (legacy if mode == "fixed" else "")
    ).strip()
    fallback_profile_id = str(raw.get("fallback_profile_id") or "").strip()
    snapshot_profile_id = str(
        raw.get("snapshot_profile_id") or raw.get("captured_profile_id") or ""
    ).strip()
    capabilities = _normalize_capabilities(
        raw.get("required_capabilities")
        if raw.get("required_capabilities") is not None
        else required_capabilities
    )
    if mode == "fixed" and not profile_id:
        raise ValueError("fixed model policy requires profile_id")
    on_unavailable = str(
        raw.get("on_unavailable") or ("fallback" if fallback_profile_id else "error")
    ).strip()
    if on_unavailable not in {"error", "fallback"}:
        raise ValueError("on_unavailable must be error or fallback")
    return {
        "mode": mode,
        "profile_id": profile_id,
        "fallback_profile_id": fallback_profile_id,
        "snapshot_profile_id": snapshot_profile_id,
        "required_capabilities": capabilities,
        "on_unavailable": on_unavailable,
        "strict_validation": structured_policy,
    }


def normalize_thinking_policy(value: Any, *, legacy_level: str = "") -> dict[str, Any]:
    """Normalize thinking inheritance independently from model selection."""

    raw = dict(value) if isinstance(value, dict) else {}
    legacy = str(legacy_level or "").strip()
    mode = str(raw.get("mode") or ("fixed" if legacy else "model_default")).strip()
    if mode not in THINKING_POLICY_MODES:
        raise ValueError(
            "thinking policy mode must be inherit_conversation, fixed, or model_default"
        )
    level = str(raw.get("level") or legacy or "").strip()
    if mode == "fixed" and level not in THINKING_LEVELS:
        raise ValueError("fixed thinking policy requires a valid level")
    return {"mode": mode, "level": level}


def resolve_secondary_model_policy(
    model_policy: Any = None,
    thinking_policy: Any = None,
    *,
    context: dict[str, Any] | None = None,
    profiles: Iterable[dict[str, Any]] | None = None,
    legacy_model: str = "",
    legacy_thinking_level: str = "",
    required_capabilities: Any = None,
    replay_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a secondary runtime model and return an auditable receipt."""

    runtime = dict(context or {})
    requested_model_policy = normalize_model_policy(
        model_policy,
        legacy_model=legacy_model,
        required_capabilities=required_capabilities,
    )
    requested_thinking_policy = normalize_thinking_policy(
        thinking_policy,
        legacy_level=legacy_thinking_level,
    )
    profile_list = [dict(item) for item in (profiles or []) if isinstance(item, dict)]
    profile_index = _profile_index(profile_list)
    public_model_policy = {
        key: deepcopy(value)
        for key, value in requested_model_policy.items()
        if key != "strict_validation"
    }
    receipt: dict[str, Any] = {
        "contract_version": "tobkiri.secondary-model-policy.v1",
        "requested_model_policy": public_model_policy,
        "requested_thinking_policy": deepcopy(requested_thinking_policy),
        "required_capabilities": list(requested_model_policy["required_capabilities"]),
        "resolved_profile_id": "",
        "resolution_source": "",
        "fallback_reason": "",
        "thinking_level": "",
        "thinking_source": "",
        "thinking_translation": {},
    }

    replay_mode = str(runtime.get("replay_mode") or "").strip().lower()
    if replay_mode in {"deterministic", "strict"} and isinstance(replay_receipt, dict):
        replay_model = str(replay_receipt.get("resolved_profile_id") or "").strip()
        if replay_model:
            selected = replay_model
            source = "replay_receipt"
            receipt["replay"] = True
        else:
            selected, source = _select_requested_profile(
                requested_model_policy, runtime, profile_list
            )
    else:
        selected, source = _select_requested_profile(requested_model_policy, runtime, profile_list)

    strict_validation = bool(requested_model_policy["strict_validation"])
    if not strict_validation:
        profile = profile_index.get(selected)
        failure_code = ""
        failure_reason = ""
    else:
        profile, failure_code, failure_reason = _validate_profile(
            selected,
            profile_index,
            requested_model_policy["required_capabilities"],
            catalog_is_authoritative=bool(profile_list),
        )
    if failure_code and requested_model_policy["mode"] == "auto_route":
        routed_profile = _first_available_profile(
            profile_list,
            requested_model_policy["required_capabilities"],
            excluded_profile_id=selected,
        )
        if routed_profile is not None:
            receipt["fallback_reason"] = f"{failure_code}:{failure_reason}"
            selected = _profile_id(routed_profile)
            profile = routed_profile
            source = "canonical_catalog_fallback"
            failure_code = ""
            failure_reason = ""
    if failure_code:
        fallback = requested_model_policy["fallback_profile_id"]
        if fallback and requested_model_policy["on_unavailable"] == "fallback":
            fallback_profile, fallback_code, fallback_failure = _validate_profile(
                fallback,
                profile_index,
                requested_model_policy["required_capabilities"],
                catalog_is_authoritative=bool(profile_list),
            )
            if fallback_code:
                receipt["fallback_reason"] = f"{failure_code}:{failure_reason}"
                receipt["fallback_failure"] = f"{fallback_code}:{fallback_failure}"
                _raise(fallback_code, fallback_failure, receipt)
            selected = fallback
            profile = fallback_profile
            source = "fallback_profile"
            receipt["fallback_reason"] = f"{failure_code}:{failure_reason}"
        else:
            _raise(failure_code, failure_reason, receipt)

    receipt["resolved_profile_id"] = selected
    receipt["resolution_source"] = source
    if requested_model_policy["mode"] == "snapshot":
        receipt["snapshot_profile_id"] = selected
        receipt["snapshot_captured"] = not bool(requested_model_policy["snapshot_profile_id"])

    resolved_thinking, thinking_source = _resolve_thinking(
        requested_thinking_policy,
        runtime,
        profile,
    )
    thinking_code, thinking_reason = _validate_thinking(resolved_thinking, profile)
    if thinking_code:
        _raise(thinking_code, thinking_reason, receipt)
    receipt["thinking_level"] = resolved_thinking
    receipt["thinking_source"] = thinking_source
    receipt["thinking_translation"] = {
        "requested": requested_thinking_policy.get("level") or requested_thinking_policy["mode"],
        "resolved": resolved_thinking,
        "translated": False,
    }
    if profile:
        receipt["provider_id"] = str(profile.get("provider_id") or profile.get("provider") or "")
        receipt["model_id"] = str(profile.get("model_id") or profile.get("model") or selected)
    return receipt


def _select_requested_profile(
    policy: dict[str, Any],
    context: dict[str, Any],
    profiles: list[dict[str, Any]],
) -> tuple[str, str]:
    turn_model = _first_string(context, "turn_model_profile_id", "turn_model", "model_override")
    conversation_model = _first_string(
        context,
        "conversation_model_profile_id",
        "conversation_model",
        "selected_model",
    )
    global_model = _first_string(
        context,
        "global_model_profile_id",
        "preferred_model",
        "global_model",
    )
    mode = policy["mode"]
    if mode == "fixed":
        return policy["profile_id"], "fixed_policy"
    if mode == "snapshot":
        snapshot = policy["snapshot_profile_id"] or _first_string(
            context,
            "snapshot_model_profile_id",
            "snapshot_model",
        )
        return (snapshot or conversation_model or global_model), (
            "snapshot_policy" if snapshot else "snapshot_capture"
        )
    if mode == "inherit_conversation":
        return (turn_model or conversation_model or global_model), (
            "turn_override"
            if turn_model
            else "conversation_model"
            if conversation_model
            else "global_model"
        )
    if turn_model:
        return turn_model, "turn_override"
    auto_routed = _first_string(context, "auto_route_profile_id", "auto_routed_model")
    if auto_routed:
        return auto_routed, "auto_route"
    candidates = [global_model, conversation_model]
    candidates.extend(_profile_id(profile) for profile in profiles)
    return next((candidate for candidate in candidates if candidate), ""), "auto_route"


def _validate_profile(
    profile_id: str,
    profile_index: dict[str, dict[str, Any]],
    required_capabilities: list[str],
    *,
    catalog_is_authoritative: bool,
) -> tuple[dict[str, Any] | None, str, str]:
    selected = str(profile_id or "").strip()
    if not selected:
        return None, "MODEL_POLICY_NO_MODEL", "model policy did not resolve a model profile"
    profile = profile_index.get(selected)
    if profile is None:
        if catalog_is_authoritative:
            return (
                None,
                "MODEL_PROFILE_UNKNOWN",
                f"model profile is not in the canonical catalog: {selected}",
            )
        return None, "", ""
    availability = (
        profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
    )
    status = str(availability.get("status") or "").strip()
    unavailable = (
        availability.get("active") is False
        or availability.get("configured") is False
        or profile.get("configured") is False
    )
    if unavailable:
        code = (
            "MODEL_API_KEY_MISSING"
            if status == "missing_api_key" or profile.get("requires_api_key")
            else "MODEL_PROFILE_UNAVAILABLE"
        )
        return profile, code, status or "model profile is unavailable"
    missing = [
        capability
        for capability in required_capabilities
        if not _profile_supports(profile, capability)
    ]
    if missing:
        return (
            profile,
            "MODEL_CAPABILITY_UNSATISFIED",
            "missing capabilities: " + ", ".join(missing),
        )
    return profile, "", ""


def _first_available_profile(
    profiles: list[dict[str, Any]],
    required_capabilities: list[str],
    *,
    excluded_profile_id: str = "",
) -> dict[str, Any] | None:
    for profile in profiles:
        profile_id = _profile_id(profile)
        if not profile_id or profile_id == excluded_profile_id:
            continue
        _, failure_code, _ = _validate_profile(
            profile_id,
            _profile_index([profile]),
            required_capabilities,
            catalog_is_authoritative=True,
        )
        if not failure_code:
            return profile
    return None


def _resolve_thinking(
    policy: dict[str, Any],
    context: dict[str, Any],
    profile: dict[str, Any] | None,
) -> tuple[str, str]:
    if policy["mode"] == "fixed":
        return policy["level"], "fixed_policy"
    if policy["mode"] == "inherit_conversation":
        turn = _first_string(context, "turn_thinking_level")
        conversation = _first_string(context, "conversation_thinking_level")
        global_level = _first_string(context, "global_thinking_level", "thinking_level")
        return (turn or conversation or global_level or "none"), (
            "turn_override"
            if turn
            else "conversation_thinking"
            if conversation
            else "global_thinking"
        )
    if profile:
        defaults = profile.get("defaults") if isinstance(profile.get("defaults"), dict) else {}
        level = str(
            profile.get("default_thinking_level") or defaults.get("thinking_level") or "none"
        ).strip()
        return level or "none", "model_default"
    return "none", "model_default"


def _validate_thinking(
    level: str,
    profile: dict[str, Any] | None,
) -> tuple[str, str]:
    if level not in THINKING_LEVELS:
        return "THINKING_LEVEL_INVALID", f"unsupported thinking level: {level}"
    if not profile or level == "none":
        return "", ""
    supports = profile.get("supports_thinking")
    if supports is False:
        return "MODEL_THINKING_UNSUPPORTED", "selected model does not support thinking"
    supported_levels = profile.get("thinking_levels")
    if isinstance(supported_levels, list) and supported_levels:
        normalized = {str(item or "").strip() for item in supported_levels}
        if level not in normalized:
            return (
                "MODEL_THINKING_LEVEL_UNSUPPORTED",
                f"selected model does not support thinking level: {level}",
            )
    return "", ""


def _profile_supports(profile: dict[str, Any], capability: str) -> bool:
    normalized = str(capability or "").strip().lower()
    if normalized in {"", "model.text", "text", "chat"}:
        return True
    aliases = {
        "model.image_input": ("supports_image_input", "supports_vision", "image_input", "vision"),
        "model.vision": ("supports_vision", "supports_image_input", "vision", "image_input"),
        "model.tool_calling": ("supports_tool_calling", "tool_calling", "tool_calls"),
        "model.thinking": ("supports_thinking", "thinking"),
        "model.fast": ("supports_fast", "fast"),
        "model.audio_input": ("supports_audio_input", "audio_input", "audio"),
    }
    checks = aliases.get(normalized, (normalized, normalized.removeprefix("model.")))
    metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    capabilities = profile.get("capabilities")
    metadata_capabilities = metadata.get("capabilities")
    tags = {
        str(item or "").strip().lower()
        for values in (profile.get("capability_tags"), metadata.get("capability_tags"))
        if isinstance(values, list)
        for item in values
    }
    for key in checks:
        if profile.get(key) is True or metadata.get(key) is True:
            return True
        if isinstance(capabilities, dict) and capabilities.get(key) is True:
            return True
        if isinstance(metadata_capabilities, dict) and metadata_capabilities.get(key) is True:
            return True
        if key.lower() in tags or f"model.{key}".lower() in tags:
            return True
    return False


def _profile_index(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        for key in ("profile_id", "qualified_model_id", "id", "model_ref"):
            value = str(profile.get(key) or "").strip()
            if value:
                result.setdefault(value, profile)
        provider = str(profile.get("provider_id") or profile.get("provider") or "").strip()
        model = str(profile.get("model_id") or profile.get("model") or "").strip()
        if provider and model:
            result.setdefault(f"{provider}/{model}", profile)
    return result


def _profile_id(profile: dict[str, Any]) -> str:
    return str(
        profile.get("profile_id") or profile.get("qualified_model_id") or profile.get("id") or ""
    ).strip()


def _normalize_capabilities(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [item.strip() for item in value.replace(",", " ").split()]
    elif isinstance(value, (list, tuple, set)):
        values = [str(item or "").strip() for item in value]
    else:
        values = []
    return list(dict.fromkeys(item for item in values if item))


def _first_string(values: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(values.get(key) or "").strip()
        if value:
            return value
    return ""


def _raise(code: str, message: str, receipt: dict[str, Any]) -> None:
    receipt["error"] = {"code": code, "message": message}
    raise ModelPolicyResolutionError(code, message, receipt)
