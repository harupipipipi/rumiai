"""
deprecation.py - deprecated API 管理基盤 (Wave 14 T-057)

deprecated デコレータ、DeprecationRegistry を提供し、
非推奨 API を体系的に管理・警告する基盤モジュール。

主要コンポーネント:
- DeprecationInfo: 非推奨情報を保持する frozen dataclass
- DeprecationRegistry: 非推奨 API を登録・管理するシングルトン
- deprecated(): 関数/メソッド用デコレータ（async 対応）
- deprecated_class(): クラス用デコレータ

警告レベル制御:
  環境変数 RUMI_DEPRECATION_LEVEL で制御:
    "warn"   (デフォルト) - warnings.warn で DeprecationWarning を発行
    "error"  - DeprecationWarning 例外を送出
    "silent" - 何もしない
    "log"    - logging で WARNING レベル出力

設計原則:
- stdlib のみに依存（循環参照を作らない）
- スレッドセーフ（threading.Lock で保護）
- Python 3.9+ 互換
"""

from __future__ import annotations

import functools
import inspect
import logging
import os
import threading
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_logger = logging.getLogger("rumi.deprecation")


# ======================================================================
# DeprecationInfo データクラス
# ======================================================================

@dataclass(frozen=True)
class DeprecationInfo:
    """非推奨 API の情報を保持する不変データクラス。

    Attributes:
        name: API の修飾名（__qualname__）。
        since: 非推奨になったバージョン。
        removed_in: 削除予定バージョン。
        alternative: 代替 API の名前（任意）。
    """

    name: str
    since: str
    removed_in: str
    alternative: Optional[str] = None

    @property
    def message(self) -> str:
        """人間可読な非推奨メッセージを生成する。"""
        msg = (
            f"{self.name} is deprecated since {self.since}, "
            f"will be removed in {self.removed_in}."
        )
        if self.alternative:
            msg += f" Use {self.alternative} instead."
        return msg

    def to_dict(self) -> Dict[str, Any]:
        """JSON シリアライズ可能な dict を返す。"""
        result: Dict[str, Any] = {
            "name": self.name,
            "since": self.since,
            "removed_in": self.removed_in,
        }
        if self.alternative is not None:
            result["alternative"] = self.alternative
        return result


# ======================================================================
# DeprecationRegistry（シングルトン）
# ======================================================================

