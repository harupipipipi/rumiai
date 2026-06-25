from __future__ import annotations

import os

from blocks._common import error, ok
from domain.webhook.url_providers.cloudflare_pages_mobile import CloudflarePagesMobileProvider
from domain.webhook.url_providers.cloudflare_quick_tunnel import CloudflareQuickTunnelProvider
from domain.webhook.url_providers.static import StaticWebhookUrlProvider


def _provider(provider_id: str):
    if provider_id == "cloudflare_pages_mobile":
        return CloudflarePagesMobileProvider()
    if provider_id == "cloudflare_quick_tunnel":
        return CloudflareQuickTunnelProvider()
    return StaticWebhookUrlProvider()


def _default_local_url() -> str:
    host = os.environ.get("DEFAULTS_HTTP_HOST") or "127.0.0.1"
    port = os.environ.get("DEFAULTS_HTTP_PORT") or "8766"
    return f"http://{host}:{port}"


def run(input_data, context):
    data = input_data or {}
    method = str(data.get("_method") or "GET").upper()
    provider_id = str(data.get("provider") or data.get("provider_id") or "static").strip()
    provider = _provider(provider_id)
    if method == "GET":
        return ok(
            {
                "providers": [
                    {"provider_id": "cloudflare_pages_mobile", "label": "Cloudflare Pages Mobile", "temporary": False},
                    {"provider_id": "cloudflare_quick_tunnel", "label": "Cloudflare Quick Tunnel", "temporary": True},
                    {"provider_id": "static", "label": "Static URL", "temporary": False},
                ],
                "default_local_url": _default_local_url(),
            }
        )
    if method == "POST":
        result = provider.create_url(
            local_url=str(data.get("local_url") or _default_local_url()),
            route_path=str(data.get("route_path") or "/"),
            ttl_seconds=int(data.get("ttl_seconds") or 0),
            context={**(context or {}), "request_data": data},
        )
        return ok(result)
    if method == "DELETE":
        return ok(provider.close_url(str(data.get("url_id") or ""), context=context or {}))
    return error("unsupported method", "METHOD_NOT_ALLOWED")
