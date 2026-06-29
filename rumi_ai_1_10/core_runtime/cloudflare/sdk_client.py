from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
from typing import Any


@dataclass(frozen=True)
class CloudflareSDKStatus:
    available: bool
    status: str
    package: str = "cloudflare"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "status": self.status,
            "package": self.package,
            "detail": self.detail,
        }


def cloudflare_sdk_status() -> dict[str, Any]:
    if importlib.util.find_spec("cloudflare") is None:
        return CloudflareSDKStatus(
            available=False,
            status="sdk_missing",
            detail="Install the official Cloudflare Python SDK to enable provisioning.",
        ).to_dict()
    return CloudflareSDKStatus(
        available=True,
        status="ready",
        detail="Cloudflare Python SDK is importable.",
    ).to_dict()


class CloudflareSDKAdapter:
    def __init__(self, *, api_token: str | None = None, account_id: str | None = None) -> None:
        self._api_token = str(api_token or "").strip()
        self._account_id = str(account_id or "").strip()

    def status(self) -> dict[str, Any]:
        status = cloudflare_sdk_status()
        return {
            **status,
            "account_configured": bool(self._account_id),
            "token_configured": bool(self._api_token),
        }

    def client(self) -> Any:
        status = cloudflare_sdk_status()
        if not status.get("available"):
            raise RuntimeError(str(status.get("status") or "sdk_missing"))
        module = importlib.import_module("cloudflare")
        client_factory = getattr(module, "Cloudflare", None)
        if not callable(client_factory):
            raise RuntimeError("sdk_invalid")
        kwargs: dict[str, str] = {}
        if self._api_token:
            kwargs["api_token"] = self._api_token
        return client_factory(**kwargs)
