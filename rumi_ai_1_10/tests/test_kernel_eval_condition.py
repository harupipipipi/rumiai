"""
test_kernel_eval_condition.py - KernelCore._eval_condition ユニットテスト

対象: core_runtime/kernel_core.py の _eval_condition メソッド
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

from core_runtime.kernel_core import KernelCore
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


class TestEvalConditionEquality(unittest.TestCase):
    """== / != 演算子の条件評価"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_simple_equality(self):
        """'value == expected' で左辺が一致すれば True"""
        ctx = {"status": "ready"}
        result = self.kc._eval_condition("$ctx.status == ready", ctx)
        self.assertTrue(result)

    def test_simple_inequality(self):
        """'value != expected' で左辺が異なれば True"""
        ctx = {"status": "ready"}
        result = self.kc._eval_condition("$ctx.status != stopped", ctx)
        self.assertTrue(result)

    def test_equality_false(self):
        """'value == wrong' で左辺が不一致なら False"""
        ctx = {"status": "ready"}
        result = self.kc._eval_condition("$ctx.status == wrong", ctx)
        self.assertFalse(result)


class TestEvalConditionBoolFallback(unittest.TestCase):
    """演算子なしの暗黙ブール評価"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_truthy_string(self):
        """非空文字列は True"""
        ctx = {"flag": "some_value"}
        result = self.kc._eval_condition("$ctx.flag", ctx)
        self.assertTrue(result)

    def test_falsy_empty(self):
        """空文字列は False"""
        ctx = {"flag": ""}
        result = self.kc._eval_condition("$ctx.flag", ctx)
        self.assertFalse(result)

    def test_falsy_none(self):
        """None は False"""
        ctx = {"flag": None}
        result = self.kc._eval_condition("$ctx.flag", ctx)
        self.assertFalse(result)


class TestEvalConditionEdge(unittest.TestCase):
    """エッジケース"""

    def setUp(self):
        self.kc = _make_kernel()

    def test_unsupported_operator(self):
        """'value > 5' のような未サポート演算子は暗黙ブール評価にフォールバック

        _CONDITION_OP_RE は == / != のみマッチするため、
        '>' はマッチせず文字列全体が _resolve_value に渡されブール評価される。
        未解決の参照文字列は truthy（非空文字列）なので True が返る。
        """
        ctx = {"value": 10}
        # "$ctx.value > 5" は演算子マッチしないので文字列として truthy
        result = self.kc._eval_condition("$ctx.value > 5", ctx)
        # 文字列 "10 > 5" ではなく、_resolve_value の結果が整数10なら bool(10)=True
        # もしくは未解決なら文字列として truthy → いずれにしても True
        self.assertTrue(result)

    def test_variable_resolution(self):
        """'$ctx.key == expected' で変数解決後に比較"""
        ctx = {"key": "expected"}
        result = self.kc._eval_condition("$ctx.key == expected", ctx)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
