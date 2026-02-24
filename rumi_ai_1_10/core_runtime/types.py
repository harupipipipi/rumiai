"""
types.py - 共通型定義

Wave 14 T-053: 型ヒント基盤モジュール。
プロジェクト全体で共有する型エイリアス・NewType・データクラスを定義する。

主要コンポーネント:
- PackId, FlowId, CapabilityName, HandlerKey, StoreKey: NewType 識別子型
- JsonValue, JsonDict: JSON 関連型エイリアス
- SyncCallback, AsyncCallback: コールバック型エイリアス
- Result[T]: 成功/失敗を表す汎用データクラス
- Severity: ログ重要度の列挙型

設計原則:
- stdlib のみに依存（循環参照を作らない）
- Python 3.9+ 互換
- PEP 561 準拠（py.typed マーカーと併用）
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    NewType,
    Optional,
    TypeVar,
    Union,
)


# ======================================================================
# NewType 識別子型
# ======================================================================

PackId = NewType("PackId", str)
"""Pack 識別子。"""

FlowId = NewType("FlowId", str)
"""Flow 識別子。"""

CapabilityName = NewType("CapabilityName", str)
"""Capability 名。"""

HandlerKey = NewType("HandlerKey", str)
"""Handler キー。"""

StoreKey = NewType("StoreKey", str)
"""Store キー。"""


# ======================================================================
# JSON 型
# ======================================================================

JsonValue = Union[
    str, int, float, bool, None,
    List["JsonValue"],
    Dict[str, "JsonValue"],
]
"""JSON として表現可能な値の再帰型。"""

JsonDict = Dict[str, JsonValue]
"""JSON オブジェクト（文字列キーの辞書）。"""


# ======================================================================
# コールバック型
# ======================================================================

SyncCallback = Callable[..., Any]
"""同期コールバック関数の型。"""

AsyncCallback = Callable[..., Awaitable[Any]]
"""非同期コールバック関数の型。"""


# ======================================================================
# 汎用型変数
# ======================================================================

T = TypeVar("T")


# ======================================================================
# Result 型
# ======================================================================

@dataclass
class Result(Generic[T]):
    """成功/失敗を表す汎用結果型。

    Attributes:
        success: 操作が成功したかどうか。
        value: 成功時の値（失敗時は None）。
        error: 失敗時のエラーメッセージ（成功時は None）。

    Usage::

        ok = Result(success=True, value=42)
        fail = Result(success=False, error="something went wrong")
    """

    success: bool
    value: Optional[T] = None
    error: Optional[str] = None


# ======================================================================
# Severity 列挙型
# ======================================================================

class Severity(str, enum.Enum):
    """ログメッセージの重要度を表す列挙型。

    ``str`` を継承しているため、文字列として直接比較可能::

        assert Severity.INFO == "INFO"
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
