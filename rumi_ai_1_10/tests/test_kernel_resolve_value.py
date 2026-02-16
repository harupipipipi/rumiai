"""
test_kernel_resolve_value.py - KernelCore._resolve_value ユニットテスト

対象: core_runtime/kernel_core.py の _resolve_value メソッド
全テストは mock ベースで外部依存なし。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.kernel_core import KernelCore, MAX_RESOLVE_DEPTH
from core_runtime.diagnostics import Diagnostics
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.event_bus import EventBus


def _make_kernel() -> KernelCore:
    """副作用を最小化した KernelCore を生成"""
    return KernelCore(
        diagnostics=Diagnostics(),
        interface_registry=InterfaceRegistry(),
        event_bus=EventBus(),
    )


class TestResolveValueLiteral(unittest.TestCase):
    """リテラル値の解決"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_literal_string(self):
        """変数参照を含まない文字列はそのまま返る"""
        ctx = {}
        result = self.kc._resolve_value("hello", ctx)
        self.assertEqual(result, "hello")


class TestResolveValueCtxRef(unittest.TestCase):
    """$ctx.xxx 参照の解決"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_ctx_reference(self):
        """$ctx.key で ctx['key'] の値が返る"""
        ctx = {"key": "resolved_value"}
        result = self.kc._resolve_value("$ctx.key", ctx)
        self.assertEqual(result, "resolved_value")


class TestResolveValueFlowRef(unittest.TestCase):
    """$flow.xxx 参照の解決"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_flow_reference(self):
        """$flow.step_id.output で前ステップの出力が返る

        Flow実行中は ctx[step_output_key] に結果が格納されるため、
        $flow.step_id は ctx 内の step_id キーを参照する。
        """
        ctx = {"step_id": {"output": "step_result"}}
        result = self.kc._resolve_value("$flow.step_id.output", ctx)
        self.assertEqual(result, "step_result")


class TestResolveValueRecursive(unittest.TestCase):
    """再帰的な値解決"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_nested_dict(self):
        """dict 内の変数参照が再帰的に解決される"""
        ctx = {"name": "rumi"}
        value = {"greeting": "$ctx.name", "literal": "fixed"}
        result = self.kc._resolve_value(value, ctx)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["greeting"], "rumi")
        self.assertEqual(result["literal"], "fixed")

    def test_nested_list(self):
        """list 内の変数参照が再帰的に解決される"""
        ctx = {"x": "alpha"}
        value = ["$ctx.x", "beta"]
        result = self.kc._resolve_value(value, ctx)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0], "alpha")
        self.assertEqual(result[1], "beta")


class TestResolveValueEdge(unittest.TestCase):
    """エッジケース"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_max_depth(self):
        """MAX_RESOLVE_DEPTH 超過で元の値を返す

        深さ制限を超えた場合、これ以上の再帰を行わず
        値をそのまま返す。
        """
        ctx = {"key": "val"}
        # _resolve_value(value, ctx, _depth) で _depth > MAX_RESOLVE_DEPTH の場合
        # 元の値がそのまま返ることを確認する
        # dict を深くネストさせて制限に到達させる
        deep = "$ctx.key"
        # MAX_RESOLVE_DEPTH + 1 の深さのネストされた dict を作る
        for _ in range(MAX_RESOLVE_DEPTH + 5):
            deep = {"inner": deep}
        result = self.kc._resolve_value(deep, ctx)
        # 最深部は解決されずに元の文字列のまま残るはず
        current = result
        for _ in range(MAX_RESOLVE_DEPTH + 5):
            self.assertIsInstance(current, dict)
            current = current["inner"]
        # 深さ超過部分は "$ctx.key" のまま（未解決）
        self.assertEqual(current, "$ctx.key")

    def test_missing_reference(self):
        """存在しない参照は元の文字列のまま返る"""
        ctx = {}
        result = self.kc._resolve_value("$ctx.nonexistent", ctx)
        # 存在しないキー → 元の文字列 "$ctx.nonexistent" が返る
        self.assertEqual(result, "$ctx.nonexistent")


if __name__ == "__main__":
    unittest.main()
