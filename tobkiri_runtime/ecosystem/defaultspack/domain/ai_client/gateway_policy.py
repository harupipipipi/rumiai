from __future__ import annotations

from typing import Any


GATEWAY_IDS = {
    "cloudflare-ai-gateway",
    "litellm-proxy",
    "portkey-ai-gateway",
    "helicone-gateway",
}
_SECRET_FIELDS = {"api_key", "token", "authorization", "headers", "secret"}


def gateway_inventory(
    gateway_id: str,
    *,
    configured_routes: list[dict[str, Any]] | None = None,
    proxy_models: Any = None,
) -> list[dict[str, Any]]:
    gateway = str(gateway_id or "").strip().lower()
    if gateway not in GATEWAY_IDS:
        raise ValueError(f"Unknown gateway: {gateway}")
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for route in configured_routes or []:
        if not isinstance(route, dict):
            continue
        if _SECRET_FIELDS.intersection({str(key).lower() for key in route}):
            raise ValueError("Gateway route inventory must not contain secrets or headers")
        provider = str(route.get("upstream_provider") or "").strip()
        model = str(route.get("upstream_model") or "").strip()
        if not provider or not model:
            continue
        key = (provider, model)
        if key in seen:
            continue
        seen.add(key)
        output.append(_entry(gateway, provider, model, source="configured_gateway_route"))

    # LiteLLM exposes an authenticated proxy model list. For other gateways,
    # request logs are observability data and are intentionally ignored.
    if gateway == "litellm-proxy":
        raw_models = proxy_models.get("data") if isinstance(proxy_models, dict) else None
        for raw in raw_models if isinstance(raw_models, list) else []:
            model = str(raw.get("id") or "").strip() if isinstance(raw, dict) else ""
            provider = str(raw.get("litellm_provider") or "unknown").strip() if isinstance(raw, dict) else "unknown"
            if not model or (provider, model) in seen:
                continue
            seen.add((provider, model))
            output.append(_entry(gateway, provider, model, source="litellm_proxy_models_api"))
    return output


def _entry(gateway: str, upstream_provider: str, upstream_model: str, *, source: str) -> dict[str, Any]:
    slug = f"{upstream_provider}/{upstream_model}"
    return {
        "id": f"{gateway}/{slug}",
        "qualified_model_id": f"{gateway}/{slug}",
        "provider_id": gateway,
        "model_id": slug,
        "display_name": upstream_model,
        "type": "unknown",
        "capabilities": {
            "text_input": None,
            "text_output": None,
            "streaming": None,
            "tool_calling": None,
            "image_input": None,
        },
        "metadata": {
            "source": source,
            "gateway_id": gateway,
            "upstream_provider": upstream_provider,
            "upstream_model": upstream_model,
            "capability_confidence": "unknown",
        },
    }
