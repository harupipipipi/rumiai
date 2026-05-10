from __future__ import annotations

from typing import Any


class WebhookUrlProvider:
    provider_id = "base"

    def create_url(self, *, local_url: str, route_path: str, ttl_seconds: int = 0, context: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def close_url(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def status(self, url_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError
