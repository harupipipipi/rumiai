"""
kernel_variable_resolver.py - 変数解決ロジック

kernel_core.py から抽出。
$flow., $ctx., $env. パターンマッチによる変数解決を提供する。

K-1: kernel_core.py 責務分割の一環
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

# --- resolve depth limit (Fix #70) ---
MAX_RESOLVE_DEPTH = 20

# --- $variable pattern ---
_VAR_REF_RE = re.compile(r'\$(?:flow|ctx|env)\.[a-zA-Z0-9_.]+')


class VariableResolver:
    """
    Flow 変数解決エンジン

    $flow.<key>, $ctx.<key>, $env.<key> 形式の変数参照を
    コンテキスト辞書から解決する。
    dict / list の再帰解決にも対応。
    """

    def __init__(self, max_depth: int = MAX_RESOLVE_DEPTH) -> None:
        self._max_depth = max_depth

    def resolve_value(self, value: Any, ctx: Dict[str, Any], depth: int = 0) -> Any:
        """
        値を解決する。

        - str: $flow.x / $ctx.x / $env.x を展開
        - dict: 各 value を再帰解決
        - list: 各要素を再帰解決
        - その他: そのまま返す
        """
        if depth > self._max_depth:
            return value

        if isinstance(value, str):
            return self._resolve_string(value, ctx, depth)
        elif isinstance(value, dict):
            return {k: self.resolve_value(v, ctx, depth + 1) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_value(item, ctx, depth + 1) for item in value]
        return value

    def resolve_args(self, args: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        引数辞書の値を解決する。
        """
        if not isinstance(args, dict):
            return args
        return {k: self.resolve_value(v, ctx) for k, v in args.items()}

    def _resolve_string(self, value: str, ctx: Dict[str, Any], depth: int) -> Any:
        """
        文字列の変数参照を解決する。

        文字列全体が単一の変数参照の場合、元の型を保持する。
        文字列の一部に変数参照が含まれる場合、文字列として展開する。
        """
        stripped = value.strip()

        # 文字列全体が単一の変数参照の場合 → 元の型を保持
        if _VAR_REF_RE.fullmatch(stripped):
            resolved = self._lookup_variable(stripped, ctx)
            if resolved is not stripped:
                # さらに文字列なら再帰解決
                if isinstance(resolved, str) and depth < self._max_depth:
                    return self.resolve_value(resolved, ctx, depth + 1)
                return resolved

        # 部分的な変数参照を含む場合 → 文字列置換
        def _replacer(m: re.Match) -> str:
            ref = m.group(0)
            resolved = self._lookup_variable(ref, ctx)
            return str(resolved) if resolved is not ref else ref

        result = _VAR_REF_RE.sub(_replacer, value)
        return result

    def _lookup_variable(self, ref: str, ctx: Dict[str, Any]) -> Any:
        """
        単一の変数参照を解決する。

        $flow.<key>  → ctx["<key>"]
        $ctx.<key>   → ctx["<key>"]
        $env.<key>   → os.environ["<key>"]

        ドット区切りのネストアクセスに対応:
        $ctx.a.b.c → ctx["a"]["b"]["c"]

        解決できない場合は元の参照文字列をそのまま返す。
        """
        if not ref.startswith("$"):
            return ref

        # $ を除去してプレフィックスとパスに分割
        body = ref[1:]  # "flow.key.sub" or "ctx.key" or "env.KEY"
        parts = body.split(".")

        if len(parts) < 2:
            return ref

        prefix = parts[0]  # "flow" | "ctx" | "env"
        path = parts[1:]   # ["key", "sub", ...]

        if prefix == "env":
            # 環境変数: ドット区切りを結合してキーとする
            env_key = ".".join(path)
            return os.environ.get(env_key, ref)

        # flow / ctx → ctx 辞書を参照
        current: Any = ctx
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return ref  # 解決不能 → 元の文字列
        return current
