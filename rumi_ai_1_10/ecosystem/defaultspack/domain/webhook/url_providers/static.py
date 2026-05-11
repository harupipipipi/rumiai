from __future__ import annotations

from typing import Any

from domain.webhook.url_provider import WebhookUrlProvider


class StaticWebhookUrlProvider(WebhookUrlProvider):
    provider_id = "static"

    def create_url(self, *, local_url: str, route_path: str, ttl_seconds: int = 0, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del ttl_seconds, context
        return {"ok": True, "provider": self.provider_id, "url_id": "static", "public_url": local_url.rstrip("/") + "/" + route_path.lstrip("/")}

    def close_url(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        return {"ok": True, "provider": self.provider_id, "url_id": url_id, "closed": True}

    def status(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        return {"ok": True, "provider": self.provider_id, "url_id": url_id, "status": "static"}
