"""
hmac_key_manager.py - HMAC鍵のローテーション管理

鍵の生成・保存・ローテーション・グレースピリオド検証を提供する。

鍵の保存先: user_data/hmac_keys.json (.gitignore 登録済み)
グレースピリオド: デフォルト24時間（ローテーション後も旧鍵で検証可能）
ローテーショントリガー:
  - 環境変数 RUMI_HMAC_ROTATE=true で起動時にローテーション
  - プログラムから rotate() を呼び出し
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# デフォルトグレースピリオド（秒）: 24時間
DEFAULT_GRACE_PERIOD_SECONDS = 86400

# デフォルト鍵保存パス
_DEFAULT_KEYS_FILENAME = "hmac_keys.json"
_DEFAULT_KEYS_SUBDIR = "user_data"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_ts() -> str:
    return _now_utc().isoformat().replace("+00:00", "Z")


def _parse_ts(ts: str) -> datetime:
    """ISO 8601 タイムスタンプをパース"""
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


@dataclass
class HMACKey:
    """HMAC鍵情報"""
    key: str
    created_at: str
    rotated_at: Optional[str] = None  # この鍵がローテーションで退役した時刻
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "created_at": self.created_at,
            "rotated_at": self.rotated_at,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HMACKey":
        return cls(
            key=data["key"],
            created_at=data["created_at"],
            rotated_at=data.get("rotated_at"),
            is_active=data.get("is_active", True),
        )


class HMACKeyManager:
    """
    HMAC鍵のライフサイクル管理

    機能:
    - 初回起動時に鍵を自動生成
    - ローテーション（新鍵生成 + 旧鍵をグレースピリオド付きで保持）
    - グレースピリオド内は旧鍵でも検証可能
    - グレースピリオド超過した旧鍵は自動削除

    使い方:
        manager = HMACKeyManager()
        current_token = manager.get_active_key()
        is_valid = manager.verify_token(token_from_request)
    """

    def __init__(
        self,
        keys_path: Optional[str] = None,
        grace_period_seconds: int = DEFAULT_GRACE_PERIOD_SECONDS,
    ):
        """
        Args:
            keys_path: 鍵ファイルのパス。None の場合は BASE_DIR/user_data/hmac_keys.json
            grace_period_seconds: グレースピリオド（秒）
        """
        if keys_path is None:
            try:
                from .paths import BASE_DIR
                keys_path = str(BASE_DIR / _DEFAULT_KEYS_SUBDIR / _DEFAULT_KEYS_FILENAME)
            except ImportError:
                keys_path = os.path.join(_DEFAULT_KEYS_SUBDIR, _DEFAULT_KEYS_FILENAME)

        self._keys_path = Path(keys_path)
        self._grace_period = timedelta(seconds=grace_period_seconds)
        self._keys: List[HMACKey] = []
        self._lock = threading.Lock()

        # 鍵をロードまたは初回生成
        self._load_or_initialize()

        # 環境変数によるローテーショントリガー
        if os.environ.get("RUMI_HMAC_ROTATE", "").lower() == "true":
            self.rotate()
            # 一度ローテーションしたらフラグをクリア（同一プロセス内での再トリガー防止）
            os.environ.pop("RUMI_HMAC_ROTATE", None)

    def _load_or_initialize(self) -> None:
        """鍵ファイルをロード。存在しなければ新規生成。"""
        with self._lock:
            if self._keys_path.exists():
                try:
                    with open(self._keys_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._keys = [HMACKey.from_dict(k) for k in data.get("keys", [])]
                    # 期限切れの旧鍵を削除
                    self._cleanup_expired_keys_internal()
                    # アクティブ鍵がなければ新規生成
                    if not any(k.is_active for k in self._keys):
                        self._generate_new_key_internal()
                    return
                except (json.JSONDecodeError, KeyError, IOError) as e:
                    print(f"[HMACKeyManager] 鍵ファイル読み込みエラー、新規生成します: {e}")

            # 初回: 新規生成
            self._keys = []
            self._generate_new_key_internal()

    def _generate_new_key_internal(self) -> HMACKey:
        """新しいアクティブ鍵を生成（ロック保持状態で呼び出す内部用）"""
        new_key = HMACKey(
            key=secrets.token_urlsafe(32),
            created_at=_now_ts(),
            is_active=True,
        )
        self._keys.append(new_key)
        self._save_internal()
        return new_key

    def _save_internal(self) -> None:
        """鍵ファイルを保存（ロック保持状態で呼び出す内部用）"""
        self._keys_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "updated_at": _now_ts(),
            "grace_period_seconds": int(self._grace_period.total_seconds()),
            "keys": [k.to_dict() for k in self._keys],
        }
        try:
            with open(self._keys_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[HMACKeyManager] 鍵ファイル保存エラー: {e}")

    def _cleanup_expired_keys_internal(self) -> None:
        """グレースピリオド超過した旧鍵を削除（ロック保持状態）"""
        now = _now_utc()
        surviving: List[HMACKey] = []
        for key in self._keys:
            if key.is_active:
                surviving.append(key)
                continue
            # 退役済み鍵: グレースピリオド内なら保持
            if key.rotated_at:
                try:
                    rotated_time = _parse_ts(key.rotated_at)
                    if now - rotated_time < self._grace_period:
                        surviving.append(key)
                        continue
                except (ValueError, TypeError):
                    pass
            # グレースピリオド超過または rotated_at なし → 削除
        self._keys = surviving

    def get_active_key(self) -> str:
        """現在のアクティブ鍵を取得"""
        with self._lock:
            for key in self._keys:
                if key.is_active:
                    return key.key
            # アクティブ鍵がない（理論上ないはず）→ 生成
            new_key = self._generate_new_key_internal()
            return new_key.key

    def verify_token(self, token: str) -> bool:
        """
        トークンを検証

        アクティブ鍵 + グレースピリオド内の旧鍵すべてで照合する。
        1つでも一致すれば True。

        Args:
            token: 検証するトークン文字列

        Returns:
            True: 有効な鍵で署名されている
            False: どの鍵にも一致しない
        """
        if not token:
            return False
        with self._lock:
            for key in self._keys:
                if hmac.compare_digest(token, key.key):
                    return True
            return False

    def rotate(self) -> str:
        """
        鍵をローテーション

        現在のアクティブ鍵を退役させ（グレースピリオド付き）、
        新しいアクティブ鍵を生成する。

        Returns:
            新しいアクティブ鍵
        """
        with self._lock:
            now_str = _now_ts()
            # 現在のアクティブ鍵を退役
            for key in self._keys:
                if key.is_active:
                    key.is_active = False
                    key.rotated_at = now_str
            # 期限切れの旧鍵を削除
            self._cleanup_expired_keys_internal()
            # 新しいアクティブ鍵を生成
            new_key = self._generate_new_key_internal()

            # 監査ログ（best-effort）
            try:
                from .audit_logger import get_audit_logger
                audit = get_audit_logger()
                audit.log_security_event(
                    event_type="hmac_key_rotated",
                    severity="info",
                    description="HMAC API key rotated",
                    details={
                        "new_key_created_at": new_key.created_at,
                        "grace_period_seconds": int(self._grace_period.total_seconds()),
                        "total_keys": len(self._keys),
                    },
                )
            except Exception:
                pass

            print(f"[HMACKeyManager] 鍵ローテーション完了。アクティブ鍵数: {sum(1 for k in self._keys if k.is_active)}, "
                  f"グレースピリオド中の旧鍵数: {sum(1 for k in self._keys if not k.is_active)}")

            return new_key.key

    def get_key_info(self) -> Dict[str, Any]:
        """鍵の状態情報を取得（デバッグ/管理用、鍵の値は含めない）"""
        with self._lock:
            return {
                "total_keys": len(self._keys),
                "active_keys": sum(1 for k in self._keys if k.is_active),
                "grace_period_keys": sum(1 for k in self._keys if not k.is_active),
                "grace_period_seconds": int(self._grace_period.total_seconds()),
                "keys_path": str(self._keys_path),
                "keys": [
                    {
                        "created_at": k.created_at,
                        "rotated_at": k.rotated_at,
                        "is_active": k.is_active,
                        "key_prefix": k.key[:8] + "...",  # 先頭8文字のみ
                    }
                    for k in self._keys
                ],
            }


# ======================================================================
# グローバルインスタンス
# ======================================================================

_global_hmac_key_manager: Optional[HMACKeyManager] = None
_hmac_lock = threading.Lock()


def get_hmac_key_manager() -> HMACKeyManager:
    """グローバルな HMACKeyManager を取得（遅延初期化）"""
    global _global_hmac_key_manager
    if _global_hmac_key_manager is None:
        with _hmac_lock:
            if _global_hmac_key_manager is None:
                _global_hmac_key_manager = HMACKeyManager()
    return _global_hmac_key_manager


def initialize_hmac_key_manager(
    keys_path: Optional[str] = None,
    grace_period_seconds: int = DEFAULT_GRACE_PERIOD_SECONDS,
) -> HMACKeyManager:
    """HMACKeyManager を明示的に初期化"""
    global _global_hmac_key_manager
    with _hmac_lock:
        _global_hmac_key_manager = HMACKeyManager(
            keys_path=keys_path,
            grace_period_seconds=grace_period_seconds,
        )
    return _global_hmac_key_manager


def reset_hmac_key_manager() -> None:
    """HMACKeyManager をリセット（テスト用）"""
    global _global_hmac_key_manager
    with _hmac_lock:
        _global_hmac_key_manager = None
