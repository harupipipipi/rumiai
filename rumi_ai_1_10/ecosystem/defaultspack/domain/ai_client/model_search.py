from __future__ import annotations

from copy import deepcopy
from typing import Any

from domain.ai_client.model_groups import normalize_model_groups


def search_models(filters: dict[str, Any] | None = None, *, profiles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    filters = dict(filters or {})
    if profiles is None:
        profiles = _profile_catalog()
    query = str(filters.get("query") or "").strip().casefold()
    requires = filters.get("requires") if isinstance(filters.get("requires"), dict) else {}
    speed_filter = _as_set(filters.get("speed_tier"))
    provider_id = str(filters.get("provider_id") or filters.get("provider") or "").strip()
    configured_only = bool(filters.get("configured_only", False))
    local_only = bool(filters.get("local_only", False))
    try:
        min_knowledge_level = int(filters.get("min_knowledge_level", 0) or 0)
    except (TypeError, ValueError):
        min_knowledge_level = 0
    try:
        max_results = max(1, min(100, int(filters.get("max_results", 20) or 20)))
    except (TypeError, ValueError):
        max_results = 20

    matches: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict) or str(profile.get("type") or "chat") not in {"", "chat", "reasoning"}:
            continue
        item = _public_model(profile)
        if query and query not in _search_text(item):
            continue
        if provider_id and item.get("provider_id") != provider_id:
            continue
        if configured_only and not item.get("configured"):
            continue
        if local_only and not item.get("local"):
            continue
        if min_knowledge_level and int(item.get("knowledge_level") or 0) < min_knowledge_level:
            continue
        if speed_filter and str(item.get("speed_tier") or "") not in speed_filter:
            continue
        if not _matches_required_capabilities(item, requires):
            continue
        item["score"] = _score_model(item, filters)
        matches.append(item)
    matches.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("label") or item.get("profile_id") or "").casefold()))
    return {
        "models": [deepcopy(item) for item in matches[:max_results]],
        "filters_applied": {
            "query": filters.get("query", ""),
            "requires": deepcopy(requires),
            "min_knowledge_level": min_knowledge_level,
            "speed_tier": sorted(speed_filter),
            "configured_only": configured_only,
            "provider_id": provider_id,
            "max_results": max_results,
        },
    }


