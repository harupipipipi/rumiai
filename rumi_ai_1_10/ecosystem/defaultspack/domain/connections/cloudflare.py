from __future__ import annotations

import os
from typing import Any, Mapping

from core_runtime.connections.adapter import GenericConnectionAdapter


_ACCOUNT_ID_ENV = ("RUMI_CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID")
_ZONE_ID_ENV = ("RUMI_CLOUDFLARE_ZONE_ID", "CLOUDFLARE_ZONE_ID")
_REQUESTED_CAPABILITIES_ENV = (
    "RUMI_CLOUDFLARE_REQUESTED_CAPABILITIES",
    "RUMI_CLOUDFLARE_OAUTH_REQUESTED_CAPABILITIES",
    "CLOUDFLARE_REQUESTED_CAPABILITIES",
    "CLOUDFLARE_API_TOKEN_REQUESTED_CAPABILITIES",
)


class CloudflareConnectionAdapter(GenericConnectionAdapter):
    def normalize_token_metadata(self, *, provider, credential_bundle, secret_material):  # type: ignore[override]
        metadata = super().normalize_token_metadata(
            provider=provider,
            credential_bundle=credential_bundle,
            secret_material=secret_material,
        )
        credentials = secret_material.get("credentials") if isinstance(secret_material.get("credentials"), Mapping) else {}
        context = secret_material.get("context") if isinstance(secret_material.get("context"), Mapping) else {}
        metadata["provider_id"] = "cloudflare"
        metadata["account_id"] = _first_text(metadata.get("account_id"), context.get("account_id"), _first_env(_ACCOUNT_ID_ENV))
        metadata["zone_id"] = _first_text(metadata.get("zone_id"), context.get("zone_id"), _first_env(_ZONE_ID_ENV))
        if not metadata.get("requested_capabilities"):
            metadata["requested_capabilities"] = _normalize_list(_first_env(_REQUESTED_CAPABILITIES_ENV))
        metadata["account_id_configured"] = bool(metadata.get("account_id"))
        metadata["zone_id_configured"] = bool(metadata.get("zone_id"))

        access_token = _first_text(credentials.get("access_token"), credentials.get("api_token"), credentials.get("token"))
        if access_token and metadata.get("account_id"):
            _attach_account_label(metadata, access_token)
        elif metadata.get("account_id"):
            metadata.setdefault("cloudflare_account_status", "configured")
        else:
            metadata.setdefault("cloudflare_account_status", "missing_account_id")
        metadata["status"] = "connected" if credentials else str(metadata.get("status") or "not_connected")
        return _without_empty(metadata)


def _attach_account_label(metadata: dict[str, Any], access_token: str) -> None:
    try:
        from core_runtime.cloudflare.sdk_client import CloudflareSDKAdapter, cloudflare_sdk_status

        if not cloudflare_sdk_status().get("available"):
            metadata["cloudflare_account_status"] = "sdk_missing"
            return
        account = CloudflareSDKAdapter(
            api_token=access_token,
            account_id=str(metadata.get("account_id") or ""),
        ).get_account()
        label = str(account.get("name") or account.get("display_name") or account.get("id") or "").strip()
        if label:
            metadata["account_label"] = f"Cloudflare: {label}"
        metadata["cloudflare_account_status"] = "verified"
    except Exception as exc:
        metadata["cloudflare_account_status"] = "unverified"
        metadata["cloudflare_account_error"] = _scrub_secret(str(exc), access_token)


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item for item in text.replace(",", " ").split() if item]


def _scrub_secret(message: str, secret: str) -> str:
    return str(message or "").replace(secret, "[redacted]") if secret else str(message or "")


def _without_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in ("", None, [])}