class DeprecationRegistry:
    """非推奨 API を登録・管理するスレッドセーフなシングルトンレジストリ。

    Usage::

        registry = DeprecationRegistry.get_instance()
        registry.register("old_func", since="1.5", removed_in="2.0",
                          alternative="new_func")
        print(registry.report())
    """

    _instance: Optional[DeprecationRegistry] = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._entries: Dict[str, DeprecationInfo] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> DeprecationRegistry:
        """スレッドセーフにシングルトンインスタンスを取得する。"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset_instance(cls) -> None:
        """シングルトンインスタンスをリセットする（テスト用）。"""
        with cls._instance_lock:
            cls._instance = None

    def register(
        self,
        name: str,
        since: str,
        removed_in: str,
        alternative: Optional[str] = None,
    ) -> DeprecationInfo:
        """非推奨 API を手動登録する。

        Args:
            name: API の名前。
            since: 非推奨になったバージョン。
            removed_in: 削除予定バージョン。
            alternative: 代替 API の名前（任意）。

        Returns:
            登録された DeprecationInfo インスタンス。
        """
        info = DeprecationInfo(
            name=name,
            since=since,
            removed_in=removed_in,
            alternative=alternative,
        )
        with self._lock:
            self._entries[name] = info
        return info

    def get_all(self) -> Dict[str, DeprecationInfo]:
        """登録済みの全非推奨 API を ``{name: DeprecationInfo}`` dict で返す。"""
        with self._lock:
            return dict(self._entries)

    def report(self) -> str:
        """テキスト形式の非推奨 API レポートを返す。"""
        with self._lock:
            entries = list(self._entries.values())

        count = len(entries)
        lines: List[str] = [
            f"Deprecated API Report ({count} items)",
            "=" * 40,
        ]
        if count == 0:
            lines.append("No deprecated APIs registered.")
        else:
            for info in sorted(entries, key=lambda x: x.name):
                parts = f"since={info.since}, removed_in={info.removed_in}"
                if info.alternative:
                    parts += f", alternative={info.alternative}"
                lines.append(f"- {info.name} ({parts})")
        return "\n".join(lines)

    def report_dict(self) -> List[Dict[str, Any]]:
        """dict 形式の非推奨 API レポートを返す。"""
        with self._lock:
            entries = list(self._entries.values())
        return [info.to_dict() for info in sorted(entries, key=lambda x: x.name)]

    def clear(self) -> None:
        """全登録をクリアする（テスト用）。"""
        with self._lock:
            self._entries.clear()


# ======================================================================
# 警告レベル制御
# ======================================================================

def _get_deprecation_level() -> str:
    """環境変数 RUMI_DEPRECATION_LEVEL から警告レベルを取得する。"""
    return os.environ.get("RUMI_DEPRECATION_LEVEL", "warn").lower()


def _emit_deprecation_warning(
    info: DeprecationInfo,
    stacklevel: int = 2,
) -> None:
    """警告レベルに応じて非推奨警告を発行する。

    Args:
        info: 非推奨情報。
        stacklevel: warnings.warn に渡す stacklevel。
    """
    level = _get_deprecation_level()
    if level == "silent":
        return
    elif level == "error":
        raise DeprecationWarning(info.message)
    elif level == "log":
        _logger.warning(info.message)
    else:
        # "warn" (default) or any unknown value
        warnings.warn(info.message, DeprecationWarning, stacklevel=stacklevel)


# ======================================================================
# deprecated デコレータ（関数/メソッド用）
# ======================================================================

def deprecated(
    since: str,
    removed_in: str,
    alternative: Optional[str] = None,
) -> Callable[[F], F]:
    """関数/メソッドに非推奨警告を付与するデコレータ。

    デコレータ適用時（定義時）に DeprecationRegistry に自動登録される。
    関数呼び出し時に RUMI_DEPRECATION_LEVEL に応じた警告を発行する。

    async def にも対応する。

    Args:
        since: 非推奨になったバージョン。
        removed_in: 削除予定バージョン。
        alternative: 代替 API の名前（任意）。

    Returns:
        デコレータ関数。

    Example::

        @deprecated(since="1.5", removed_in="2.0", alternative="new_func")
        def old_func(x):
            return x * 2
    """
    def decorator(func: F) -> F:
        qualname = func.__qualname__
        info = DeprecationRegistry.get_instance().register(
            name=qualname,
            since=since,
            removed_in=removed_in,
            alternative=alternative,
        )

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                _emit_deprecation_warning(info, stacklevel=3)
                return await func(*args, **kwargs)
            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                _emit_deprecation_warning(info, stacklevel=3)
                return func(*args, **kwargs)
            return sync_wrapper  # type: ignore[return-value]

    return decorator


# ======================================================================
# deprecated_class デコレータ（クラス用）
# ======================================================================

def deprecated_class(
    since: str,
    removed_in: str,
    alternative: Optional[str] = None,
) -> Callable[[type], type]:
    """クラスに非推奨警告を付与するデコレータ。

    __init__ 呼び出し時に RUMI_DEPRECATION_LEVEL に応じた警告を発行する。
    デコレータ適用時に DeprecationRegistry に自動登録される。

    Args:
        since: 非推奨になったバージョン。
        removed_in: 削除予定バージョン。
        alternative: 代替クラスの名前（任意）。

    Returns:
        デコレータ関数。

    Example::

        @deprecated_class(since="1.5", removed_in="2.0", alternative="NewClass")
        class OldClass:
            pass
    """
    def decorator(cls: type) -> type:
        qualname = cls.__qualname__
        info = DeprecationRegistry.get_instance().register(
            name=qualname,
            since=since,
            removed_in=removed_in,
            alternative=alternative,
        )

        original_init = cls.__init__  # type: ignore[misc]

        def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
            _emit_deprecation_warning(info, stacklevel=3)
            original_init(self, *args, **kwargs)

        # functools.wraps を安全に適用（object.__init__ 等は属性が無い場合がある）
        try:
            new_init = functools.wraps(original_init)(new_init)
        except (TypeError, AttributeError):
            pass

        cls.__init__ = new_init  # type: ignore[misc]
        return cls

    return decorator
