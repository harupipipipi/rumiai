#!/usr/bin/env python3
"""
request_display - viewer:display capability の使用例（スタブ）。

この Function は calling_convention: block で定義されています。
実行時は Kernel の DI ハンドラ（handle_display）経由で処理されます。
このファイルは Pack 構造の完全性のために存在します。

stdin/stdout JSON インターフェースは、将来のサブプロセス実行モデル
への移行に備えたプレースホルダーです。
"""

import json
import sys


def main():
    """Stub entry point for 'request_display'."""
    try:
        raw = sys.stdin.read()
        if raw.strip():
            request = json.loads(raw)
        else:
            request = {}
    except json.JSONDecodeError:
        request = {}

    response = {
        "status": "error",
        "message": (
            "This function uses calling_convention 'block'. "
            "It is executed via the kernel's DI handler (handle_display). "
            "Direct invocation via stdin/stdout is not supported."
        ),
        "function_id": "request_display",
    }

    json.dump(response, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
