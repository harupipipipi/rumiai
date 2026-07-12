from __future__ import annotations

import hashlib
import ipaddress
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .errors import (
    DESTINATION_PROVIDER_UNREACHABLE,
    LOCAL_MODEL_PROVIDER_NOT_PORTABLE,
    NO_ELIGIBLE_FALLBACK_ROUTE,
    PROVIDER_ENDPOINT_SOURCE_ONLY,
    PROVIDER_ROUTE_NOT_FOUND,
)
from .models import ContinuityPreflightResult, ProviderRouteRef, content_hash

try:
    from domain.ai_client.api_key_store import (
        provider_api_metadata,
        provider_key_status,
        provider_named_api_keys,
        read_provider_api_key,
    )
except ModuleNotFoundError:
    from ecosystem.defaultspack.domain.ai_client.api_key_store import (  # type: ignore
        provider_api_metadata,
        provider_key_status,
        provider_named_api_keys,
        read_provider_api_key,
    )


LOCAL_PROVIDER_IDS = {
    "llama_cpp",
    "llamacpp",
    "ollama",
    "lmstudio",
    "vllm",
    "human_operator",
    "stub",
    "rumi",
}

DEFAULT_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "cerebras": "https://api.cerebras.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "moonshotai": "https://api.moonshot.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openai": "https://api.openai.com/v1",
    "openai_compatible": "",
    "openrouter": "https://openrouter.ai/api/v1",
    "perplexity": "https://api.perplexity.ai",
    "together": "https://api.together.xyz/v1",
    "xai": "https://api.x.ai/v1",
}


@dataclass(frozen=True)
class EndpointClassification:
    endpoint_class: str
    portable: bool
    blocked_reason: str | None = None


def classify_endpoint(provider_id: str, base_url: str | None) -> EndpointClassification:
    provider_id = str(provider_id or "").strip()
    if provider_id in LOCAL_PROVIDER_IDS:
        return EndpointClassification("source_only", False, LOCAL_MODEL_PROVIDER_NOT_PORTABLE)
    url = str(base_url or DEFAULT_BASE_URLS.get(provider_id, "") or "").strip()
    if not url:
        return EndpointClassification("public_https", True, None)
    if url.startswith("unix://") or url.startswith("file://"):
        return EndpointClassification("unix_socket", False, PROVIDER_ENDPOINT_SOURCE_ONLY)
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    scheme = (parsed.scheme or "").strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return EndpointClassification("loopback", False, PROVIDER_ENDPOINT_SOURCE_ONLY)
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return EndpointClassification("loopback", False, PROVIDER_ENDPOINT_SOURCE_ONLY)
        if ip.is_private:
            if scheme == "https":
                return EndpointClassification("private_network", True, None)
            return EndpointClassification("plain_http_private", False, DESTINATION_PROVIDER_UNREACHABLE)
    except ValueError:
        pass
    if scheme == "https":
        return EndpointClassification("public_https", True, None)
    if scheme == "http":
        return EndpointClassification("plain_http_public", False, DESTINATION_PROVIDER_UNREACHABLE)
    return EndpointClassification("unknown", False, DESTINATION_PROVIDER_UNREACHABLE)


def _adapter_id(provider_id: str, metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("adapter_id") or "").strip()
    if explicit:
        return explicit
    if provider_id in {"anthropic"}:
        return "anthropic"
    if provider_id in {"google", "gemini"}:
        return "google"
    if provider_id in {"openai"}:
        return "openai"
    return "openai_compatible"


def _route_from_api(provider_id: str, api: dict[str, Any], *, fallback_routes: tuple[str, ...] = ()) -> ProviderRouteRef:
    api_id = str(api.get("api_id") or "legacy").strip() or "legacy"
    metadata = provider_api_metadata(provider_id, api_id)
    base_url = str(metadata.get("base_url") or api.get("base_url") or DEFAULT_BASE_URLS.get(provider_id, "") or "").strip() or None
    allowed_models = tuple(str(item) for item in (metadata.get("allowed_models") or api.get("allowed_models") or []) if str(item or "").strip())
    default_model = str(metadata.get("default_model") or api.get("default_model") or "").strip()
    model_id = default_model or (allowed_models[0] if allowed_models else "*")
    classification = classify_endpoint(provider_id, base_url)
    credential_ref = str(api.get("key") or f"{provider_id}:{api_id}")
    capability_hash = content_hash(
        {
            "provider_id": provider_id,
            "api_id": api_id,
            "allowed_models": allowed_models,
            "adapter_id": _adapter_id(provider_id, metadata),
            "base_url": base_url or "",
        }
    )
    return ProviderRouteRef(
        provider_id=provider_id,
        api_id=api_id,
        model_id=model_id,
        adapter_id=_adapter_id(provider_id, metadata),
        provider_extension_ref=str(metadata.get("provider_extension_ref") or "") or None,
        base_url=base_url,
        auth_scheme=str(metadata.get("auth_scheme") or "bearer"),
        header_profile=str(metadata.get("header_profile") or "") or None,
        allowed_models=allowed_models,
        capability_hash=capability_hash,
        endpoint_class=classification.endpoint_class,
        credential_ref=credential_ref,
        fallback_routes=fallback_routes,
        portable=classification.portable,
        blocked_reason=classification.blocked_reason,
    )


