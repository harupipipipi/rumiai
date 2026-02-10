"""
capability_trust_store.py - Capability ハンドラー信頼ストア

user_data/capabilities/trust/trusted_handlers.json を管理し、
handler_id + sha256 の allowlist による信頼判定を行う。

設計原則:
- Trust は handler.py の sha256 一致で判定（必須）
- sha256 不一致は無条件で拒否
- 信頼リストに無い handler_id も拒否
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TrustedHandler:
    """信頼済みハンドラーエントリ"""
    handler_id: str
    sha256: str
    note: str = ""


@dataclass
class TrustCheckResult:
    """Trust チェック結果"""
    trusted: bool
    reason: str
    handler_id: str
    expected_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None


class CapabilityTrustStore:
    """
    ハンドラー信頼ストア
    
    trusted_handlers.json から allowlist をロードし、
    handler_id + sha256 で信頼判定を行う。
    """
    
    DEFAULT_TRUST_DIR = "user_data/capabilities/trust"
    TRUST_FILE_NAME = "trusted_handlers.json"
    
    def __init__(self, trust_dir: str = None):
        self._trust_dir = Path(trust_dir) if trust_dir else Path(self.DEFAULT_TRUST_DIR)
        self._trust_file = self._trust_dir / self.TRUST_FILE_NAME
        self._lock = threading.RLock()
        self._trusted: Dict[str, TrustedHandler] = {}  # handler_id -> TrustedHandler
        self._loaded: bool = False
        self._load_error: Optional[str] = None
    
    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def load(self) -> bool:
        """信頼リストをロード"""
        with self._lock:
            self._trusted.clear()
            self._loaded = False
            self._load_error = None
            
            if not self._trust_file.exists():
                # ファイルが無い場合は空リスト（全拒否）
                self._loaded = True
                return True
            
            try:
                with open(self._trust_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self._load_error = f"Failed to parse trust file: {e}"
                return False
            
            if not isinstance(data, dict):
                self._load_error = "Trust file must be a JSON object"
                return False
            
            trusted_list = data.get("trusted", [])
            if not isinstance(trusted_list, list):
                self._load_error = "'trusted' must be an array"
                return False
            
            for i, entry in enumerate(trusted_list):
                if not isinstance(entry, dict):
                    self._load_error = f"trusted[{i}] must be an object"
                    return False
                
                handler_id = entry.get("handler_id")
                sha256 = entry.get("sha256")
                
                if not handler_id or not isinstance(handler_id, str):
                    self._load_error = f"trusted[{i}]: missing or invalid 'handler_id'"
                    return False
                
                if not sha256 or not isinstance(sha256, str):
                    self._load_error = f"trusted[{i}]: missing or invalid 'sha256'"
                    return False
                
                # sha256 形式の基本チェック（64文字の16進数）
                if len(sha256) != 64:
                    self._load_error = f"trusted[{i}]: sha256 must be 64 hex characters, got {len(sha256)}"
                    return False
                
                try:
                    int(sha256, 16)
                except ValueError:
                    self._load_error = f"trusted[{i}]: sha256 is not valid hex"
                    return False
                
                self._trusted[handler_id] = TrustedHandler(
                    handler_id=handler_id,
                    sha256=sha256.lower(),
                    note=entry.get("note", ""),
                )
            
            self._loaded = True
            return True
    
    def is_trusted(self, handler_id: str, actual_sha256: str) -> TrustCheckResult:
        """
        ハンドラーが信頼済みかチェック
        
        Args:
            handler_id: ハンドラーID
            actual_sha256: handler.py の実際の sha256
        
        Returns:
            TrustCheckResult
        """
        with self._lock:
            if not self._loaded:
                return TrustCheckResult(
                    trusted=False,
                    reason="Trust store not loaded",
                    handler_id=handler_id,
                    actual_sha256=actual_sha256,
                )
            
            entry = self._trusted.get(handler_id)
            if entry is None:
                return TrustCheckResult(
                    trusted=False,
                    reason=f"Handler '{handler_id}' not in trust list",
                    handler_id=handler_id,
                    actual_sha256=actual_sha256,
                )
            
            actual_lower = actual_sha256.lower()
            if entry.sha256 != actual_lower:
                return TrustCheckResult(
                    trusted=False,
                    reason=f"SHA-256 mismatch for handler '{handler_id}'",
                    handler_id=handler_id,
                    expected_sha256=entry.sha256,
                    actual_sha256=actual_lower,
                )
            
            return TrustCheckResult(
                trusted=True,
                reason="Trusted",
                handler_id=handler_id,
                expected_sha256=entry.sha256,
                actual_sha256=actual_lower,
            )
    
    def list_trusted(self) -> List[TrustedHandler]:
        """信頼済みハンドラー一覧"""
        with self._lock:
            return list(self._trusted.values())
    
    def is_loaded(self) -> bool:
        """ロード済みか"""
        with self._lock:
            return self._loaded
    
    def get_load_error(self) -> Optional[str]:
        """ロードエラーを取得"""
        with self._lock:
            return self._load_error
    
    def add_trust(self, handler_id: str, sha256: str, note: str = "") -> bool:
        """
        信頼を追加し、ファイルに保存
        
        Args:
            handler_id: ハンドラーID
            sha256: handler.py の sha256
            note: メモ
        
        Returns:
            成功したか
        """
        with self._lock:
            self._trusted[handler_id] = TrustedHandler(
                handler_id=handler_id,
                sha256=sha256.lower(),
                note=note,
            )
            return self._save()
    
    def remove_trust(self, handler_id: str) -> bool:
        """信頼を削除"""
        with self._lock:
            if handler_id not in self._trusted:
                return False
            del self._trusted[handler_id]
            return self._save()
    
    def _save(self) -> bool:
        """信頼リストをファイルに保存"""
        try:
            self._trust_dir.mkdir(parents=True, exist_ok=True)
            
            data = {
                "version": "1.0",
                "trusted_at": self._now_ts(),
                "trusted": [
                    {
                        "handler_id": t.handler_id,
                        "sha256": t.sha256,
                        "note": t.note,
                    }
                    for t in self._trusted.values()
                ],
            }
            
            with open(self._trust_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception:
            return False


# グローバルインスタンス
_global_trust_store: Optional[CapabilityTrustStore] = None
_trust_lock = threading.Lock()


def get_capability_trust_store() -> CapabilityTrustStore:
    """グローバルなCapabilityTrustStoreを取得"""
    global _global_trust_store
    if _global_trust_store is None:
        with _trust_lock:
            if _global_trust_store is None:
                _global_trust_store = CapabilityTrustStore()
    return _global_trust_store


def reset_capability_trust_store(trust_dir: str = None) -> CapabilityTrustStore:
    """リセット（テスト用）"""
    global _global_trust_store
    with _trust_lock:
        _global_trust_store = CapabilityTrustStore(trust_dir)
    return _global_trust_store
