"""
syscall.py - 後方互換ラッパー

PR-B: 単一ソースは core_runtime/rumi_syscall.py
このファイルは後方互換のために残し、rumi_syscallをre-exportする。

これにより、既存の `from core_runtime.syscall import ...` や
`from core_runtime import syscall` が引き続き動作する。
"""

from __future__ import annotations

# 単一ソースからすべてをre-export
from .rumi_syscall import (
    # 定数
    DEFAULT_SOCKET_PATH,
    SOCKET_PATH,
    MAX_RESPONSE_SIZE,
    DEFAULT_TIMEOUT,
    MAX_TIMEOUT,
    # 例外
    SyscallError,
    # 関数
    http_request,
    request,
    get,
    post,
    post_json,
)

__all__ = [
    "DEFAULT_SOCKET_PATH",
    "SOCKET_PATH",
    "MAX_RESPONSE_SIZE",
    "DEFAULT_TIMEOUT",
    "MAX_TIMEOUT",
    "SyscallError",
    "http_request",
    "request",
    "get",
    "post",
    "post_json",
]
