"""
store_registry.py - ストア定義・作成・列挙・削除

Store（共有領域）を管理する。
公式は "tool/chat/asset" の意味を一切解釈しない。

保存先: user_data/stores/index.json

追加機能:
- #62 create_store_for_pack: 宣言的Store作成
- #6  cas: Compare-And-Swap
- #18 list_keys: ページネーション付きキー列挙
- #19 batch_get: 複数キー一括取得
"""

from __future__ import annotations

import base64
import bisect
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


STORES_INDEX_PATH = "user_data/stores/index.json"
STORES_BASE_DIR = Path("user_data/stores")
MAX_STORES_PER_PACK = 10
MAX_VALUE_BYTES_CAS = 1 * 1024 * 1024  # 1MB
CAS_LOCK_TIMEOUT = 5  # seconds


def _validate_store_path(root_path: str) -> Optional[str]:
    """
    root_path が STORES_BASE_DIR 配下であることを検証する。

    Returns:
        エラーメッセージ (問題がなければ None)
    """
    if ".." in str(root_path):
        return "root_path must not contain '..'"
    resolved = Path(root_path).resolve()
    base = STORES_BASE_DIR.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return f"root_path must be under {STORES_BASE_DIR}/"
    return None


@dataclass
class StoreDefinition:
    store_id: str
    root_path: str
    created_at: str
    created_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store_id": self.store_id,
            "root_path": self.root_path,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoreDefinition":
        return cls(
            store_id=data.get("store_id", ""),
            root_path=data.get("root_path", ""),
            created_at=data.get("created_at", ""),
            created_by=data.get("created_by", ""),
        )


@dataclass
class StoreResult:
    success: bool
    store_id: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "store_id": self.store_id,
            "error": self.error,
        }