def get_model_capabilities(profile_id: str, *, profiles: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    needle = str(profile_id or "").strip()
    if not needle:
        return None
    for profile in profiles if profiles is not None else _profile_catalog():
        if not isinstance(profile, dict):
            continue
        aliases = {
            str(profile.get("profile_id") or ""),
            str(profile.get("qualified_model_id") or ""),
            "{}/{}".format(profile.get("provider_id") or profile.get("provider") or "", profile.get("model_id") or ""),
        }
        if needle in aliases:
            return _public_model(profile)
    return None


def recommend_model(request: dict[str, Any] | None = None, *, profiles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    request = dict(request or {})
    filters = {
        "query": request.get("query", ""),
        "requires": request.get("requires", {}),
        "min_knowledge_level": request.get("min_knowledge_level", 0),
        "speed_tier": request.get("speed_tier"),
        "configured_only": request.get("configured_only", False),
        "provider_id": request.get("provider_id", ""),
        "max_results": request.get("max_results", 10),
    }
    result = search_models(filters, profiles=profiles)
    selected = result["models"][0] if result["models"] else None
    return {
        "selected_model": selected,
        "candidates": result["models"],
        "reason_codes": _recommendation_reasons(selected, request) if selected else ["no_matching_model"],
        "filters_applied": result["filters_applied"],
    }


def models_for_group(group_id: str, settings: dict[str, Any] | None, profiles: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    groups = normalize_model_groups((settings or {}).get("model_groups") if isinstance(settings, dict) else None)
    group = groups.get(str(group_id or "default"), groups["default"])
    candidates = [_public_model(profile) for profile in (profiles if profiles is not None else _profile_catalog()) if isinstance(profile, dict)]
    allowed = {str(item) for item in group.get("allowed_models", []) if str(item or "").strip()}
    if allowed:
        candidates = [item for item in candidates if str(item.get("profile_id") or "") in allowed or str(item.get("qualified_model_id") or "") in allowed]
    if group.get("require_vision"):
        candidates = [item for item in candidates if item.get("supports_vision")]
    if group.get("require_thinking"):
        candidates = [item for item in candidates if item.get("supports_thinking")]
    min_level = group.get("min_knowledge_level")
    if min_level is not None:
        try:
            floor = int(min_level)
            candidates = [item for item in candidates if int(item.get("knowledge_level") or 0) >= floor]
        except (TypeError, ValueError):
            pass
    max_level = group.get("max_knowledge_level")
    if max_level is not None:
        try:
            ceiling = int(max_level)
            candidates = [item for item in candidates if int(item.get("knowledge_level") or 0) <= ceiling]
        except (TypeError, ValueError):
            pass
    min_speed = str(group.get("min_speed_tier") or "").strip()
    if min_speed:
        candidates = [item for item in candidates if str(item.get("speed_tier") or "") == min_speed]
    return candidates


def _profile_catalog() -> list[dict[str, Any]]:
    try:
        from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog
    except ModuleNotFoundError:
        from backend.ai_client.provider_catalog import list_profile_catalog
    return list_profile_catalog()


def _public_model(profile: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(profile.get("profile_id") or profile.get("qualified_model_id") or profile.get("id") or "").strip()
    provider_id = str(profile.get("provider_id") or profile.get("provider") or "").strip()
    model_id = str(profile.get("model_id") or profile.get("model") or "").strip()
    label_provider = str(profile.get("provider_display_name") or profile.get("provider_name") or provider_id or "").strip()
    display_name = str(profile.get("display_name") or profile.get("name") or model_id or profile_id).strip()
    availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
    configured = bool(
        profile.get("configured")
        or availability.get("configured")
        or availability.get("active")
        or str(availability.get("status") or "").lower() in {"configured", "active"}
        or provider_id == "stub"
    )
    return {
        "profile_id": profile_id,
        "qualified_model_id": str(profile.get("qualified_model_id") or profile_id),
        "label": f"{label_provider} / {display_name}" if label_provider else display_name,
        "display_name": display_name,
        "provider_id": provider_id,
        "provider_display_name": label_provider,
        "model_id": model_id,
        "configured": configured,
        "local": bool(profile.get("local") or availability.get("local") or provider_id in {"stub", "ollama", "lmstudio", "vllm", "llamacpp"}),
        "requires_api_key": bool(provider_id and provider_id not in {"stub"} and not configured),
        "supports_vision": bool(profile.get("supports_vision")),
        "supports_image_input": bool(profile.get("supports_image_input") or profile.get("supports_vision")),
        "supports_tool_calling": bool(profile.get("supports_tool_calling")),
        "supports_thinking": bool(profile.get("supports_thinking")),
        "thinking_levels": list(profile.get("thinking_levels") or []),
        "supports_fast": bool(profile.get("supports_fast")),
        "speed_tier": str(profile.get("speed_tier") or "balanced"),
        "quality_tier": str(profile.get("quality_tier") or "unknown"),
        "knowledge_level": int(profile.get("knowledge_level") or 0),
        "knowledge_band": str(profile.get("knowledge_band") or "unknown"),
        "cost_tier": str(profile.get("cost_tier") or "unknown"),
        "capability_tags": list(profile.get("capability_tags") or []),
        "recommended_roles": list(profile.get("recommended_roles") or []),
        "allowed_roles": list(profile.get("allowed_roles") or []),
        "max_context": profile.get("max_context"),
        "availability": deepcopy(availability),
        "metadata": deepcopy(profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}),
    }


def _as_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip()} if value.strip() else set()
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item or "").strip()}
    return set()


def _matches_required_capabilities(item: dict[str, Any], requires: dict[str, Any]) -> bool:
    mapping = {
        "vision": "supports_vision",
        "image_input": "supports_image_input",
        "tool_calling": "supports_tool_calling",
        "tools": "supports_tool_calling",
        "thinking": "supports_thinking",
        "fast": "supports_fast",
    }
    for source, target in mapping.items():
        if requires.get(source) is True and not item.get(target):
            return False
    return True


def _score_model(item: dict[str, Any], filters: dict[str, Any]) -> int:
    score = int(item.get("knowledge_level") or 0)
    score += 25 if item.get("configured") else 0
    score += 10 if item.get("supports_thinking") and (filters.get("requires") or {}).get("thinking") else 0
    score += 10 if item.get("supports_vision") and (filters.get("requires") or {}).get("vision") else 0
    score += 8 if item.get("supports_tool_calling") and (filters.get("requires") or {}).get("tool_calling") else 0
    score += 6 if item.get("speed_tier") == "fast" else 0
    score += 4 if item.get("local") else 0
    return score


def _search_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("profile_id", "qualified_model_id", "label", "display_name", "provider_id", "model_id", "knowledge_band")
    ).casefold()


def _recommendation_reasons(selected: dict[str, Any] | None, request: dict[str, Any]) -> list[str]:
    if not selected:
        return ["no_matching_model"]
    reasons = []
    requires = request.get("requires") if isinstance(request.get("requires"), dict) else {}
    if requires.get("vision") and selected.get("supports_vision"):
        reasons.append("requires_vision")
    if requires.get("tool_calling") and selected.get("supports_tool_calling"):
        reasons.append("requires_tool_calling")
    if requires.get("thinking") and selected.get("supports_thinking"):
        reasons.append("requires_thinking")
    if selected.get("speed_tier") == "fast":
        reasons.append("fast_candidate")
    if not reasons:
        reasons.append("best_available_match")
    return reasons
