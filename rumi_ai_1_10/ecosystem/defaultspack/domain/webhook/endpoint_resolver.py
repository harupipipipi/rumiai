from __future__ import annotations

from typing import Any

from .component_defaults import default_endpoint_id_for_provider
from .endpoint import WebhookEndpoint
from .endpoint_store import WebhookEndpointStore


class ProviderEndpointResolver:
    def __init__(self, store: WebhookEndpointStore | None = None) -> None:
        self.store = store or WebhookEndpointStore()

    def resolve(self, provider: str, input_data: dict[str, Any] | None = None) -> WebhookEndpoint | None:
        payload = input_data if isinstance(input_data, dict) else {}
        provider = str(provider or "").strip().lower()
        endpoint_id = str(payload.get("endpoint_id") or payload.get("_endpoint_id") or "").strip()
        if endpoint_id:
            return self.store.get(endpoint_id)
        default_id = default_endpoint_id_for_provider(provider)
        if default_id:
            endpoint = self.store.get(default_id)
            if endpoint is not None:
                return endpoint
        default_id = f"{provider}-main" if provider else ""
        if default_id:
            endpoint = self.store.get(default_id)
            if endpoint is not None:
                return endpoint
        for candidate in self.store.list_endpoints():
            if str(candidate.get("kind") or "").strip().lower() == provider:
                return self.store.get(str(candidate.get("id") or ""))
        return None
