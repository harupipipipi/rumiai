"""
secrets_store.py - Secrets 永続ストア

user_data/secrets/ に秘密情報を保存し、getを提供しない。
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


SECRET_KEY_REGEX = re.compile(r"^[A-Z0-9_]{1,64}$")


@dataclass
class SecretRecord:
    key: str
    value: str
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecretRecord":
        return cls(
            key=data.get("key", ""),
            value=data.get("value", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            deleted_at=data.get("deleted_at"),
        )


class SecretsStore:
    DEFAULT_SECRETS_DIR = "user_data/secrets"
    JOURNAL_FILE = "user_data/secrets/journal.jsonl"

    def __init__(self, secrets_dir: str = None):
        self._secrets_dir = Path(secrets_dir) if secrets_dir else Path(self.DEFAULT_SECRETS_DIR)
        self._journal_path = Path(self.JOURNAL_FILE)
        self._lock = threading.RLock()
        self._ensure_dir()

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _ensure_dir(self) -> None:
        self._secrets_dir.mkdir(parents=True, exist_ok=True)
        self._journal_path.parent.mkdir(parents=True, exist_ok=True)

    def _validate_key(self, key: str) -> Optional[str]:
        if not isinstance(key, str) or not key:
            return "missing_key"
        if not SECRET_KEY_REGEX.match(key):
            return "invalid_key"
        return None

    def _secret_file(self, key: str) -> Path:
        return self._secrets_dir / f"{key}.json"

    def _load_record(self, key: str) -> Optional[SecretRecord]:
        file_path = self._secret_file(key)
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return SecretRecord.from_dict(data)
        except Exception:
            return None

    def list_secrets(self) -> List[Dict[str, Any]]:
        with self._lock:
            results: List[Dict[str, Any]] = []
            if not self._secrets_dir.exists():
                return results
            for file_path in sorted(self._secrets_dir.glob("*.json")):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    record = SecretRecord.from_dict(data)
                    if record.deleted_at:
                        continue
                    results.append({
                        "key": record.key,
                        "masked_value": "****",
                        "updated_at": record.updated_at,
                    })
                except Exception:
                    continue
            return results

    def set_secret(self, key: str, value: str, actor: str = "system", reason: str = "") -> Dict[str, Any]:
        validation_error = self._validate_key(key)
        if validation_error:
            return {"success": False, "error": validation_error}

        if not isinstance(value, str):
            return {"success": False, "error": "invalid_value"}

        with self._lock:
            now = self._now_ts()
            existing = self._load_record(key)
            created_at = existing.created_at if existing else now
            record = SecretRecord(
                key=key,
                value=value,
                created_at=created_at,
                updated_at=now,
                deleted_at=None,
            )
            file_path = self._secret_file(key)
            file_path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            self._apply_secure_permissions(file_path)
            self._append_journal("set", key, actor, reason)
            self._audit_secret_event("secret_set", key, actor)
            return {"success": True, "key": key, "updated_at": now}

    def delete_secret(self, key: str, actor: str = "system", reason: str = "") -> Dict[str, Any]:
        validation_error = self._validate_key(key)
        if validation_error:
            return {"success": False, "error": validation_error}

        with self._lock:
            now = self._now_ts()
            existing = self._load_record(key)
            if existing is None:
                return {"success": False, "error": "not_found"}

            record = SecretRecord(
                key=key,
                value="",
                created_at=existing.created_at or now,
                updated_at=now,
                deleted_at=now,
            )
            file_path = self._secret_file(key)
            file_path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            self._apply_secure_permissions(file_path)
            self._append_journal("delete", key, actor, reason)
            self._audit_secret_event("secret_deleted", key, actor)
            return {"success": True, "key": key, "deleted_at": now}

    def _append_journal(self, action: str, key: str, actor: str, reason: str) -> None:
        entry = {
            "ts": self._now_ts(),
            "action": action,
            "key": key,
            "actor": actor,
        }
        if reason:
            entry["reason"] = reason
        try:
            with open(self._journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _apply_secure_permissions(self, file_path: Path) -> None:
        try:
            os.chmod(file_path, 0o600)
        except (OSError, AttributeError) as e:
            self._audit_permission_warning(file_path, str(e))

    def _audit_secret_event(self, event_type: str, key: str, actor: str) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_security_event(
                event_type=event_type,
                severity="info",
                description=f"Secret event: {event_type}",
                details={
                    "key": key,
                    "actor": actor,
                },
            )
        except Exception:
            pass

    def _audit_permission_warning(self, file_path: Path, error: str) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_security_event(
                event_type="secret_chmod_failed",
                severity="warning",
                description="Failed to set secret file permissions",
                details={
                    "file": str(file_path),
                    "error": error,
                },
            )
        except Exception:
            pass


_global_secrets_store: Optional[SecretsStore] = None
_store_lock = threading.Lock()


def get_secrets_store() -> SecretsStore:
    global _global_secrets_store
    if _global_secrets_store is None:
        with _store_lock:
            if _global_secrets_store is None:
                _global_secrets_store = SecretsStore()
    return _global_secrets_store


def reset_secrets_store(secrets_dir: str = None) -> SecretsStore:
    global _global_secrets_store
    with _store_lock:
        _global_secrets_store = SecretsStore(secrets_dir)
    return _global_secrets_store
