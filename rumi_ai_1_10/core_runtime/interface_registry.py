"""
interface_registry.py - 提供物登録箱(用途名固定しない)

スレッドセーフ、Observable対応版
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Literal, Callable, Iterable, Tuple
from threading import RLock
from contextlib import contextmanager
import fnmatch
import uuid


GetStrategy = Literal["first", "last", "all"]

logger = logging.getLogger(__name__)

# --- Protected key patterns (W17-C: Phase 1 warn only, block behind env flag) ---
_PROTECTED_KEY_PATTERNS: frozenset[str] = frozenset({
    "io.http.server",
    "flow.hooks.before_step",
    "flow.hooks.after_step",
    "flow.error_handler",
})
_PROTECTED_KEY_PREFIXES: tuple[str, ...] = (
    "flow.construct.",
    "kernel:",
)


def _is_protected_key(key: str) -> bool:
    """Return True if *key* matches a protected pattern."""
    if key in _PROTECTED_KEY_PATTERNS:
        return True
    return any(key.startswith(p) for p in _PROTECTED_KEY_PREFIXES)


def _check_protected_key(key: str, meta_dict: Dict[str, Any]) -> bool:
    """Check protected key and handle block/warn.

    Returns True if registration should proceed, raises PermissionError if blocked.
    Sets ``_should_warn`` flag for post-registration warning (returned as side-effect).
    """
    if not _is_protected_key(key) or meta_dict.get("_system"):
        return False  # not protected or system — no warning needed

    _source = meta_dict.get("_source_pack_id", "unknown")

    if os.environ.get("RUMI_BLOCK_PROTECTED_KEYS") == "1":
        logger.error(
            "BLOCKED: Registration to protected key '%s' without _system flag. "
            "source_pack_id=%s",
            key, _source,
        )
        try:
            from .audit_logger import get_audit_logger
            get_audit_logger().log_security_event(
                event_type="protected_key_registration_blocked",
                severity="error",
                description=f"Blocked registration to '{key}'",
                details={"key": key, "source_pack_id": _source},
            )
        except Exception:
            pass
        raise PermissionError(
            f"Registration to protected key '{key}' requires _system=True in meta"
        )

    return True  # warn after registration


def _emit_protected_key_warning(key: str, meta_dict: Dict[str, Any]) -> None:
    """Emit warning + audit log for unprotected registration (outside lock)."""
    _source = meta_dict.get("_source_pack_id", "unknown")
    logger.warning(
        "Registration to protected key '%s' without _system flag. "
        "source_pack_id=%s. This will be blocked in a future version.",
        key, _source,
    )
    try:
        from .audit_logger import get_audit_logger
        get_audit_logger().log_security_event(
            event_type="protected_key_registration",
            severity="warning",
            description=f"Unprotected registration to '{key}'",
            details={"key": key, "source_pack_id": _source},
        )
    except Exception:
        pass


@dataclass
class InterfaceRegistry:
    """
    提供物の登録箱。

    設計(確定仕様):
    - tool/prompt/ai_client 等の用途名をKernelが固定しないため、
      "何でも登録できる箱" を提供する。
    - 同一キーへの複数登録を許可する(OS的な拡張に強い)。
    - スレッドセーフ（RLock使用）
    - Observable（キー変更の監視機能）
    """

    _store: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)
    _observers: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def register(self, key: str, value: Any, meta: Optional[Dict[str, Any]] = None) -> None:
        """
        値をキーに登録する（スレッドセーフ、Observable対応）
        """
        meta_dict: Dict[str, Any]
        if meta is None:
            meta_dict = {}
        elif isinstance(meta, dict):
            meta_dict = dict(meta)
        else:
            meta_dict = {"_raw_meta": meta}

        # W17-C: protected key check (before lock — audit_logger safe)
        _should_warn = _check_protected_key(key, meta_dict)

        entry = {
            "key": key,
            "value": value,
            "meta": meta_dict,
            "ts": self._now_ts(),
        }
        
        old_value = None
        with self._lock:
            items = self._store.get(key, [])
            if items:
                old_value = items[-1].get("value")
            self._store.setdefault(key, []).append(entry)
        
        self._notify_observers(key, old_value, value)

        # W17-C: emit warning outside lock
        if _should_warn:
            _emit_protected_key_warning(key, meta_dict)

    def register_if_absent(
        self, 
        key: str, 
        value: Any, 
        meta: Optional[Dict[str, Any]] = None,
        ttl: Optional[float] = None
    ) -> bool:
        """
        キーが存在しない場合のみ登録（アトミック操作）
        
        Args:
            key: 登録キー
            value: 登録する値
            meta: メタデータ
            ttl: 有効期限（秒）。指定するとその時間後に期限切れとなり、
                 次のregister_if_absentで上書き可能になる。
        
        Returns:
            True: 登録成功（キーが存在しなかった、または期限切れだった）
            False: 登録失敗（キーが既に存在し、有効）
        """
        # W17-C: prepare meta and check protected keys before lock
        meta_dict = dict(meta) if isinstance(meta, dict) else ({"_raw_meta": meta} if meta else {})
        _should_warn = _check_protected_key(key, meta_dict)

        with self._lock:
            existing = self._store.get(key, [])
            
            # 有効なエントリが存在するかチェック
            has_valid = False
            now = datetime.now(timezone.utc)
            for it in existing:
                item_meta = it.get("meta", {})
                expires_at = item_meta.get("_expires_at")
                if expires_at:
                    try:
                        exp_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                        if now <= exp_time:
                            has_valid = True
                            break
                    except (ValueError, TypeError):
                        has_valid = True
                        break
                else:
                    has_valid = True
                    break
            
            if has_valid:
                return False
            
            # TTLが指定されていれば有効期限を設定
            if ttl is not None and ttl > 0:
                expires_at_str = (now + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")
                meta_dict["_expires_at"] = expires_at_str
                meta_dict["_ttl"] = ttl
            
            entry = {
                "key": key,
                "value": value,
                "meta": meta_dict,
                "ts": self._now_ts(),
            }
            self._store.setdefault(key, []).append(entry)
        
        self._notify_observers(key, None, value)

        # W17-C: emit warning outside lock
        if _should_warn:
            _emit_protected_key_warning(key, meta_dict)

        return True

    def register_handler(
        self,
        key: str,
        handler: Callable,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        source_code: Optional[str] = None,
    ) -> None:
        """
        handlerをスキーマ情報付きで登録
        """
        if not callable(handler):
            raise TypeError(f"handler must be callable, got {type(handler)}")
        
        meta_dict = dict(meta) if isinstance(meta, dict) else {}
        meta_dict["_input_schema"] = input_schema
        meta_dict["_output_schema"] = output_schema
        meta_dict["_source_code"] = source_code
        meta_dict["_is_handler"] = True
        
        self.register(key, handler, meta=meta_dict)

    def get(self, key: str, strategy: GetStrategy = "last") -> Any:
        """
        キーから値を取得（スレッドセーフ）
        strategy="all" の場合、空でも [] を返す（None ではない）
        """
        with self._lock:
            items = self._store.get(key, [])
            if not items:
                if strategy == "all":
                    return []
                return None

            if strategy == "first":
                return items[0]["value"]
            if strategy == "last":
                return items[-1]["value"]
            if strategy == "all":
                return [it["value"] for it in items]

            return items[-1]["value"]

    def get_by_owner(self, key: str, owner_pack: str) -> Any:
        """
        キーから特定の owner_pack が登録した値を取得。

        meta の owner_pack, pack_id, source, _source_pack_id, registered_by の
        いずれかが owner_pack に一致するエントリを探す。
        見つからない場合は last を返す。
        """
        with self._lock:
            items = self._store.get(key, [])
            if not items:
                return None
            for item in reversed(items):
                meta = item.get("meta", {})
                item_owner = (
                    meta.get("owner_pack")
                    or meta.get("pack_id")
                    or meta.get("source")
                    or meta.get("_source_pack_id")
                    or meta.get("registered_by")
                )
                if item_owner == owner_pack:
                    return item["value"]
            return items[-1]["value"]

    def get_schema(self, key: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """handlerのスキーマを取得"""
        with self._lock:
            entries = self._store.get(key, [])
            if not entries:
                return None, None
            meta = entries[-1].get("meta", {})
            return meta.get("_input_schema"), meta.get("_output_schema")

    def get_source(self, key: str) -> Optional[str]:
        """handlerのソースコードを取得"""
        with self._lock:
            entries = self._store.get(key, [])
            if not entries:
                return None
            return entries[-1].get("meta", {}).get("_source_code")

    def observe(
        self,
        key_or_pattern: str,
        callback: Callable[[str, Any, Any], None],
        immediate: bool = False
    ) -> str:
        """
        キーまたはパターンの変更を監視
        
        Returns:
            observer_id（解除用）
        """
        observer_id = f"obs_{uuid.uuid4().hex[:8]}"
        
        current_value = None
        with self._lock:
            self._observers.setdefault(key_or_pattern, []).append({
                "id": observer_id,
                "callback": callback
            })
            
            if immediate:
                current = self._store.get(key_or_pattern, [])
                current_value = current[-1]["value"] if current else None
        
        if immediate and current_value is not None:
            try:
                callback(key_or_pattern, None, current_value)
            except Exception:
                pass
        
        return observer_id

    def unobserve(self, observer_id: str) -> bool:
        """監視を解除"""
        with self._lock:
            for pattern, observers in list(self._observers.items()):
                for obs in observers:
                    if obs["id"] == observer_id:
                        observers.remove(obs)
                        if not observers:
                            del self._observers[pattern]
                        return True
        return False

    def unobserve_all(self, pattern: Optional[str] = None) -> int:
        """パターンに一致する全てのobserverを解除"""
        count = 0
        with self._lock:
            if pattern is None:
                count = sum(len(obs) for obs in self._observers.values())
                self._observers.clear()
            elif pattern in self._observers:
                count = len(self._observers[pattern])
                del self._observers[pattern]
        return count

    def _notify_observers(self, key: str, old_value: Any, new_value: Any) -> None:
        """マッチするobserverに通知"""
        to_notify: List[Tuple[str, Callable]] = []
        
        with self._lock:
            for pattern, observers in self._observers.items():
                if self._matches(key, pattern):
                    for obs in observers:
                        to_notify.append((pattern, obs["callback"]))
        
        for pattern, callback in to_notify:
            try:
                callback(key, old_value, new_value)
            except Exception:
                pass

    def _matches(self, key: str, pattern: str) -> bool:
        """キーがパターンにマッチするか"""
        if pattern == key:
            return True
        if "*" in pattern:
            return fnmatch.fnmatch(key, pattern)
        return False

    @contextmanager
    def temporary_override(self, key: str, value: Any, meta: Optional[Dict[str, Any]] = None):
        """一時的な上書き。withブロック終了時に自動復元"""
        with self._lock:
            original_count = len(self._store.get(key, []))
        
        self.register(key, value, meta)
        
        try:
            yield
        finally:
            with self._lock:
                entries = self._store.get(key, [])
                if len(entries) > original_count:
                    self._store[key] = entries[:original_count] if original_count > 0 else []
                    if not self._store[key]:
                        del self._store[key]

    def list(self, prefix: Optional[str] = None, include_meta: bool = False) -> Dict[str, Any]:
        """登録状況を列挙する（スレッドセーフ）"""
        with self._lock:
            keys: Iterable[str]
            if prefix is None:
                keys = list(self._store.keys())
            else:
                keys = [k for k in self._store.keys() if k.startswith(prefix)]

            if not include_meta:
                return {k: len(self._store.get(k, [])) for k in keys}

            out: Dict[str, Any] = {}
            for k in keys:
                items = self._store.get(k, [])
                last = items[-1] if items else None
                out[k] = {
                    "count": len(items),
                    "last_ts": last.get("ts") if last else None,
                    "last_meta": last.get("meta") if last else None,
                }
            return out

    def find(self, predicate: Callable[[str, Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
        """用途名を固定しない探索API（スレッドセーフ）"""
        results: List[Dict[str, Any]] = []
        with self._lock:
            for k, items in self._store.items():
                for entry in items:
                    try:
                        if predicate(k, entry):
                            results.append(entry)
                    except Exception:
                        continue
        return results

    def unregister(self, key: str, predicate: Optional[Callable[[Dict[str, Any]], bool]] = None) -> int:
        """登録解除（スレッドセーフ）"""
        with self._lock:
            if key not in self._store:
                return 0
            if predicate is None:
                count = len(self._store[key])
                del self._store[key]
                return count

            items = self._store.get(key, [])
            kept: List[Dict[str, Any]] = []
            removed = 0
            for entry in items:
                try:
                    if predicate(entry):
                        removed += 1
                    else:
                        kept.append(entry)
                except Exception:
                    kept.append(entry)
            
            if kept:
                self._store[key] = kept
            else:
                del self._store[key]
            return removed
