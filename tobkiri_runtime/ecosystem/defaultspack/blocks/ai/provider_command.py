from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
from domain.ai_client.provider_routing_settings import (
    gateway_routing_summary,
    normalize_gateway_target,
    normalize_provider_slug,
    update_gateway_routing_settings,
)


_GATEWAY_TOKENS = {
    "all",
    "auto",
    "gateway",
    "gateways",
    "openrouter",
    "open-router",
    "or",
    "vercel",
    "vercel-ai",
    "vercel-ai-gateway",
    "ai-gateway",
    "aigateway",
    "ai_gateway",
}
_MODE_TOKENS = {
    "auto": "auto",
    "default": "auto",
    "prefer": "prefer",
    "preferred": "prefer",
    "order": "prefer",
    "only": "only",
    "strict": "only",
}


def _clean(value: Any) -> str:
    return str(value or "").strip().lower()


def _switch_direct_provider(provider_id: str) -> dict[str, Any]:
    try:
        from domain.ai_client.providers import (
            get_best_model_for_provider,
            get_provider_catalog_map,
        )

        catalog = get_provider_catalog_map()
    except Exception as exc:
        return error(f"provider catalog is unavailable: {exc}", "PROVIDER_CATALOG_UNAVAILABLE")

    if provider_id not in catalog:
        return error(
            f"unknown provider: {provider_id}",
            "PROVIDER_NOT_FOUND",
            details={"provider_id": provider_id},
        )
    model_id = str(get_best_model_for_provider(provider_id, use_case="chat") or "").strip()
    if not model_id:
        return error(
            f"provider has no selectable chat model: {provider_id}",
            "PROVIDER_MODEL_NOT_FOUND",
            details={"provider_id": provider_id},
        )
    profile_id = model_id if model_id.startswith(f"{provider_id}/") else f"{provider_id}/{model_id}"
    selected = ModelRuntimeSettingsService().set_preferred_model(profile_id)
    return ok(
        {
            "message": f"Providerを {provider_id} に切り替えました。model={profile_id}",
            "provider_id": provider_id,
            "profile_id": profile_id,
            "selected": selected,
        }
    )


def run(input_data: Any, context: dict[str, Any]) -> dict[str, Any]:
    del context
    data = input_data if isinstance(input_data, dict) else {}
    raw_target = _clean(data.get("target") or data.get("gateway") or data.get("provider"))
    raw_upstream = _clean(data.get("upstream") or data.get("upstream_provider"))
    raw_mode = _clean(data.get("routing_mode") or data.get("mode"))

    if not raw_target:
        summary = gateway_routing_summary()
        summary["message"] = (
            "Gateway routing: "
            f"target={summary['target']}, mode={summary['mode']}, "
            f"provider={summary['primary_provider'] or 'auto'}, sort={summary['sort']}"
        )
        return ok(summary)

    if raw_target not in _GATEWAY_TOKENS and not raw_upstream and not raw_mode:
        return _switch_direct_provider(normalize_provider_slug(raw_target))

    if raw_target in {"auto", "default"}:
        settings = update_gateway_routing_settings(
            {
                "gateway_routing_target": "all",
                "gateway_provider_mode": "auto",
                "gateway_primary_provider": "",
                "gateway_provider_order": [],
                "gateway_provider_only": [],
                "gateway_provider_ignore": [],
                "gateway_provider_sort": "auto",
            }
        )
        summary = gateway_routing_summary(settings)
        summary["message"] = "Gateway provider routingをAutoに戻しました。"
        return ok(summary)

    target = normalize_gateway_target(raw_target)
    upstream = normalize_provider_slug(raw_upstream)
    mode = _MODE_TOKENS.get(raw_mode, "prefer" if upstream else "auto")
    patch: dict[str, Any] = {
        "gateway_routing_target": target,
        "gateway_provider_mode": mode,
        "gateway_primary_provider": upstream,
    }
    if mode == "auto":
        patch.update(
            {
                "gateway_provider_order": [],
                "gateway_provider_only": [],
            }
        )
    elif mode == "prefer":
        patch.update(
            {
                "gateway_provider_order": [upstream] if upstream else [],
                "gateway_provider_only": [],
            }
        )
    elif mode == "only":
        if not upstream:
            return error(
                "provider mode 'only' requires an upstream provider slug",
                "UPSTREAM_PROVIDER_REQUIRED",
            )
        patch.update(
            {
                "gateway_provider_order": [],
                "gateway_provider_only": [upstream],
            }
        )

    settings = update_gateway_routing_settings(patch)
    summary = gateway_routing_summary(settings)
    summary["message"] = (
        f"Gateway routingを target={target}, mode={mode}, "
        f"provider={upstream or 'auto'} に更新しました。"
    )
    return ok(summary)
