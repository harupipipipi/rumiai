from __future__ import annotations

from blocks._common import error, ok
from domain.webhook.url_providers.cloudflare_quick_tunnel import CloudflareQuickTunnelProvider
from domain.webhook.url_providers.static import StaticWebhookUrlProvider


def _provider(provider_id: str):
    if provider_id == "cloudflare_quick_tunnel":
        return CloudflareQuickTunnelProvider()
    return StaticWebhookUrlProvider()


def run(input_data, context):
    data = input_data or {}
    method = str(data.get("_method") or "GET").upper()
    provider_id = str(data.get("provider") or data.get("provider_id") or "static").strip()
    provider = _provider(provider_id)
    if method == "GET":
        return ok({"providers": ["static", "cloudflare_quick_tunnel"]})
    if method == "POST":
        result = provider.create_url(
            local_url=str(data.get("local_url") or "http://127.0.0.1:8787"),
            route_path=str(data.get("route_path") or "/"),
            ttl_seconds=int(data.get("ttl_seconds") or 0),
            context=context or {},
        )
        if not result.get("ok"):
            return error(str(result.get("error") or "failed to create public URL"), "PUBLIC_URL_FAILED", details=result)
        return ok(result)
    if method == "DELETE":
        return ok(provider.close_url(str(data.get("url_id") or ""), context=context or {}))
    return error("unsupported method", "METHOD_NOT_ALLOWED")
