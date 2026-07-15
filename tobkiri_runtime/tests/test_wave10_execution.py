"""
test_wave10_execution.py - Wave 10-C: depends_on 実行時チェックのテスト

kernel_flow_execution.py の depends_on チェックロジックを直接テストする。
Kernel全体の起動は不要。モック/スタブで実行ループのみをテストする。
"""

from __future__ import annotations

import asyncio
import sys
import os
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock

# テスト対象のインポートパスを通す
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core_runtime.kernel_flow_execution import KernelFlowExecutionMixin


# ---------------------------------------------------------------------------
# Stub: Mixin を単独でインスタンス化するための最小スタブ
# ---------------------------------------------------------------------------

class _StubDiagnostics:
    """diagnostics の最小スタブ"""

    def __init__(self):
        self.records: List[Dict[str, Any]] = []

    def record_step(self, **kwargs):
        self.records.append(kwargs)

    def as_dict(self):
        return {"steps": self.records}


class _StubInterfaceRegistry:
    """interface_registry の最小スタブ"""

    def __init__(self):
        self._store: Dict[str, Any] = {}

    def get(self, key: str, strategy: str = "last"):
        if strategy == "all":
            v = self._store.get(key)
            return [v] if v is not None else []
        return self._store.get(key)

    def register(self, key: str, value: Any, meta: Any = None):
        self._store[key] = value

    def list(self):
        return self._store


class _FakeKernel(KernelFlowExecutionMixin):
    """
    Mixin のメソッドを呼び出すための最小 Kernel スタブ。
    Mixin が期待する self 属性を定義する。
    """

    def __init__(self):
        self.diagnostics = _StubDiagnostics()
        self.interface_registry = _StubInterfaceRegistry()
        self.config = MagicMock()
        self.event_bus = MagicMock()
        self._flow = None
        self._executor = None
        self._flow_converter = MagicMock()
        self._variable_resolver = MagicMock()

    def _build_kernel_context(self) -> Dict[str, Any]:
        return {}

    def _resolve_value(self, value: Any, ctx: Dict[str, Any], depth: int = 0) -> Any:
        return value

    def _resolve_handler(self, handler: str, args: Any = None):
        return None

    def _vocab_normalize_output(self, unwrapped, step, ctx):
        return unwrapped


# ---------------------------------------------------------------------------
# Helper: step dict を作る
# ---------------------------------------------------------------------------

def _make_step(
    step_id: str,
    handler: str = "test:noop",
    depends_on: Optional[List[str]] = None,
    step_type: str = "handler",
    when: Optional[str] = None,
) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": step_id,
        "type": step_type,
        "handler": handler,
    }
    if when is not None:
        d["when"] = when
    if depends_on is not None:
        d["depends_on"] = depends_on
    return d


