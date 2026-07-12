from __future__ import annotations

import json
import os
import threading
import time
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from typing import Any


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_registry_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_MCP_REGISTRY_PATH")
    if override:
        return Path(override)
    return _pack_root() / "user_data" / "defaultspack" / "mcp_servers.json"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class McpRegistry:
    """Persistent MVP registry for user-configured MCP servers."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_registry_path()
        self._lock = threading.RLock()

    def list_servers(self) -> list[dict[str, Any]]:
        data = self._read()
        servers = data.get("servers", {})
        if isinstance(servers, list):
            values = servers
        elif isinstance(servers, dict):
            values = list(servers.values())
        else:
            values = []
        return [self._public_server(server) for server in values if isinstance(server, dict)]

    def get_server(self, server_id: str) -> dict[str, Any] | None:
        server_id = str(server_id or "").strip()
        if not server_id:
            return None
        for server in self.list_servers():
            if server_id in {server.get("server_id"), server.get("name")}:
                return server
        return None

    def add_server(self, server: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_server(server)
        data = self._read()
        servers = data.setdefault("servers", {})
        if not isinstance(servers, dict):
            servers = {}
            data["servers"] = servers
        current = servers.get(normalized["server_id"])
        if isinstance(current, dict):
            existing_permissions = (
                current.get("permissions") if isinstance(current.get("permissions"), dict) else {}
            )
            normalized["permissions"] = {
                **existing_permissions,
                **normalized.get("permissions", {}),
            }
            normalized["created_at"] = current.get("created_at") or normalized["created_at"]
        servers[normalized["server_id"]] = normalized
        self._write(data)
        return self._public_server(normalized)

    def delete_server(self, server_id: str) -> bool:
        data = self._read()
        servers = data.get("servers", {})
        if not isinstance(servers, dict):
            return False
        target = str(server_id or "").strip()
        key = None
        for candidate, server in servers.items():
            if target in {
                str(candidate),
                str(server.get("server_id") or ""),
                str(server.get("name") or ""),
            }:
                key = candidate
                break
        if key is None:
            return False
        servers.pop(key, None)
        self._write(data)
        return True

    def mark_connected(
        self,
        server_id: str,
        *,
        status: str = "connected",
        tools: list[Any] | None = None,
        approved: bool = True,
    ) -> dict[str, Any] | None:
        data = self._read()
        servers = data.get("servers", {})
        if not isinstance(servers, dict):
            return None
        target = str(server_id or "").strip()
        for key, server in servers.items():
            if target in {
                str(key),
                str(server.get("server_id") or ""),
                str(server.get("name") or ""),
            }:
                server["status"] = status
                server["connected"] = status == "connected"
                server["updated_at"] = _now_iso()
                if tools is not None:
                    server["tools"] = tools
                permissions = (
                    server.get("permissions") if isinstance(server.get("permissions"), dict) else {}
                )
                permissions["approved"] = bool(approved)
                permissions.setdefault("approved_at", _now_iso())
                server["permissions"] = permissions
                self._write(data)
                return self._public_server(server)
        return None

    def mark_connection_failed(
        self,
        server_id: str,
        *,
        reason: str = "MCP connection failed",
    ) -> dict[str, Any] | None:
        """Persist a recoverable failed state without storing raw process output."""
        data = self._read()
        servers = data.get("servers", {})
        if not isinstance(servers, dict):
            return None
        target = str(server_id or "").strip()
        for key, server in servers.items():
            if target not in {
                str(key),
                str(server.get("server_id") or ""),
                str(server.get("name") or ""),
            }:
                continue
            server["status"] = "failed"
            server["connected"] = False
            server["updated_at"] = _now_iso()
            server["last_error"] = str(reason or "MCP connection failed")
            permissions = (
                server.get("permissions") if isinstance(server.get("permissions"), dict) else {}
            )
            permissions["approved"] = False
            server["permissions"] = permissions
            self._write(data)
            return self._public_server(server)
        return None

    def is_approved(self, server_id: str) -> bool:
        server = self.get_server(server_id)
        permissions = server.get("permissions") if isinstance(server, dict) else {}
        return bool(isinstance(permissions, dict) and permissions.get("approved"))

    @staticmethod
    def public_config(config: Any) -> dict[str, Any]:
        """Return the client-safe representation of an MCP server config."""
        return _public_config(config)

    def _read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.is_file():
                return {"version": 1, "servers": {}}
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {"version": 1, "servers": {}}
        return loaded if isinstance(loaded, dict) else {"version": 1, "servers": {}}

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tmp.replace(self.path)

    def _normalize_server(self, server: dict[str, Any]) -> dict[str, Any]:
        config = dict(server.get("config") or server)
        server_id = str(
            server.get("server_id")
            or config.get("server_id")
            or server.get("name")
            or config.get("name")
            or ""
        ).strip()
        if not server_id:
            raise ValueError("server_id or name is required")
        name = str(server.get("name") or config.get("name") or server_id).strip()
        transport = str(config.get("transport") or server.get("transport") or "stdio").strip()
        if transport not in {"stdio", "sse"}:
            raise ValueError("transport must be 'stdio' or 'sse'")
        clean_config = dict(config)
        clean_config["server_id"] = server_id
        clean_config["name"] = name
        clean_config["transport"] = transport
        permissions = (
            server.get("permissions") if isinstance(server.get("permissions"), dict) else {}
        )
        return {
            "server_id": server_id,
            "name": name,
            "transport": transport,
            "config": clean_config,
            "permissions": {
                "approved": bool(permissions.get("approved")),
                "scopes": list(permissions.get("scopes", []))
                if isinstance(permissions.get("scopes"), list)
                else [],
                "risk": str(permissions.get("risk") or "high"),
            },
            "status": str(server.get("status") or "registered"),
            "connected": bool(server.get("connected")),
            "tools": list(server.get("tools", [])) if isinstance(server.get("tools"), list) else [],
            "created_at": str(server.get("created_at") or _now_iso()),
            "updated_at": _now_iso(),
            "metadata": dict(server.get("metadata") or {})
            if isinstance(server.get("metadata"), dict)
            else {},
        }

    @staticmethod
    def _public_server(server: dict[str, Any]) -> dict[str, Any]:
        return {
            "server_id": server.get("server_id"),
            "name": server.get("name"),
            "server_name": server.get("name"),
            "transport": server.get("transport"),
            "config": _public_config(server.get("config")),
            "permissions": server.get("permissions", {}),
            "status": server.get("status", "registered"),
            "connected": bool(server.get("connected")),
            "tools": server.get("tools", []),
            "created_at": server.get("created_at"),
            "updated_at": server.get("updated_at"),
            "metadata": server.get("metadata", {}),
            "last_error": server.get("last_error"),
        }


def _public_config(value: Any) -> dict[str, Any]:
    config = dict(value) if isinstance(value, dict) else {}
    public = {
        key: config.get(key)
        for key in ("server_id", "name", "transport", "tool_prefix")
        if key in config
    }
    if "command" in config:
        public["command"] = str(config.get("command") or "")
    if isinstance(config.get("args"), list):
        public["args"] = [
            "<redacted>" if _looks_sensitive_argument(str(item)) else str(item)
            for item in config["args"]
        ]
    if "cwd" in config:
        public["cwd"] = str(config.get("cwd") or "")
    if isinstance(config.get("env"), dict):
        public["env"] = {str(key): "<redacted>" for key in config["env"]}
    if isinstance(config.get("headers"), dict):
        public["headers"] = {
            str(key): "<redacted>" for key in config["headers"]
        }
    if "url" in config:
        public["url"] = _public_url(config.get("url"))
    return public


def _looks_sensitive_argument(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in ("api-key", "api_key", "token", "secret", "password", "authorization")
    )


def _public_url(value: Any) -> str:
    try:
        parsed = urlsplit(str(value or ""))
        hostname = parsed.hostname or ""
        netloc = hostname
        if parsed.port is not None:
            netloc = f"{hostname}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "<invalid-url>"
