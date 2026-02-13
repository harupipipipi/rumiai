"""
secrets_store.py - Secrets 管理（at-rest 暗号化対応）

user_data/secrets/ に秘密を暗号化して保存する。
運用API は list(mask) / set / delete のみ。get（再表示）は絶対に提供しない。
値はログ・監査・例外に絶対出さない。

保存: 1 key 1 file (user_data/secrets/<KEY>.json)
KEY制約: ^[A-Z0-9_]{1,64}$
削除: tombstone (deleted_at を入れ、value は空にする)
journal: user_data/secrets/journal.jsonl (値/長さ/ハッシュは入れない)

暗号化:
- Fernet (cryptography パッケージ) が利用可能な場合に使用
- 利用不可の場合は base64 エンコード + 警告ログ（フォールバック）
- 暗号化キー: 環境変数 RUMI_SECRETS_KEY → user_data/.secrets_key → 自動生成
- 後方互換性: 平文データ読み込み時に自動暗号化マイグレーション
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

SECRETS_DIR = "user_data/secrets"
KEY_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")
SECRETS_KEY_FILE = "user_data/.secrets_key"

# Fernet トークンは常に "gAAAAA" で始まる
_FERNET_PREFIX = "gAAAAA"
# base64 フォールバックのプレフィックス
_B64_PREFIX = "b64:"


# ------------------------------------------------------------------
# 暗号化バックエンド
# ------------------------------------------------------------------

class _CryptoBackend:
    """Fernet / base64 フォールバックを抽象化する暗号化バックエンド"""

    def __init__(self) -> None:
        self._fernet = None
        self._use_fernet = False
        self._initialized = False
        self._init_lock = threading.Lock()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self._setup()
            self._initialized = True

    def _setup(self) -> None:
        key_bytes = self._load_or_generate_key()

        try:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(key_bytes)
            self._use_fernet = True
            logger.info("Secrets encryption: Fernet (cryptography) enabled.")
        except ImportError:
            self._use_fernet = False
            logger.warning(
                "cryptography package not installed. Secrets will use base64 "
                "encoding as fallback. Install cryptography for real encryption: "
                "pip install 'cryptography>=41.0.0'"
            )
        except Exception as e:
            self._use_fernet = False
            logger.warning(
                "Failed to initialize Fernet encryption (%s). "
                "Falling back to base64 encoding.", e
            )

    def _load_or_generate_key(self) -> bytes:
        """暗号化キーをロード、なければ生成して保存"""
        # 1. 環境変数から取得
        env_key = os.environ.get("RUMI_SECRETS_KEY")
        if env_key:
            logger.debug("Using encryption key from RUMI_SECRETS_KEY env var.")
            return env_key.encode("utf-8")

        # 2. ファイルから取得
        key_path = Path(SECRETS_KEY_FILE)
        if key_path.exists():
            try:
                key_data = key_path.read_text(encoding="utf-8").strip()
                if key_data:
                    logger.debug("Using encryption key from %s.", SECRETS_KEY_FILE)
                    return key_data.encode("utf-8")
            except Exception as e:
                logger.warning("Failed to read key file %s: %s", SECRETS_KEY_FILE, e)

        # 3. 自動生成
        try:
            from cryptography.fernet import Fernet
            new_key = Fernet.generate_key()
        except ImportError:
            # cryptography がない場合でも base64 フォールバック用のキーを生成
            import secrets as _secrets_mod
            new_key = base64.urlsafe_b64encode(_secrets_mod.token_bytes(32))

        # ファイルに保存 (atomic write)
        try:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(key_path.parent), prefix=".secrets_key_tmp_"
            )
            try:
                os.write(fd, new_key if isinstance(new_key, bytes) else new_key.encode("utf-8"))
                os.close(fd)
                fd = -1
                os.replace(tmp_path, str(key_path))
                try:
                    os.chmod(str(key_path), 0o600)
                except (OSError, AttributeError):
                    pass
                logger.info("Generated new encryption key → %s", SECRETS_KEY_FILE)
            except Exception:
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.warning("Failed to save key to %s: %s", SECRETS_KEY_FILE, e)

        return new_key if isinstance(new_key, bytes) else new_key.encode("utf-8")

    def encrypt(self, plaintext: str) -> str:
        """平文を暗号化（またはエンコード）して文字列を返す"""
        self._ensure_initialized()
        if self._use_fernet and self._fernet:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        # base64 フォールバック
        encoded = base64.urlsafe_b64encode(plaintext.encode("utf-8")).decode("utf-8")
        return f"{_B64_PREFIX}{encoded}"

    def decrypt(self, ciphertext: str) -> str:
        """暗号文（またはエンコード済み文字列）を復号して平文を返す"""
        self._ensure_initialized()
        if ciphertext.startswith(_FERNET_PREFIX):
            if self._use_fernet and self._fernet:
                return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
            raise ValueError(
                "Fernet-encrypted secret found but cryptography package is not "
                "available. Install cryptography to decrypt."
            )
        if ciphertext.startswith(_B64_PREFIX):
            encoded = ciphertext[len(_B64_PREFIX):]
            return base64.urlsafe_b64decode(encoded.encode("utf-8")).decode("utf-8")
        # 平文と判断 — そのまま返す
        return ciphertext

    def is_encrypted(self, value: str) -> bool:
        """値が暗号化/エンコード済みかどうか判定"""
        if not isinstance(value, str):
            return False
        return value.startswith(_FERNET_PREFIX) or value.startswith(_B64_PREFIX)


# グローバルバックエンドインスタンス
_crypto = _CryptoBackend()


# ------------------------------------------------------------------
# データクラス（公開API互換 — 変更なし）
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Atomic write ヘルパー
# ------------------------------------------------------------------

def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """JSON データを atomic に書き込む（tempfile → os.replace）"""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.stem}_tmp_", suffix=".json"
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = -1
        os.replace(tmp_path, str(path))
        try:
            os.chmod(str(path), 0o600)
        except (OSError, AttributeError):
            pass
    except Exception:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------
# SecretsStore
# ------------------------------------------------------------------

class SecretsStore:
    """
    Secrets 管理（at-rest 暗号化対応）

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
            encrypted_value = _crypto.encrypt(value)
            data = {
                "key": key,
                "value": encrypted_value,
                "created_at": now if created else self._read_meta_field(key, "created_at", now),
                "updated_at": now,
                "deleted_at": None,
            }

            try:
                _atomic_write_json(path, data)
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
                _atomic_write_json(path, data)
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
                raw_value = data.get("value")
                if raw_value is None:
                    return None

                # 復号
                try:
                    plaintext = _crypto.decrypt(raw_value)
                except Exception as e:
                    logger.error("Failed to decrypt secret '%s': %s", key, e)
                    return None

                # 平文データの自動マイグレーション
                if not _crypto.is_encrypted(raw_value):
                    self._migrate_to_encrypted(key, data, plaintext)

                return plaintext
            except Exception:
                return None

    def _migrate_to_encrypted(
        self, key: str, data: Dict[str, Any], plaintext: str
    ) -> None:
        """平文の secret を暗号化して書き直す（自動マイグレーション）"""
        try:
            encrypted_value = _crypto.encrypt(plaintext)
            migrated_data = dict(data)
            migrated_data["value"] = encrypted_value
            path = self._key_path(key)
            _atomic_write_json(path, migrated_data)
            logger.info("Migrated secret '%s' from plaintext to encrypted storage.", key)
        except Exception as e:
            # マイグレーション失敗でも元データは atomic write により保持
            logger.warning(
                "Failed to migrate secret '%s' to encrypted storage: %s. "
                "Plaintext data is preserved.", key, e
            )

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