def _run_async(coro):
    """asyncio.run のヘルパー（Python 3.9+ 互換）"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ===========================================================================
# Tests: _check_depends_on ヘルパーメソッド
# ===========================================================================

class TestCheckDependsOn:
    """_check_depends_on メソッドの単体テスト"""

    def setup_method(self):
        self.kernel = _FakeKernel()

    def test_depends_on_none_returns_true(self):
        """depends_on が None → チェックスキップ、実行許可"""
        step = _make_step("s1", depends_on=None)
        ok, missing = self.kernel._check_depends_on(step, set())
        assert ok is True
        assert missing == []

    def test_depends_on_empty_list_returns_true(self):
        """depends_on が空リスト → チェックスキップ、実行許可"""
        step = _make_step("s1", depends_on=[])
        ok, missing = self.kernel._check_depends_on(step, set())
        assert ok is True
        assert missing == []

    def test_depends_on_satisfied(self):
        """depends_on の全IDが executed_ids に含まれる → 実行許可"""
        step = _make_step("s2", depends_on=["s1"])
        ok, missing = self.kernel._check_depends_on(step, {"s1"})
        assert ok is True
        assert missing == []

    def test_depends_on_multiple_satisfied(self):
        """複数の depends_on が全て満たされる"""
        step = _make_step("s3", depends_on=["s1", "s2"])
        ok, missing = self.kernel._check_depends_on(step, {"s1", "s2", "s0"})
        assert ok is True
        assert missing == []

    def test_depends_on_not_satisfied(self):
        """depends_on の一部が未実行 → 実行不可 + missing リスト"""
        step = _make_step("s3", depends_on=["s1", "s2"])
        ok, missing = self.kernel._check_depends_on(step, {"s1"})
        assert ok is False
        assert missing == ["s2"]

    def test_depends_on_all_missing(self):
        """depends_on が全て未実行"""
        step = _make_step("s2", depends_on=["s1", "s0"])
        ok, missing = self.kernel._check_depends_on(step, set())
        assert ok is False
        assert set(missing) == {"s1", "s0"}

    def test_depends_on_self_reference(self):
        """depends_on に自分自身 → 未充足（自分はまだ executed ではない）"""
        step = _make_step("s1", depends_on=["s1"])
        ok, missing = self.kernel._check_depends_on(step, set())
        assert ok is False
        assert missing == ["s1"]

    def test_getattr_fallback_no_depends_on_attr(self):
        """depends_on 属性を持たないオブジェクト → None として扱い実行許可"""

        class _BareStep:
            id = "bare"
            type = "handler"
            # depends_on 属性なし

        step = _BareStep()
        ok, missing = self.kernel._check_depends_on(step, set())
        assert ok is True
        assert missing == []

    def test_getattr_fallback_dict_without_depends_on_key(self):
        """dict に depends_on キーがない → None として扱い実行許可"""
        step = {"id": "s1", "type": "handler", "handler": "test:noop"}
        ok, missing = self.kernel._check_depends_on(step, set())
        assert ok is True
        assert missing == []


# ===========================================================================
# Tests: _get_step_depends_on 静的メソッド
# ===========================================================================

class TestGetStepDependsOn:
    """_get_step_depends_on 静的メソッドのテスト"""

    def test_dict_with_depends_on(self):
        step = {"id": "s1", "depends_on": ["a", "b"]}
        result = KernelFlowExecutionMixin._get_step_depends_on(step)
        assert result == ["a", "b"]

    def test_dict_without_depends_on(self):
        step = {"id": "s1"}
        result = KernelFlowExecutionMixin._get_step_depends_on(step)
        assert result is None

    def test_object_with_depends_on(self):
        class _Step:
            depends_on = ["x"]
        result = KernelFlowExecutionMixin._get_step_depends_on(_Step())
        assert result == ["x"]

    def test_object_without_depends_on(self):
        class _Step:
            id = "s1"
        result = KernelFlowExecutionMixin._get_step_depends_on(_Step())
        assert result is None


# ===========================================================================
# Tests: _execute_steps_async 統合テスト
# ===========================================================================

class TestExecuteStepsAsyncDependsOn:
    """_execute_steps_async でのdepends_onチェック統合テスト"""

    def setup_method(self):
        self.kernel = _FakeKernel()
        self.executed_handlers: List[str] = []

    def _register_handler(self, handler_key: str):
        """テスト用ハンドラを登録"""
        executed = self.executed_handlers

        def _handler(args, ctx):
            executed.append(handler_key)
            return {"output": "ok"}

        self.kernel.interface_registry.register(handler_key, _handler)

    def test_depends_on_satisfied_executes(self):
        """A(no deps) → B(depends_on=[A]) : B が実行される"""
        self._register_handler("test:a")
        self._register_handler("test:b")

        steps = [
            _make_step("A", handler="test:a"),
            _make_step("B", handler="test:b", depends_on=["A"]),
        ]
        ctx = {"_flow_defaults": {"fail_soft": True}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert "test:a" in self.executed_handlers
        assert "test:b" in self.executed_handlers

    def test_depends_on_not_satisfied_skips_fail_soft(self):
        """B(depends_on=[A]) だが A が存在しない → B スキップ (fail_soft)"""
        self._register_handler("test:b")

        steps = [
            _make_step("B", handler="test:b", depends_on=["A"]),
        ]
        ctx = {"_flow_defaults": {"fail_soft": True}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert "test:b" not in self.executed_handlers
        # diagnostics にスキップ記録があること
        skip_records = [
            r for r in self.kernel.diagnostics.records
            if "depends_on" in r.get("step_id", "")
        ]
        assert len(skip_records) > 0
        assert skip_records[0]["status"] == "skipped"

    def test_depends_on_not_satisfied_aborts_strict(self):
        """B(depends_on=[A]) だが A が存在しない + fail_soft=False → abort"""
        self._register_handler("test:b")
        self._register_handler("test:c")

        steps = [
            _make_step("B", handler="test:b", depends_on=["A"]),
            _make_step("C", handler="test:c"),
        ]
        ctx = {"_flow_defaults": {"fail_soft": False}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert "test:b" not in self.executed_handlers
        # strict モードなので C も実行されない
        assert "test:c" not in self.executed_handlers
        # diagnostics に abort 記録があること
        abort_records = [
            r for r in self.kernel.diagnostics.records
            if "depends_on.abort" in r.get("step_id", "")
        ]
        assert len(abort_records) > 0
        assert abort_records[0]["status"] == "failed"

    def test_depends_on_none_no_overhead(self):
        """depends_on=None のステップは即座に通過して実行される"""
        self._register_handler("test:a")

        steps = [
            _make_step("A", handler="test:a"),  # depends_on なし
        ]
        ctx = {"_flow_defaults": {"fail_soft": True}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert "test:a" in self.executed_handlers

    def test_chain_dependency(self):
        """A → B(depends_on=[A]) → C(depends_on=[B]) : 全て実行される"""
        self._register_handler("test:a")
        self._register_handler("test:b")
        self._register_handler("test:c")

        steps = [
            _make_step("A", handler="test:a"),
            _make_step("B", handler="test:b", depends_on=["A"]),
            _make_step("C", handler="test:c", depends_on=["B"]),
        ]
        ctx = {"_flow_defaults": {"fail_soft": True}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert self.executed_handlers == ["test:a", "test:b", "test:c"]

    def test_chain_dependency_broken_in_middle(self):
        """A なし → B(depends_on=[A]) スキップ → C(depends_on=[B]) スキップ"""
        self._register_handler("test:b")
        self._register_handler("test:c")

        steps = [
            _make_step("B", handler="test:b", depends_on=["A"]),
            _make_step("C", handler="test:c", depends_on=["B"]),
        ]
        ctx = {"_flow_defaults": {"fail_soft": True}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert "test:b" not in self.executed_handlers
        assert "test:c" not in self.executed_handlers

    def test_diamond_dependency(self):
        """A → B(dep A), C(dep A) → D(dep B,C) : 全て実行"""
        self._register_handler("test:a")
        self._register_handler("test:b")
        self._register_handler("test:c")
        self._register_handler("test:d")

        steps = [
            _make_step("A", handler="test:a"),
            _make_step("B", handler="test:b", depends_on=["A"]),
            _make_step("C", handler="test:c", depends_on=["A"]),
            _make_step("D", handler="test:d", depends_on=["B", "C"]),
        ]
        ctx = {"_flow_defaults": {"fail_soft": True}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert self.executed_handlers == ["test:a", "test:b", "test:c", "test:d"]

    def test_no_depends_on_key_in_step_dict(self):
        """ステップdictに depends_on キーがない → 通常実行"""
        self._register_handler("test:a")

        steps = [
            {"id": "A", "type": "handler", "handler": "test:a"},
        ]
        ctx = {"_flow_defaults": {"fail_soft": True}}
        _run_async(self.kernel._execute_steps_async(steps, ctx))

        assert "test:a" in self.executed_handlers
