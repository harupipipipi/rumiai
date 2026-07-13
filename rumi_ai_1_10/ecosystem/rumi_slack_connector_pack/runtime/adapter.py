"""Slack signature verification, normalization, and bounded delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

AUTHORITY = "rumi.service.host.authorize.v1"
CREDENTIAL = "rumi.service.credential.resolve.v1"
SERVICE_PACK_ID = "rumi_slack_connector_pack"
ADAPTER_ID = "slack"
_ENDPOINT = "https://slack.com/api/chat.postMessage"


class SlackConnector:
    """Own only Slack protocol verification and delivery."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def invoke(self, name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Invoke Slack inbound or outbound protocol handling."""

        if name == "verify_normalize":
            return self._verify(payload)
        if name == "deliver":
            return self._deliver(payload)
        raise ValueError(f"unknown Slack connector operation: {name}")

    def _verify(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        connector = _connector(payload)
        headers = _headers(payload.get("headers"))
        body = str(payload.get("body") or "")
        timestamp = int(headers.get("x-slack-request-timestamp") or 0)
        if abs(int(time.time()) - timestamp) > 300:
            raise PermissionError("Slack request timestamp is outside replay window")
        secret = self._secret(connector, "connector.inbound.verify", "signing_secret")
        expected = "v0=" + hmac.new(
            secret.encode("utf-8"),
            f"v0:{timestamp}:{body}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        supplied = headers.get("x-slack-signature", "")
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise PermissionError("Slack signature is invalid")
        value = json.loads(body)
        if not isinstance(value, Mapping):
            raise ValueError("Slack event must be an object")
        event = value.get("event") if isinstance(value.get("event"), Mapping) else value
        event_id = str(value.get("event_id") or value.get("trigger_id") or "").strip()
        if not event_id:
            raise ValueError("Slack event ID is required")
        return {
            "event_id": event_id,
            "type": str(event.get("type") or value.get("type") or "event")[:120],
            "actor_id": str(event.get("user") or event.get("bot_id") or "")[:255],
            "channel_id": str(event.get("channel") or "")[:255],
            "thread_id": str(event.get("thread_ts") or event.get("ts") or "")[:255],
            "text": str(event.get("text") or "")[:40_000],
            "team_id": str(value.get("team_id") or "")[:255],
        }

    def _deliver(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        arguments = _delivery_arguments(payload)
        self._redeem(payload, arguments)
        connector = arguments["connector"]
        token = self._secret(connector, "connector.outbound.deliver", "bot_token")
        message = arguments["message"]
        channel = str(message.get("channel_id") or message.get("channel") or "")
        text = str(message.get("text") or "")
        if not channel or not text:
            raise ValueError("Slack channel_id and text are required")
        body: dict[str, Any] = {"channel": channel, "text": text[:40_000]}
        thread_ts = str(message.get("thread_id") or message.get("thread_ts") or "")
        if thread_ts:
            body["thread_ts"] = thread_ts
        request = urllib.request.Request(
            _ENDPOINT,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                content = response.read(64 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            return {"status": "failed", "http_status": int(exc.code)}
        if len(content) > 64 * 1024:
            raise RuntimeError("Slack response exceeds size limit")
        parsed = json.loads(content or b"{}")
        succeeded = isinstance(parsed, Mapping) and parsed.get("ok") is True
        return {
            "status": "delivered" if succeeded else "failed",
            "http_status": int(response.status),
            "provider_error": "" if succeeded else str(parsed.get("error") or "unknown_error"),
        }

    def _secret(
        self,
        connector: Mapping[str, Any],
        scope: str,
        key: str,
    ) -> str:
        resolved = self.client.invoke(
            CREDENTIAL,
            "resolve",
            {
                "handle": str(connector.get("credential_ref") or ""),
                "provider_instance_id": ADAPTER_ID,
                "scope": scope,
            },
        )
        material = resolved.get("secret_material")
        if not isinstance(material, Mapping) or not str(material.get(key) or ""):
            raise PermissionError(f"Slack credential lacks {key}")
        return str(material[key])

    def _redeem(
        self,
        payload: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> None:
        result = self.client.invoke(
            AUTHORITY,
            "redeem",
            {
                "receipt": str(payload.get("authority_receipt") or ""),
                "service_pack_id": SERVICE_PACK_ID,
                "operation": "connector.adapter.deliver",
                "authority": "connector.delivery.execute",
                "caller_id": str(payload.get("caller_id") or ""),
                "caller_pack_id": str(payload.get("caller_pack_id") or ""),
                "caller_function_id": str(payload.get("caller_function_id") or ""),
                "profile_id": str(payload.get("profile_id") or "default"),
                "workspace_id": "",
                "session_id": str(payload.get("session_id") or ""),
                "arguments": dict(arguments),
            },
        )
        if not result.get("authorized"):
            raise PermissionError(str(result.get("reason") or "Slack delivery denied"))


def create_connector_adapter(client: Any) -> Callable[[str, Mapping[str, Any]], Any]:
    """Create the Slack connector adapter."""

    adapter = SlackConnector(client)

    def operation(name: str, payload: Mapping[str, Any]) -> Any:
        return adapter.invoke(name, payload)

    return operation


def _delivery_arguments(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "connector": dict(_connector(payload)),
        "registry_revision": max(0, int(payload.get("registry_revision") or 0)),
        "delivery_id": str(payload.get("delivery_id") or ""),
        "message": dict(_mapping(payload.get("message"))),
    }


def _connector(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("connector")
    if not isinstance(value, Mapping) or value.get("adapter_id") != ADAPTER_ID:
        raise PermissionError("connector is not bound to Slack adapter")
    return value


def _headers(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key).casefold(): str(item) for key, item in value.items()}


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("object payload is required")
    return value
