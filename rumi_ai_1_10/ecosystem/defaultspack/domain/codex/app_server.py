from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
import ipaddress
import urllib.error
import urllib.request

from .connection_store import codex_connection_status, read_codex_access_token


_DEFAULT_CONFIG = {
    "enabled": False,
    "base_url": "",
    "websocket_url": "",
    "tool_source_enabled": False,
    "automation_endpoint_enabled": False,
}


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_path(pack_root: Path | None = None) -> Path:
    return (pack_root or _pack_root()) / "user_data" / "settings" / "codex_app_server.json"


def _read_config(pack_root: Path | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(_config_path(pack_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_CONFIG)
    if not isinstance(payload, dict):
        return dict(_DEFAULT_CONFIG)
    return _normalize_config(payload)


def _write_config(payload: dict[str, Any], pack_root: Path | None = None) -> None:
    path = _config_path(pack_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def _normalize_url(value: Any, *, allowed_schemes: set[str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in allowed_schemes or not parsed.netloc:
        return ""
    return text


def _hostname_is_loopback(hostname: str) -> bool:
    host = str(hostname or "").strip().strip("[]").lower()
    if host in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _url_is_loopback(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    return _hostname_is_loopback(parsed.hostname or "")


def _normalize_config(payload: dict[str, Any]) -> dict[str, Any]:
    base_url = _normalize_url(payload.get("base_url"), allowed_schemes={"http", "https"})
    websocket_url = _normalize_url(payload.get("websocket_url"), allowed_schemes={"ws", "wss"})
    return {
        "enabled": _bool(payload.get("enabled")),
        "base_url": base_url,
        "websocket_url": websocket_url,
        "tool_source_enabled": _bool(payload.get("tool_source_enabled")),
        "automation_endpoint_enabled": _bool(payload.get("automation_endpoint_enabled")),
    }


def _non_loopback_websocket_without_auth(config: dict[str, Any], *, pack_root: Path | None = None) -> bool:
    websocket_url = str(config.get("websocket_url") or "").strip()
    if not websocket_url or _url_is_loopback(websocket_url):
        return False
    return not bool(read_codex_access_token(pack_root=pack_root))


def save_codex_app_server_config(payload: dict[str, Any], *, pack_root: Path | None = None) -> dict[str, Any]:
    config = _normalize_config(payload if isinstance(payload, dict) else {})
    if _non_loopback_websocket_without_auth(config, pack_root=pack_root):
        return {
            "success": False,
            "provider_id": "codex",
            "error": "non-loopback websocket requires a saved Codex access token",
            "code": "AUTH_REQUIRED_FOR_NON_LOOPBACK_WEBSOCKET",
        }
    _write_config(config, pack_root)
    return {
        "success": True,
        "provider_id": "codex",
        "app_server": codex_app_server_status(pack_root=pack_root),
    }


def clear_codex_app_server_config(*, pack_root: Path | None = None) -> dict[str, Any]:
    try:
        _config_path(pack_root).unlink()
    except OSError:
        pass
    return {
        "success": True,
        "provider_id": "codex",
        "app_server": codex_app_server_status(pack_root=pack_root),
    }


def codex_app_server_status(*, pack_root: Path | None = None) -> dict[str, Any]:
    config = _read_config(pack_root)
    token_status = codex_connection_status(pack_root=pack_root)
    base_url = str(config.get("base_url") or "")
    websocket_url = str(config.get("websocket_url") or "")
    configured = bool(config.get("enabled") and (base_url or websocket_url))
    auth_required = bool(websocket_url and not _url_is_loopback(websocket_url))
    auth_configured = bool(token_status.get("configured"))
    blocked_reason = (
        "Save Codex access token before using a non-loopback websocket."
        if auth_required and not auth_configured
        else ""
    )
    return {
        "provider_id": "codex",
        "configured": configured,
        "enabled": bool(config.get("enabled")),
        "connection_status": "blocked_auth_required" if blocked_reason else "configured" if configured else "not_configured",
        "status_label": "Auth required" if blocked_reason else "Configured" if configured else "Not configured",
        "blocked_reason": blocked_reason,
        "base_url": base_url,
        "websocket_url": websocket_url,
        "loopback": bool((not base_url or _url_is_loopback(base_url)) and (not websocket_url or _url_is_loopback(websocket_url))),
        "auth_required": auth_required,
        "auth_configured": auth_configured,
        "tool_source": {
            "enabled": bool(config.get("tool_source_enabled")),
            "status": "blocked_auth_required" if blocked_reason else "configured" if config.get("tool_source_enabled") and configured else "disabled",
        },
        "automation_endpoint": {
            "enabled": bool(config.get("automation_endpoint_enabled")),
            "status": "blocked_auth_required" if blocked_reason else "configured" if config.get("automation_endpoint_enabled") and configured else "disabled",
        },
        "probe": {"status": "not_run"},
    }


def codex_app_server_probe(*, pack_root: Path | None = None, timeout: float = 2.0) -> dict[str, Any]:
    status = codex_app_server_status(pack_root=pack_root)
    if status.get("blocked_reason"):
        return {"success": False, "provider_id": "codex", "probe": {"status": "auth_required"}}
    base_url = str(status.get("base_url") or "").rstrip("/")
    if not base_url:
        return {"success": False, "provider_id": "codex", "probe": {"status": "not_configured"}}
    if not status.get("loopback") and not read_codex_access_token(pack_root=pack_root):
        return {"success": False, "provider_id": "codex", "probe": {"status": "auth_required"}}
    token = read_codex_access_token(pack_root=pack_root)
    request = urllib.request.Request(f"{base_url}/status", method="GET")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "success": True,
                "provider_id": "codex",
                "probe": {
                    "status": "ok" if response.status < 400 else "error",
                    "http_status": int(response.status),
                },
            }
    except urllib.error.HTTPError as exc:
        return {
            "success": False,
            "provider_id": "codex",
            "probe": {"status": "http_error", "http_status": int(exc.code)},
        }
    except OSError:
        return {"success": False, "provider_id": "codex", "probe": {"status": "unreachable"}}