def route_ref_from_dict(payload: dict[str, Any]) -> ProviderRouteRef:
    clean = dict(payload)
    clean.pop("qualified_route", None)
    return ProviderRouteRef(**clean)


class ProviderPortabilityService:
    def list_routes(self) -> list[dict[str, Any]]:
        routes: list[ProviderRouteRef] = []
        for provider in provider_key_status():
            provider_id = str(provider.get("provider_id") or "").strip()
            if not provider_id:
                continue
            apis = provider.get("apis") if isinstance(provider.get("apis"), list) else []
            for api in apis:
                if isinstance(api, dict) and api.get("configured"):
                    routes.append(_route_from_api(provider_id, api))
            if not apis and provider.get("configured"):
                routes.append(
                    _route_from_api(
                        provider_id,
                        {
                            "api_id": "legacy",
                            "key": provider.get("key"),
                            "default_model": "",
                            "allowed_models": [],
                        },
                    )
                )
        route_ids = tuple(route.route_id for route in routes if route.portable)
        return [
            {
                **route.as_dict(),
                "fallback_routes": [item for item in route_ids if item != route.route_id][:3],
            }
            for route in routes
        ]

    def resolve(self, payload: dict[str, Any]) -> ProviderRouteRef:
        route_id = str(payload.get("route_id") or "").strip()
        provider_id = str(payload.get("provider_id") or "").strip()
        api_id = str(payload.get("api_id") or "").strip()
        model_id = str(payload.get("model_id") or "").strip()
        qualified = str(payload.get("provider_route") or payload.get("route") or "").strip()
        if qualified and not (provider_id and api_id and model_id):
            parts = qualified.split("/", 2)
            if len(parts) == 3:
                provider_id, api_id, model_id = parts
        for item in self.list_routes():
            if route_id and str(item.get("route_id") or "") == route_id:
                return route_ref_from_dict(item)
            if provider_id and api_id and str(item.get("provider_id")) == provider_id and str(item.get("api_id")) == api_id:
                route = dict(item)
                if model_id:
                    route["model_id"] = model_id
                return route_ref_from_dict(route)
        if provider_id and api_id:
            metadata = provider_api_metadata(provider_id, api_id)
            api = {
                "api_id": api_id,
                "key": f"{provider_id}:{api_id}",
                "default_model": model_id,
                "allowed_models": metadata.get("allowed_models") or ([model_id] if model_id else []),
                "base_url": metadata.get("base_url"),
            }
            return _route_from_api(provider_id, api)
        raise ContinuityError("Provider route was not found.", PROVIDER_ROUTE_NOT_FOUND, 404)

    def secret_for_route(self, route: ProviderRouteRef) -> str:
        return str(read_provider_api_key(route.provider_id, route.api_id) or "")

    def destination_probe(self, route: ProviderRouteRef, destination: dict[str, Any], *, model_policy: str = "api_only") -> ContinuityPreflightResult:
        checks: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        if model_policy == "api_only" and route.provider_id in LOCAL_PROVIDER_IDS:
            errors.append({"code": LOCAL_MODEL_PROVIDER_NOT_PORTABLE, "message": "Local model providers cannot be handed off under api_only policy."})
        if route.blocked_reason:
            errors.append({"code": route.blocked_reason, "message": f"Endpoint class {route.endpoint_class} is not portable."})
        reachability = set(str(item) for item in destination.get("network_reachability_classes") or [])
        if route.endpoint_class and route.endpoint_class not in {"source_only", "loopback", "unix_socket"}:
            if route.endpoint_class not in reachability and route.endpoint_class != "public_https":
                errors.append({"code": DESTINATION_PROVIDER_UNREACHABLE, "message": f"Destination cannot reach {route.endpoint_class} endpoints."})
            else:
                checks.append({"code": "DESTINATION_ENDPOINT_REACHABLE", "ok": True, "endpoint_class": route.endpoint_class})
        if route.provider_extension_ref:
            installed = {str(item) for item in destination.get("provider_extension_digests") or []}
            if route.provider_extension_ref not in installed:
                errors.append({"code": "PROVIDER_EXTENSION_UNAVAILABLE", "message": "Destination does not have the required provider extension digest."})
        configured = bool(self.secret_for_route(route))
        if not configured:
            errors.append({"code": "CREDENTIAL_UNAVAILABLE", "message": "Provider route credential is not configured."})
        else:
            checks.append({"code": "CREDENTIAL_REFERENCE_CONFIGURED", "ok": True, "credential_ref": route.credential_ref})
        if route.allowed_models and route.model_id not in route.allowed_models:
            errors.append({"code": NO_ELIGIBLE_FALLBACK_ROUTE, "message": "Selected model is outside the named API allowed model list."})
        ok = not errors
        return ContinuityPreflightResult(
            ok=ok,
            route=route.as_dict(),
            destination={key: value for key, value in destination.items() if "private" not in key and "secret" not in key},
            checks=tuple(checks),
            errors=tuple(errors),
        )
