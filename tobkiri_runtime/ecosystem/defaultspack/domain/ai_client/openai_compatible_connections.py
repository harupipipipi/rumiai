from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import uuid


_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_AUTH_MODES = {"none", "bearer", "api_key_header", "basic"}


def connections_path(pack_root: Path | None = None) -> Path:
    root = pack_root or Path(__file__).resolve().parents[3]
    return root / "user_data" / "shared" / "openai_compatible_connections.json"


def list_connections(*, pack_root: Path | None = None) -> list[dict[str, Any]]:
    payload = _read(pack_root)
    return [deepcopy(payload[key]) for key in sorted(payload)]


def get_connection(connection_id: str, *, pack_root: Path | None = None) -> dict[str, Any] | None:
    value = _read(pack_root).get(_normalize_id(connection_id))
    return deepcopy(value) if value else None


def save_connection(definition: dict[str, Any], *, pack_root: Path | None = None) -> dict[str, Any]:
    raw_id = str(definition.get("connection_id") or "").strip().lower()
    connection_id = _normalize_id(raw_id) if raw_id else f"connection-{uuid.uuid4().hex[:12]}"
    base_url = _http_url(definition.get("base_url"), field="base_url")
    auth_mode = str(definition.get("auth_mode") or "none").strip().lower()
    if auth_mode not in _AUTH_MODES:
        raise ValueError(f"Unsupported auth mode: {auth_mode}")
    model_list = definition.get("model_list") if isinstance(definition.get("model_list"), dict) else {}
    manual_models = []
    for item in definition.get("manual_models", []):
        if isinstance(item, str) and item.strip() and item.strip() not in manual_models:
            manual_models.append(item.strip())
        elif isinstance(item, dict) and str(item.get("id") or "").strip():
            manual_models.append({
                "id": str(item["id"]).strip(),
                "type": str(item.get("type") or "unknown").strip().lower(),
                "capabilities": dict(item.get("capabilities") or {}),
            })
    record = {
        "schema_version": 1,
        "connection_id": connection_id,
        "label": str(definition.get("label") or connection_id).strip(),
        "base_url": base_url,
        "auth_mode": auth_mode,
        "auth_header": str(definition.get("auth_header") or "X-API-Key").strip(),
        "api_key_env": str(definition.get("api_key_env") or "").strip(),
        "username_env": str(definition.get("username_env") or "").strip(),
        "model_list": {
            "enabled": bool(model_list.get("enabled")),
            "url": _optional_http_url(model_list.get("url")),
            "path": str(model_list.get("path") or "/models").strip(),
            "items_path": str(model_list.get("items_path") or "data").strip(),
            "next_path": str(model_list.get("next_path") or "next").strip(),
            "cursor_param": str(model_list.get("cursor_param") or "cursor").strip(),
            "max_pages": max(1, min(100, int(model_list.get("max_pages") or 20))),
        },
        "manual_models": manual_models,
    }
    # Only environment-variable references are persisted; secret values are rejected.
    forbidden = {"api_key", "token", "password", "authorization", "headers"}
    if forbidden.intersection({str(key).lower() for key in definition}):
        raise ValueError("Connection definitions must not contain secret values or headers")
    records = _read(pack_root)
    records[connection_id] = record
    _write(records, pack_root)
    return deepcopy(record)


def delete_connection(connection_id: str, *, pack_root: Path | None = None) -> bool:
    records = _read(pack_root)
    removed = records.pop(_normalize_id(connection_id), None) is not None
    if removed:
        _write(records, pack_root)
    return removed


def resolve_connection_secret(connection: dict[str, Any]) -> tuple[str, str]:
    key = os.environ.get(str(connection.get("api_key_env") or ""), "") if connection.get("api_key_env") else ""
    username = os.environ.get(str(connection.get("username_env") or ""), "") if connection.get("username_env") else ""
    return str(key), str(username)


def _normalize_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not _ID.fullmatch(text):
        raise ValueError("connection_id must match [a-z0-9][a-z0-9_-]{0,63}")
    return text


def _http_url(value: Any, *, field: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text.startswith(("http://", "https://")):
        raise ValueError(f"{field} must be an HTTP(S) URL")
    return text


def _optional_http_url(value: Any) -> str:
    return _http_url(value, field="model_list.url") if str(value or "").strip() else ""


def _read(pack_root: Path | None) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(connections_path(pack_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    records = payload.get("connections") if isinstance(payload, dict) else None
    return {str(key): dict(value) for key, value in records.items() if isinstance(value, dict)} if isinstance(records, dict) else {}


def _write(records: dict[str, dict[str, Any]], pack_root: Path | None) -> None:
    path = connections_path(pack_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"schema_version": 1, "connections": records}, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