class StoreRegistry:
    MAX_BATCH_KEYS = 100
    MAX_BATCH_RESPONSE_BYTES = 900 * 1024  # 900KB

    def __init__(self, index_path: Optional[str] = None):
        self._index_path = Path(index_path or STORES_INDEX_PATH)
        self._lock = threading.RLock()
        self._stores: Dict[str, StoreDefinition] = {}
        self._load()

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, sdata in data.get("stores", {}).items():
                self._stores[sid] = StoreDefinition.from_dict(sdata)
        except Exception:
            pass

    def _save(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "updated_at": self._now_ts(),
            "stores": {sid: s.to_dict() for sid, s in self._stores.items()},
        }
        tmp = self._index_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self._index_path)

    def create_store(
        self,
        store_id: str,
        root_path: str,
        created_by: str = "api_user",
    ) -> StoreResult:
        if not store_id or not re.match(r'^[a-zA-Z0-9_-]{1,128}$', store_id):
            return StoreResult(
                success=False, store_id=store_id,
                error="store_id must match ^[a-zA-Z0-9_-]{1,128}$",
            )
        if not root_path:
            return StoreResult(
                success=False, store_id=store_id, error="root_path is required",
            )

        # パストラバーサル防止
        path_err = _validate_store_path(root_path)
        if path_err:
            return StoreResult(
                success=False, store_id=store_id, error=path_err,
            )

        with self._lock:
            if store_id in self._stores:
                return StoreResult(
                    success=False, store_id=store_id,
                    error=f"Store already exists: {store_id}",
                )
            rp = Path(root_path)
            try:
                rp.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return StoreResult(
                    success=False, store_id=store_id,
                    error=f"Failed to create root_path: {e}",
                )
            self._stores[store_id] = StoreDefinition(
                store_id=store_id,
                root_path=str(rp.resolve()),
                created_at=self._now_ts(),
                created_by=created_by,
            )
            self._save()
            self._audit("store_created", True, {
                "store_id": store_id, "root_path": str(rp.resolve()),
            })
            return StoreResult(success=True, store_id=store_id)

    def list_stores(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._stores.values()]

    def get_store(self, store_id: str) -> Optional[StoreDefinition]:
        with self._lock:
            return self._stores.get(store_id)

    def delete_store(
        self,
        store_id: str,
        delete_files: bool = False,
    ) -> StoreResult:
        with self._lock:
            store = self._stores.get(store_id)
            if store is None:
                return StoreResult(
                    success=False, store_id=store_id,
                    error=f"Store not found: {store_id}",
                )

            # パストラバーサル防止（登録済みパスも再検証）
            path_err = _validate_store_path(store.root_path)
            if path_err:
                return StoreResult(
                    success=False, store_id=store_id, error=path_err,
                )

            if delete_files:
                try:
                    rp = Path(store.root_path)
                    if rp.exists():
                        shutil.rmtree(rp)
                except Exception as e:
                    return StoreResult(
                        success=False, store_id=store_id,
                        error=f"Failed to delete files: {e}",
                    )
            del self._stores[store_id]
            self._save()
            self._audit("store_deleted", True, {
                "store_id": store_id, "delete_files": delete_files,
            })
            return StoreResult(success=True, store_id=store_id)

    # ------------------------------------------------------------------ #
    # #62  Declarative store creation (called from approval_manager)
    # ------------------------------------------------------------------ #

    def create_store_for_pack(
        self,
        pack_id: str,
        stores_decl: List[Dict[str, Any]],
    ) -> List[StoreResult]:
        """
        ecosystem.json の stores 宣言に基づき Store を一括作成する。

        - store_id には "{pack_id}__" プレフィックスを強制付与
        - 1 Pack あたり最大 MAX_STORES_PER_PACK 個
        - 既に存在する場合はスキップ（成功扱い）
        """
        results: List[StoreResult] = []

        if not stores_decl or not isinstance(stores_decl, list):
            return results

        if len(stores_decl) > MAX_STORES_PER_PACK:
            results.append(StoreResult(
                success=False,
                error=f"Too many stores declared ({len(stores_decl)}). "
                      f"Maximum is {MAX_STORES_PER_PACK} per Pack.",
            ))
            return results

        for entry in stores_decl:
            if not isinstance(entry, dict):
                results.append(StoreResult(
                    success=False,
                    error="Invalid store declaration (not a dict)",
                ))
                continue

            raw_store_id = entry.get("store_id", "")
            if not raw_store_id or not isinstance(raw_store_id, str):
                results.append(StoreResult(
                    success=False,
                    error="Missing or invalid store_id in declaration",
                ))
                continue

            # プレフィックス強制
            prefix = f"{pack_id}__"
            if raw_store_id.startswith(prefix):
                qualified_id = raw_store_id
            else:
                qualified_id = f"{prefix}{raw_store_id}"

            # store_id バリデーション
            if not re.match(r'^[a-zA-Z0-9_-]{1,128}$', qualified_id):
                results.append(StoreResult(
                    success=False,
                    store_id=qualified_id,
                    error="Qualified store_id must match ^[a-zA-Z0-9_-]{1,128}$",
                ))
                continue

            root_path = str(STORES_BASE_DIR / qualified_id)

            with self._lock:
                if qualified_id in self._stores:
                    results.append(StoreResult(success=True, store_id=qualified_id))
                    continue

            result = self.create_store(
                store_id=qualified_id,
                root_path=root_path,
                created_by=f"pack:{pack_id}",
            )
            results.append(result)

        return results

    # ------------------------------------------------------------------ #
    # #6  Compare-And-Swap
    # ------------------------------------------------------------------ #

    def cas(
        self,
        store_id: str,
        key: str,
        expected_value: Any,
        new_value: Any,
    ) -> Dict[str, Any]:
        """
        Compare-And-Swap: expected_value が現在値と一致する場合のみ
        new_value で上書きする。ファイルレベルロック使用。

        Linux/macOS のみ対応。
        """
        import platform
        if platform.system() == "Windows":
            raise NotImplementedError(
                "store.cas is not supported on Windows (requires fcntl)"
            )

        import fcntl
        import signal

        store_def = self.get_store(store_id)
        if store_def is None:
            return {
                "success": False,
                "error": f"Store not found: {store_id}",
                "error_type": "store_not_found",
            }

        store_root = Path(store_def.root_path)
        if not store_root.is_dir():
            return {
                "success": False,
                "error": f"Store root not found: {store_id}",
                "error_type": "store_not_found",
            }

        file_path = store_root / (key + ".json")
        file_path = Path(os.path.normpath(file_path))

        # boundary check
        try:
            resolved = file_path.resolve()
            resolved.relative_to(store_root.resolve())
        except (ValueError, OSError):
            return {
                "success": False,
                "error": "Path traversal detected",
                "error_type": "security_error",
            }

        # value size check
        try:
            new_value_json = json.dumps(
                new_value, ensure_ascii=False, default=str
            )
        except (TypeError, ValueError) as e:
            return {
                "success": False,
                "error": f"new_value is not JSON serializable: {e}",
                "error_type": "validation_error",
            }

        if len(new_value_json.encode("utf-8")) > MAX_VALUE_BYTES_CAS:
            return {
                "success": False,
                "error": f"Value too large (max {MAX_VALUE_BYTES_CAS} bytes)",
                "error_type": "payload_too_large",
            }

        file_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = file_path.with_suffix(".lock")

        lock_fd = None
        try:
            lock_fd = open(lock_path, "w")

            old_handler = signal.signal(
                signal.SIGALRM,
                lambda s, f: (_ for _ in ()).throw(
                    TimeoutError("CAS lock timeout")
                ),
            )
            signal.alarm(CAS_LOCK_TIMEOUT)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            # --- critical section ---
            current_value = None
            exists = file_path.exists()

            if exists:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        current_value = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    return {
                        "success": False,
                        "error": f"Failed to read current value: {e}",
                        "error_type": "read_error",
                    }

            # compare
            if not exists and expected_value is None:
                pass  # create OK
            elif not exists and expected_value is not None:
                return {
                    "success": False,
                    "error": "Key does not exist but expected_value is not None",
                    "error_type": "conflict",
                    "current_value": None,
                }
            elif exists and expected_value is None:
                return {
                    "success": False,
                    "error": "Key exists but expected_value is None",
                    "error_type": "conflict",
                    "current_value": current_value,
                }
            else:
                if current_value != expected_value:
                    return {
                        "success": False,
                        "error": "Value mismatch (conflict)",
                        "error_type": "conflict",
                        "current_value": current_value,
                    }

            # swap — atomic write
            tmp_path = file_path.with_suffix(".cas_tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(new_value_json)
            tmp_path.replace(file_path)

            return {"success": True, "store_id": store_id, "key": key}

        except TimeoutError:
            return {
                "success": False,
                "error": "CAS lock timeout",
                "error_type": "timeout",
            }
        except OSError as e:
            return {
                "success": False,
                "error": f"CAS I/O error: {e}",
                "error_type": "io_error",
            }
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    lock_fd.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------ #
    # #18  List with pagination
    # ------------------------------------------------------------------ #

    def list_keys(
        self,
        store_id: str,
        prefix: str = "",
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store 内のキーを列挙する（ページネーション対応）。

        limit/cursor 両方 None なら全件返却（後方互換）。
        """
        store_def = self.get_store(store_id)
        if store_def is None:
            return {
                "success": False,
                "error": f"Store not found: {store_id}",
                "error_type": "store_not_found",
            }

        store_root = Path(store_def.root_path)
        if not store_root.is_dir():
            return {
                "success": False,
                "error": "Store root not found",
                "error_type": "store_not_found",
            }

        # Enumerate all keys
        all_keys: List[str] = []
        try:
            for json_file in sorted(store_root.rglob("*.json")):
                if not json_file.is_file():
                    continue
                try:
                    rel = json_file.relative_to(store_root)
                except ValueError:
                    continue
                key = str(rel.with_suffix("")).replace("\\", "/")
                if prefix and not key.startswith(prefix):
                    continue
                all_keys.append(key)
        except OSError:
            pass

        total_estimate = len(all_keys)

        # No pagination → return all (backward compatible)
        if limit is None and cursor is None:
            return {
                "success": True,
                "keys": all_keys,
                "next_cursor": None,
                "has_more": False,
                "total_estimate": total_estimate,
            }

        if limit is None:
            limit = 100
        if not isinstance(limit, int) or limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000

        start_idx = 0
        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode("utf-8")
            except Exception:
                return {
                    "success": False,
                    "error": "Invalid cursor",
                    "error_type": "validation_error",
                }
            start_idx = bisect.bisect_right(all_keys, decoded)

        page = all_keys[start_idx : start_idx + limit]
        has_more = (start_idx + limit) < total_estimate

        next_cursor = None
        if has_more and page:
            next_cursor = base64.b64encode(
                page[-1].encode("utf-8")
            ).decode("ascii")

        return {
            "success": True,
            "keys": page,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total_estimate": total_estimate,
        }

    # ------------------------------------------------------------------ #
    # #19  Batch get
    # ------------------------------------------------------------------ #

    def batch_get(
        self,
        store_id: str,
        keys: List[str],
    ) -> Dict[str, Any]:
        """
        複数キーを一度に取得する。最大100キー、累計900KB超で残りはnull。
        """
        if not keys or not isinstance(keys, list):
            return {
                "success": False,
                "error": "Missing or invalid keys",
                "error_type": "validation_error",
            }

        if len(keys) > self.MAX_BATCH_KEYS:
            return {
                "success": False,
                "error": f"Too many keys ({len(keys)}). "
                         f"Maximum is {self.MAX_BATCH_KEYS}.",
                "error_type": "validation_error",
            }

        store_def = self.get_store(store_id)
        if store_def is None:
            return {
                "success": False,
                "error": f"Store not found: {store_id}",
                "error_type": "store_not_found",
            }

        store_root = Path(store_def.root_path)
        if not store_root.is_dir():
            return {
                "success": False,
                "error": "Store root not found",
                "error_type": "store_not_found",
            }

        results: Dict[str, Any] = {}
        found = 0
        not_found = 0
        warnings: List[str] = []
        cumulative_size = 0
        size_exceeded = False

        for key in keys:
            if size_exceeded:
                results[key] = None
                not_found += 1
                continue

            if not key or not isinstance(key, str):
                results[key if key else ""] = None
                not_found += 1
                continue

            file_path = store_root / (key + ".json")
            file_path = Path(os.path.normpath(file_path))

            try:
                resolved = file_path.resolve()
                resolved.relative_to(store_root.resolve())
            except (ValueError, OSError):
                results[key] = None
                not_found += 1
                continue

            if not file_path.exists():
                results[key] = None
                not_found += 1
                continue

            try:
                raw = file_path.read_text(encoding="utf-8")
                value = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                results[key] = None
                not_found += 1
                continue

            entry_size = len(raw.encode("utf-8"))
            if cumulative_size + entry_size > self.MAX_BATCH_RESPONSE_BYTES:
                size_exceeded = True
                results[key] = None
                not_found += 1
                remaining_count = len(keys) - len(results)
                warnings.append(
                    f"Response size limit (900KB) exceeded at key '{key}'. "
                    f"Remaining {remaining_count} keys returned as null."
                )
                continue

            cumulative_size += entry_size
            results[key] = value
            found += 1

        resp: Dict[str, Any] = {
            "success": True,
            "results": results,
            "found": found,
            "not_found": not_found,
        }
        if warnings:
            resp["warnings"] = warnings
        return resp

    @staticmethod
    def _audit(event_type: str, success: bool, details: Dict[str, Any]) -> None:
        try:
            from .audit_logger import get_audit_logger
            get_audit_logger().log_system_event(
                event_type=event_type, success=success, details=details,
            )
        except Exception:
            pass


_global_store_registry: Optional[StoreRegistry] = None
_store_lock = threading.Lock()


def get_store_registry() -> StoreRegistry:
    global _global_store_registry
    if _global_store_registry is None:
        with _store_lock:
            if _global_store_registry is None:
                _global_store_registry = StoreRegistry()
    return _global_store_registry


def reset_store_registry(index_path: str = None) -> StoreRegistry:
    global _global_store_registry
    with _store_lock:
        _global_store_registry = StoreRegistry(index_path)
    return _global_store_registry
