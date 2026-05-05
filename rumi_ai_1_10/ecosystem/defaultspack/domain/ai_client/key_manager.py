from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .api_key_store import _get_store, _reset_ai_client, _secrets_dir


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sanitize_key_id(value: Any) -> str:
    raw = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9._-]+", "_", raw).strip("._-")
    return (cleaned or f"key_{int(time.time())}")[:80]


def secret_name_for(key_id: str) -> str:
    normalized = re.sub(r"[^A-Z0-9_]+", "_", key_id.upper()).strip("_")
    return f"DEFAULTSPACK_API_KEY_{normalized}"


def secret_preview(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 8:
        return "***"
    return f"{cleaned[:5]}...{cleaned[-4:]}"


class KeyManager:
    """Named API key metadata with SecretsStore-backed secret values."""

    def __init__(self, root: Path | None = None, *, pack_root: Path | None = None) -> None:
        self.pack_root = Path(pack_root or root or _pack_root())
        override = os.environ.get("RUMI_DEFAULTSPACK_API_KEYS_PATH", "").strip()
        secrets_override = os.environ.get("RUMI_DEFAULTSPACK_SECRETS_DIR", "").strip()
        if override:
            self.path = Path(override)
        elif secrets_override and root is None and pack_root is None:
            self.path = Path(secrets_override).parent / "shared" / "api_keys" / "keys.json"
        else:
            self.path = self.pack_root / "user_data" / "shared" / "api_keys" / "keys.json"

    def list_keys(self) -> list[dict[str, Any]]:
        keys = self._read().get("keys", {})
        return [self.public_view(item) for _, item in sorted(keys.items()) if isinstance(item, dict)]

    def get_key(self, key_id: str) -> dict[str, Any] | None:
        item = self._read().get("keys", {}).get(sanitize_key_id(key_id))
        return self.public_view(item) if isinstance(item, dict) else None

    def create_key(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = {**(payload or {}), **kwargs}
        if payload.get("name") and not payload.get("display_name"):
            payload["display_name"] = payload["name"]
        if payload.get("profile_ids") and not payload.get("allowed_profiles"):
            payload["allowed_profiles"] = payload["profile_ids"]
        if payload.get("agent_ids") and not payload.get("allowed_agents"):
            payload["allowed_agents"] = payload["agent_ids"]
        if payload.get("env_var") and not payload.get("secret_name"):
            payload["secret_name"] = payload["env_var"]
        key_id = sanitize_key_id(payload.get("key_id") or payload.get("id") or payload.get("display_name"))
        provider_id = str(payload.get("provider_id") or "").strip().lower()
        if not provider_id:
            raise ValueError("provider_id is required")
        secret_name = str(payload.get("secret_name") or secret_name_for(key_id))
        value = str(payload.get("api_key") or payload.get("secret") or payload.get("value") or "").strip()
        data = self._read()
        keys = data.setdefault("keys", {})
        item = self._normalize({**payload, "key_id": key_id, "provider_id": provider_id, "secret_name": secret_name})
        item.setdefault("created_at", _now_iso())
        if value:
            result = _get_store(self.pack_root).set_secret(secret_name, value, actor="defaultspack.api_keys", reason=f"set named api key {key_id}")
            if not result.success:
                raise ValueError(result.error or "failed to store secret")
            item["secret_preview"] = secret_preview(value)
        keys[key_id] = item
        data["updated_at"] = _now_iso()
        self._write(data)
        _reset_ai_client()
        return self.public_view(item)

    def update_key(self, key_id: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = {**(payload or {}), **kwargs}
        if payload.get("name") and not payload.get("display_name"):
            payload["display_name"] = payload["name"]
        if payload.get("profile_ids") and not payload.get("allowed_profiles"):
            payload["allowed_profiles"] = payload["profile_ids"]
        if payload.get("agent_ids") and not payload.get("allowed_agents"):
            payload["allowed_agents"] = payload["agent_ids"]
        key_id = sanitize_key_id(key_id)
        data = self._read()
        keys = data.setdefault("keys", {})
        item = keys.get(key_id)
        if not isinstance(item, dict):
            raise ValueError("api key not found")
        for key, value in payload.items():
            if key in {"api_key", "secret", "value"}:
                continue
            if key not in {"key_id", "id"}:
                item[key] = value
        value = str(payload.get("api_key") or payload.get("secret") or payload.get("value") or "").strip()
        if value:
            secret_name = str(item.get("secret_name") or secret_name_for(key_id))
            result = _get_store(self.pack_root).set_secret(secret_name, value, actor="defaultspack.api_keys", reason=f"update named api key {key_id}")
            if not result.success:
                raise ValueError(result.error or "failed to store secret")
            item["secret_name"] = secret_name
            item["secret_preview"] = secret_preview(value)
        item["updated_at"] = _now_iso()
        keys[key_id] = self._normalize(item)
        data["updated_at"] = _now_iso()
        self._write(data)
        _reset_ai_client()
        return self.public_view(keys[key_id])

    def delete_key(self, key_id: str) -> dict[str, Any]:
        key_id = sanitize_key_id(key_id)
        data = self._read()
        item = data.setdefault("keys", {}).pop(key_id, None)
        if isinstance(item, dict) and item.get("secret_name"):
            _get_store(self.pack_root).delete_secret(str(item["secret_name"]), actor="defaultspack.api_keys", reason=f"delete named api key {key_id}")
        data["updated_at"] = _now_iso()
        self._write(data)
        _reset_ai_client()
        return {"key_id": key_id, "deleted": bool(item)}

    def read_secret(self, key_id: str) -> str | None:
        item = self._read().get("keys", {}).get(sanitize_key_id(key_id))
        if not isinstance(item, dict) or not item.get("secret_name"):
            return None
        return _get_store(self.pack_root)._internal_read_value(str(item["secret_name"]), caller_id=f"defaultspack.api_keys:{key_id}")

    def public_view(self, item: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        view = {key: value for key, value in item.items() if key not in {"api_key", "secret", "value"}}
        secret_name = str(view.get("secret_name") or "")
        view["configured"] = bool(secret_name and (_secrets_dir(self.pack_root) / f"{secret_name}.json").exists() and _get_store(self.pack_root).has_secret(secret_name))
        view.setdefault("secret_preview", "")
        return view

    def _normalize(self, item: dict[str, Any]) -> dict[str, Any]:
        key_id = sanitize_key_id(item.get("key_id") or item.get("id"))
        return {
            "key_id": key_id,
            "id": key_id,
            "display_name": str(item.get("display_name") or key_id),
            "name": str(item.get("display_name") or item.get("name") or key_id),
            "provider_id": str(item.get("provider_id") or "").strip().lower(),
            "enabled": item.get("enabled", True) is not False,
            "secret_name": str(item.get("secret_name") or secret_name_for(key_id)),
            "env_var": str(item.get("env_var") or item.get("secret_name") or secret_name_for(key_id)),
            "secret_preview": str(item.get("secret_preview") or ""),
            "allowed_profiles": list(item.get("allowed_profiles") or []),
            "allowed_agents": list(item.get("allowed_agents") or []),
            "allowed_models": list(item.get("allowed_models") or []),
            "profile_ids": list(item.get("allowed_profiles") or item.get("profile_ids") or []),
            "agent_ids": list(item.get("allowed_agents") or item.get("agent_ids") or []),
            "default_for_provider": bool(item.get("default_for_provider", False)),
            "limits": dict(item.get("limits") or {}),
            "conditions": dict(item.get("conditions") or {}),
            "metadata": dict(item.get("metadata") or {}),
            "created_at": item.get("created_at") or _now_iso(),
            "updated_at": item.get("updated_at") or _now_iso(),
        }

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {"schema_version": 1, "keys": {}}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema_version": 1, **value}, ensure_ascii=False, indent=2), encoding="utf-8")
