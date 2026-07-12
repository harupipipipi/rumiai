"""Executable gateway adapters with explicit upstream route ownership."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import urllib.parse
from typing import Any

from ..gateway_policy import gateway_inventory
from .openai_compatible_provider import OpenAICompatibleProvider


class GatewayConfigurationError(ValueError):
    """A gateway route is missing or violates endpoint policy."""


class ConfiguredGatewayProvider(OpenAICompatibleProvider):
    """OpenAI-format gateway that only invokes explicitly configured upstreams."""

    manifest_factory = True

    def __init__(self, *args, configured_routes=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._configured_routes = self._load_routes(configured_routes)

    @staticmethod
    def _load_routes(configured_routes: Any) -> list[dict[str, Any]]:
        raw = configured_routes
        if raw is None:
            encoded = str(os.environ.get("RUMI_GATEWAY_ROUTES_JSON") or "").strip()
            if encoded:
                try:
                    raw = json.loads(encoded)
                except json.JSONDecodeError as exc:
                    raise GatewayConfigurationError("Gateway routes JSON is invalid") from exc
        routes = raw if isinstance(raw, list) else []
        # gateway_inventory performs secret/header rejection and canonical dedupe.
        return [dict(route) for route in routes if isinstance(route, dict)]

    def list_models(self):
        return gateway_inventory(self.provider_id, configured_routes=self._configured_routes)

    def _route(self, model: str) -> dict[str, Any]:
        requested = self._model_id(model)
        for route in self._configured_routes:
            provider = str(route.get("upstream_provider") or "").strip()
            upstream_model = str(route.get("upstream_model") or "").strip()
            if requested in {f"{provider}/{upstream_model}", upstream_model}:
                # Re-run policy validation for the selected route before every invoke.
                gateway_inventory(self.provider_id, configured_routes=[route])
                return route
        raise GatewayConfigurationError(
            f"{self.provider_id}: model is not backed by a configured upstream route"
        )

    def _model_id(self, model: str) -> str:
        value = str(model or "").strip()
        prefix = f"{self.provider_id}/"
        return value[len(prefix) :] if value.startswith(prefix) else value

    def _gateway_model(self, route: dict[str, Any]) -> str:
        provider = str(route["upstream_provider"])
        model = str(route["upstream_model"])
        return f"{provider}/{model}"

    def _headers(self, content_type="application/json"):
        headers = super()._headers(content_type)
        route = getattr(self, "_active_route", None)
        if isinstance(route, dict):
            headers.update(self._route_headers(route))
        return headers

    def _route_headers(self, route: dict[str, Any]) -> dict[str, str]:
        return {}

    def complete(self, model, messages, tools, params):
        route = self._route(model)
        self._active_route = route
        try:
            return super().complete(
                self._gateway_model(route), messages, tools, params
            )
        finally:
            self._active_route = None

    def stream(self, model, messages, tools, params):
        route = self._route(model)
        self._active_route = route
        try:
            yield from super().stream(
                self._gateway_model(route), messages, tools, params
            )
        finally:
            self._active_route = None


class CloudflareAIGatewayProvider(ConfiguredGatewayProvider):
    """Cloudflare AI Gateway OpenAI-compatible `/compat` endpoint."""

    provider_name = "cloudflare-ai-gateway"

    def __init__(self, *args, **kwargs) -> None:
        if not kwargs.get("base_url") and not kwargs.get("default_base_url"):
            configured = str(os.environ.get("CLOUDFLARE_AI_GATEWAY_URL") or "").strip()
            account = str(os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
            gateway = str(os.environ.get("CLOUDFLARE_AI_GATEWAY_ID") or "").strip()
            if configured:
                kwargs["default_base_url"] = configured
            elif account and gateway:
                kwargs["default_base_url"] = (
                    "https://gateway.ai.cloudflare.com/v1/"
                    f"{urllib.parse.quote(account, safe='')}/"
                    f"{urllib.parse.quote(gateway, safe='')}/compat"
                )
        super().__init__(*args, **kwargs)

    def _route_headers(self, route: dict[str, Any]) -> dict[str, str]:
        return {"cf-aig-authorization": f"Bearer {self._api_key}"}


class PortkeyGatewayProvider(ConfiguredGatewayProvider):
    """Portkey Universal API with explicit Model Catalog provider routing."""

    provider_name = "portkey-ai-gateway"

    def _gateway_model(self, route: dict[str, Any]) -> str:
        provider = str(route["upstream_provider"]).lstrip("@")
        model = str(route["upstream_model"])
        return f"@{provider}/{model}"

    def _route_headers(self, route: dict[str, Any]) -> dict[str, str]:
        return {"x-portkey-api-key": self._api_key}


class HeliconeGatewayProvider(ConfiguredGatewayProvider):
    """Helicone managed gateway or approved HTTPS target pass-through."""

    provider_name = "helicone-gateway"

    def _route_headers(self, route: dict[str, Any]) -> dict[str, str]:
        headers = {"Helicone-Auth": f"Bearer {self._api_key}"}
        target = str(route.get("target_url") or "").strip()
        if target:
            headers["Helicone-Target-Url"] = _validated_public_https_target(target)
            headers["Helicone-Target-Provider"] = str(route["upstream_provider"])
        return headers


def _validated_public_https_target(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise GatewayConfigurationError("Helicone target must be a credential-free HTTPS URL")
    if parsed.port not in {None, 443}:
        raise GatewayConfigurationError("Helicone target must use HTTPS port 443")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".local"):
        raise GatewayConfigurationError("Helicone target cannot use a local host")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443)}
    except OSError as exc:
        raise GatewayConfigurationError("Helicone target could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise GatewayConfigurationError("Helicone target must resolve only to public addresses")
    return urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path.rstrip("/"), "", ""))
