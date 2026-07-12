from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


VIEWER_BROKER_HELPER_TIMEOUT_SECONDS = 45
VIEWER_BROKER_REQUEST_TIMEOUT_SECONDS = VIEWER_BROKER_HELPER_TIMEOUT_SECONDS + 15


class ViewerBrokerClient:
    def __init__(self, *, url: str = "", token: str = "", connection_path: Path | None = None) -> None:
        self.url = str(url or "").rstrip("/")
        self.token = str(token or "")
        self.connection_path = connection_path

    @classmethod
    def from_environment(cls) -> "ViewerBrokerClient":
        env_url = str(os.environ.get("RUMI_VIEWER_HOST_BROKER_URL") or "").strip()
        env_token = str(os.environ.get("RUMI_VIEWER_HOST_BROKER_TOKEN") or "").strip()
        if env_url and env_token:
            return cls(url=env_url, token=env_token)

        connection_env = str(os.environ.get("RUMI_VIEWER_HOST_BROKER_CONNECTION") or "").strip()
        if connection_env:
            return cls._from_connection_file(Path(connection_env))

        user_data = str(os.environ.get("RUMI_USER_DATA") or "").strip()
        if user_data:
            return cls._from_connection_file(Path(user_data) / "host_broker" / "connection.json")

        return cls()

    @classmethod
    def _from_connection_file(cls, path: Path) -> "ViewerBrokerClient":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return cls(connection_path=path)
        return cls(
            url=str(raw.get("url") or ""),
            token=str(raw.get("token") or ""),
            connection_path=path,
        )

    def available(self) -> bool:
        return bool(self.url and self.token)

    def permissions(self) -> dict[str, Any]:
        return self._request("GET", "/api/host/permissions")

    def execute_intent(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/host/intent/execute", dict(payload or {}))

    def start_stream(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/host/stream/start", dict(payload or {}))

    def stop_stream(self, stream_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request_payload = dict(payload or {})
        request_payload["stream_id"] = _string(stream_id)
        return self._request("POST", "/api/host/stream/stop", request_payload)

    def stream_events(self, stream_id: str) -> dict[str, Any]:
        encoded_stream_id = urllib.parse.quote(_string(stream_id), safe="")
        return self._request("GET", f"/api/host/stream/events/{encoded_stream_id}")

    def run_computer(
        self,
        function_id: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
        artifact_root: Path | None = None,
    ) -> dict[str, Any]:
        payload = {
            "function_id": function_id,
            "profile_id": _context_value(context, "profile_id", "input_profile_id"),
            "pack_id": _context_value(context, "owner_pack", "pack_id", "_source_pack_id") or "defaultspack",
            "conversation_id": _context_value(context, "conversation_id", "conversation_turn_id"),
            "approval_token": _string(args.get("approval_token")),
            "args": dict(args or {}),
        }
        if artifact_root is not None:
            payload["artifact_root"] = str(artifact_root)
        response = self._request("POST", "/api/host/computer/run", payload)
        audit_id = _string(response.get("audit_id"))
        if response.get("ok") is True and isinstance(response.get("result"), dict):
            result = dict(response["result"])
            if audit_id:
                result.setdefault("host_audit_id", audit_id)
            result.setdefault("permission_subject", "Rumi Viewer")
            return result

        error = response.get("error") if isinstance(response, dict) else {}
        message = _string((error or {}).get("message")) or "Viewer broker request failed."
        code = _string((error or {}).get("code")) or "VIEWER_HOST_FAILED"
        if code == "APPROVAL_REQUIRED" and isinstance(response.get("result"), dict):
            result = dict(response["result"])
            result.setdefault("action", function_id)
            result.setdefault("error_code", code)
            if audit_id:
                result.setdefault("host_audit_id", audit_id)
            result.setdefault("permission_subject", "Rumi Viewer")
            return result
        return {
            "action": function_id,
            "is_error": True,
            "reason": message,
            "error_code": code,
            "permission_subject": "Rumi Viewer",
            **({"host_audit_id": audit_id} if audit_id else {}),
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("Rumi Viewer host broker is unavailable.")
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-Rumi-Viewer-Broker-Token": self.token,
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.url}{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=VIEWER_BROKER_REQUEST_TIMEOUT_SECONDS) as response:
                data = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Viewer broker returned HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Viewer broker request failed: {exc.reason}") from exc
        decoded = json.loads(data or "{}")
        return decoded if isinstance(decoded, dict) else {}


def _context_value(context: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(context, dict):
        return ""
    for key in keys:
        value = _string(context.get(key))
        if value:
            return value
    return ""


def _string(value: Any) -> str:
    return str(value or "").strip()
