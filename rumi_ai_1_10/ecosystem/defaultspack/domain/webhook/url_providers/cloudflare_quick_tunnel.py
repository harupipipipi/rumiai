from __future__ import annotations

import shutil
from typing import Any

from domain.webhook.url_provider import WebhookUrlProvider


class CloudflareQuickTunnelProvider(WebhookUrlProvider):
    provider_id = "cloudflare_quick_tunnel"

    def create_url(self, *, local_url: str, route_path: str, ttl_seconds: int = 0, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del ttl_seconds, context
        if not shutil.which("cloudflared"):
            return {
                "ok": False,
                "provider": self.provider_id,
                "error": "cloudflared is not installed",
                "command": "cloudflared tunnel --url " + local_url,
                "route_path": route_path,
            }
        return {
            "ok": False,
            "provider": self.provider_id,
            "error": "starting long-running cloudflared tunnels is not supported in this API call yet",
            "command": "cloudflared tunnel --url " + local_url,
            "route_path": route_path,
        }

    def close_url(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        return {"ok": True, "provider": self.provider_id, "url_id": url_id, "closed": True}

    def status(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        return {"ok": False, "provider": self.provider_id, "url_id": url_id, "error": "no cloudflared process is tracked"}
