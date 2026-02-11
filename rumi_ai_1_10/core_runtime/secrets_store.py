"""
secrets_store.py - Secrets 管理

user_data/secrets/ に秘密を保存する。
運用API は list(mask) / set / delete のみ。get（再表示）は絶対に提供しない。
値はログ・監査・例外に絶対出さない。

保存: 1 key 1 file (user_data/secrets/<KEY>.json)
KEY制約: ^[A-Z0-9_]{1,64}$
削除: tombstone (deleted_at を入れ、value は空にする)
journal: user_data/secrets/journal.jsonl (値/長さ/ハッシュは入れない)
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SECRETS_DIR = "user_data/secrets"
KEY_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")


@dataclass
class SecretMeta:
    key: str
    exists: bool
    deleted: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    deleted_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "key": self.key,
            "exists": self.exists,
            "deleted": self.deleted,
        }
        if self.created_at:
            d["created_at"] = self.created_at
        if self.updated_at:
            d["updated_at"] = self.updated_at
        if self.deleted_at:
            d["deleted_at"] = self.deleted_at
        return d


@dataclass
class SecretSetResult:
    success: bool
    key: str = ""
    created: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "key": self.key,
            "created": self.created,
            "error": self.error,
        }


@dataclass
class SecretDeleteResult:
    success: bool
    key: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "key": self.key,
            "error": self.error,
        }


class SecretsStore:
    """
    Secrets 管理

    API:
    - list_keys() -> mask list
    - set_secret(key, value) -> set
    - delete_secret(key) -> tombstone delete
    - has_secret(key) -> exists check（値は返さない）
    - _read_value(key) -> 内部専用（外部APIには絶対公開しない）
    """

    def __init__(self, secrets_dir: Optional[str] = None):
        self._secrets_dir = Path(secrets_dir or SECRETS_DIR)
        self._lock = threading.RLock()
        self._secrets_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def validate_key(key: str) -> Optional[str]:
        if not key:
            return "Key is empty"
        if not KEY_PATTERN.match(key):
            return f"Invalid key: must match ^[A-Z0-9_]{{1,64}}$"
        return None

    def _key_path(self, key: str) -> Path:
        return self._secrets_dir / f"{key}.json"

    def set_secret(
        self,
        key: str,
        value: str,
        actor: str = "api_user",
        reason: str = "",
    ) -> SecretSetResult:
        err = self.validate_key(key)
        if err:
            return SecretSetResult(success=False, key=key, error=err)

        with self._lock:
            path = self._key_path(key)
            created = not path.exists()

            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if existing.get("deleted_at"):
                        created = True
                except Exception:
                    created = True

            now = self._now_ts()
            data = {
                "key": key,
                "value": value,
                "created_at": now if created else self._read_meta_field(key, "created_at", now),
                "updated_at": now,
                "deleted_at": None,
            }

            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                try:
                    os.chmod(path, 0o600)
                except (OSError, AttributeError):
                    pass
            except Exception:
                return SecretSetResult(
                    success=False, key=key,
                    error="Failed to write secret file",
                )

            self._append_journal("set", key, actor, reason)
            self._audit("secret_set", True, {"key": key, "created": created, "actor": actor})
            return SecretSetResult(success=True, key=key, created=created)

    def delete_secret(
        self,
        key: str,
        actor: str = "api_user",
        reason: str = "",
    ) -> SecretDeleteResult:
        err = self.validate_key(key)
        if err:
            return SecretDeleteResult(success=False, key=key, error=err)

        with self._lock:
            path = self._key_path(key)
            if not path.exists():
                return SecretDeleteResult(
                    success=False, key=key, error=f"Secret not found: {key}",
                )

            now = self._now_ts()
            data = {
                "key": key,
                "value": "",
                "created_at": self._read_meta_field(key, "created_at", now),
                "updated_at": now,
                "deleted_at": now,
            }

            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                return SecretDeleteResult(
                    success=False, key=key, error="Failed to write tombstone",
                )

            self._append_journal("deleted", key, actor, reason)
            self._audit("secret_deleted", True, {"key": key, "actor": actor})
            return SecretDeleteResult(success=True, key=key)

    def list_keys(self) -> List[SecretMeta]:
        results = []
        with self._lock:
            if not self._secrets_dir.exists():
                return results
            for f in sorted(self._secrets_dir.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    deleted_at = data.get("deleted_at")
                    results.append(SecretMeta(
                        key=data.get("key", f.stem),
                        exists=not bool(deleted_at),
                        deleted=bool(deleted_at),
                        created_at=data.get("created_at"),
                        updated_at=data.get("updated_at"),
                        deleted_at=deleted_at,
                    ))
                except Exception:
                    continue
        return results

    def has_secret(self, key: str) -> bool:
        if self.validate_key(key):
            return False
        with self._lock:
            path = self._key_path(key)
            if not path.exists():
                return False
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return not bool(data.get("deleted_at"))
            except Exception:
                return False

    def _read_value(self, key: str) -> Optional[str]:
        """内部専用。API からは絶対に呼ばない。"""
        if self.validate_key(key):
            return None
        with self._lock:
            path = self._key_path(key)
            if not path.exists():
                return None
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("deleted_at"):
                    return None
                return data.get("value")
            except Exception:
                return None

    def _read_meta_field(self, key: str, field: str, default: str = "") -> str:
        try:
            path = self._key_path(key)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f).get(field, default)
        except Exception:
            pass
        return default

    def _append_journal(
        self, action: str, key: str, actor: str, reason: str = "",
    ) -> None:
        entry: Dict[str, Any] = {
            "ts": self._now_ts(),
            "action": action,
            "key": key,
            "actor": actor,
        }
        if reason:
            entry["reason"] = reason
        try:
            with open(self._secrets_dir / "journal.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    @staticmethod
    def _audit(event_type: str, success: bool, details: Dict[str, Any]) -> None:
        try:
            from .audit_logger import get_audit_logger
            get_audit_logger().log_system_event(
                event_type=event_type, success=success, details=details,
            )
        except Exception:
            pass


_global_secrets_store: Optional[SecretsStore] = None
_secrets_lock = threading.Lock()


def get_secrets_store() -> SecretsStore:
    global _global_secrets_store
    if _global_secrets_store is None:
        with _secrets_lock:
            if _global_secrets_store is None:
                _global_secrets_store = SecretsStore()
    return _global_secrets_store


def reset_secrets_store(secrets_dir: str = None) -> SecretsStore:
    global _global_secrets_store
    with _secrets_lock:
        _global_secrets_store = SecretsStore(secrets_dir)
    return _global_secrets_store
