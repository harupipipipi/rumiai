from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .endpoint import WebhookEndpoint


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_endpoint_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe = dict(payload)
    kind = str(safe.get("kind") or "generic").strip() or "generic"

    if "enabled" not in safe:
        safe["enabled"] = False

    security = safe.get("security")
    if not isinstance(security, dict) or not security:
        if kind in {"line", "discord", "slack"}:
            safe["security"] = {"mode": "provider_signature"}
        else:
            safe["security"] = {
                "mode": "shared_secret",
                "header": "x-rumi-webhook-token",
            }

    return safe


class WebhookEndpointStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()
        self._data = self._load()

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_WEBHOOK_ENDPOINTS_PATH", "").strip()
        if override:
            return Path(override)
        return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "webhooks" / "endpoints.json"

    def list_endpoints(self) -> list[dict[str, Any]]:
        return [endpoint.as_dict() for endpoint in self._endpoints().values()]

    def get(self, endpoint_id: str) -> WebhookEndpoint | None:
        return self._endpoints().get(str(endpoint_id or "").strip())

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = _safe_endpoint_payload(payload)
        endpoint_id = str(payload.get("id") or "").strip() or self._make_id(str(payload.get("kind") or "webhook"))
        endpoint = WebhookEndpoint.from_dict({**payload, "id": endpoint_id})
        endpoints = self._endpoints()
        existed = endpoint_id in endpoints
        endpoints[endpoint_id] = endpoint
        self._data["endpoints"] = {key: item.as_dict(redact=False) for key, item in endpoints.items()}
        self._save()
        return {"endpoint": endpoint.as_dict(), "created": not existed}

    def delete(self, endpoint_id: str) -> dict[str, Any]:
        endpoints = self._endpoints()
        existed = str(endpoint_id or "").strip() in endpoints
        endpoints.pop(str(endpoint_id or "").strip(), None)
        self._data["endpoints"] = {key: item.as_dict(redact=False) for key, item in endpoints.items()}
        self._save()
        return {"deleted": existed, "webhook_id": endpoint_id}

    def _endpoints(self) -> dict[str, WebhookEndpoint]:
        raw = self._data.setdefault("endpoints", {})
        if not isinstance(raw, dict):
            raw = {}
            self._data["endpoints"] = raw
        endpoints = {key: WebhookEndpoint.from_dict(value) for key, value in raw.items() if isinstance(value, dict)}
        if not endpoints:
            for endpoint in self._default_endpoints():
                endpoints[endpoint.id] = endpoint
        return endpoints

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 1)
        data.setdefault("endpoints", {})
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_ms()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _make_id(kind: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", str(kind or "webhook").lower()).strip("-") or "webhook"
        return f"{slug}-{int(time.time() * 1000)}"

    @staticmethod
    def _default_endpoints() -> list[WebhookEndpoint]:
        return [
            WebhookEndpoint(
                id="line-main",
                kind="line",
                input_profile_id="line.default",
                audience_policy_id="line.production",
                response_profile_id="line.default",
                security={"mode": "provider_signature"},
                conversation={"strategy": "external_key", "model": "google/gemini-2.5-pro"},
                enabled=False,
            ),
            WebhookEndpoint(
                id="discord-main",
                kind="discord",
                input_profile_id="discord.default",
                audience_policy_id="discord.production",
                response_profile_id="discord.bot_channel",
                security={"mode": "provider_signature"},
                conversation={"strategy": "external_key", "model": "google/gemini-2.5-pro"},
                enabled=False,
            ),
            WebhookEndpoint(
                id="slack-main",
                kind="slack",
                input_profile_id="slack.default",
                audience_policy_id="slack.production",
                response_profile_id="slack.default",
                security={"mode": "provider_signature"},
                conversation={"strategy": "external_key", "model": "google/gemini-2.5-pro"},
                enabled=False,
            ),
            WebhookEndpoint(
                id="test-webhook",
                kind="generic",
                input_profile_id="generic.webhook.default",
                security={"mode": "shared_secret", "header": "x-rumi-webhook-token"},
                response={"mode": "json"},
                enabled=False,
            ),
        ]
