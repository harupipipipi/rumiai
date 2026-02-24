"""
test_wave15b_flow_execution.py - Wave 15-B: kernel_flow_execution.py 基盤モジュール統合テスト

テスト対象:
- logging → get_structured_logger 移行
- Profiler でFlow/ステップ計測
- MetricsCollector でステップ成功/失敗/Flow完了カウント
- 既存動作（depends_on, chain depth, 条件評価等）の非破壊検証
"""

from __future__ import annotations

import asyncio
import types
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import MagicMock, patch

import pytest

from core_runtime.logging_utils import StructuredLogger, get_structured_logger
from core_runtime.profiling import Profiler, get_profiler, reset_profiler
from core_runtime.metrics import MetricsCollector, get_metrics_collector, reset_metrics_collector
from core_runtime.kernel_flow_execution import (
    KernelFlowExecutionMixin,
    MAX_FLOW_CHAIN_DEPTH,
    _logger as module_logger,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def _reset_profiler_and_metrics():
    """各テスト前後で Profiler / MetricsCollector シングルトンをリセットする。"""
    reset_profiler()
    reset_metrics_collector()
    yield
    reset_profiler()
    reset_metrics_collector()


# ============================================================
# Test helpers — minimal mock kernel
# ============================================================

class MockDiagnostics:
    """diagnostics.record_step を記録するだけのモック。"""

    def __init__(self) -> None:
        self.steps: List[Dict[str, Any]] = []

    def record_step(self, **kwargs: Any) -> None:
        self.steps.append(kwargs)

    def as_dict(self) -> Dict[str, Any]:
        return {"steps": list(self.steps)}


class MockInterfaceRegistry:
    """InterfaceRegistry の最小モック。"""

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def register(self, key: str, value: Any, meta: Any = None) -> None:
        self._store[key] = value

    def get(self, key: str, strategy: str = "last") -> Any:
        if strategy == "all":
            val = self._store.get(key)
            return [val] if val is not None else []
        return self._store.get(key)

    def list(self) -> Dict[str, Any]:
        return dict(self._store)


class TestKernel(KernelFlowExecutionMixin):
    """テスト用の最小 Kernel。Mixin が依存する属性/メソッドを全て提供する。"""

    def __init__(self) -> None:
        self.diagnostics = MockDiagnostics()
        self.interface_registry = MockInterfaceRegistry()
        self._flow: Optional[Dict[str, Any]] = None
        self._executor = ThreadPoolExecutor(max_workers=2)

    def _build_kernel_context(self) -> Dict[str, Any]:
        return {}

    def _resolve_value(self, value: Any, ctx: Dict[str, Any], depth: int = 0) -> Any:
        if isinstance(value, str) and value in ctx:
            return ctx[value]
        return value

    def _resolve_handler(self, handler: str, args: Any = None) -> Any:
        return None

    def load_flow(self, path: Any = None) -> Dict[str, Any]:
        return self._flow or {}

    def load_user_flows(self, path: Any = None) -> None:
        pass

    def _load_single_flow(self, flow_path: Any) -> Dict[str, Any]:
        return {}

    def _vocab_normalize_output(self, unwrapped: Any, step: Any, ctx: Any) -> Any:
        return unwrapped


def _run_async(coro):
    """ヘルパー: coroutine を同期的に実行する。"""
    return asyncio.run(coro)


# ============================================================
# 1. Logger 型検証
# ============================================================

class TestLoggerMigration:
    """logging → get_structured_logger 移行の検証。"""

    def test_module_logger_is_structured_logger(self):
        """_logger が StructuredLogger インスタンスであること。"""
        assert isinstance(module_logger, StructuredLogger)

    def test_module_logger_name(self):
        """_logger の name が正しいこと。"""
        assert module_logger.name == "rumi.kernel.flow_execution"

    def test_logger_has_warning_method(self):
        """StructuredLogger に warning メソッドがあること。"""
        assert callable(getattr(module_logger, "warning", None))

    def test_logger_has_debug_method(self):
        """StructuredLogger に debug メソッドがあること。"""
        assert callable(getattr(module_logger, "debug", None))


# ============================================================
# 2. Profiler 計測検証
# ============================================================

class TestProfilerIntegration:
    """Profiler によるFlow/ステップ計測の検証。"""

    def test_flow_execution_records_profiler_data(self):
        """_execute_flow_internal で flow.{flow_id} が Profiler に記録されること。"""
        kernel = TestKernel()
        kernel.interface_registry.register("flow.test_flow", {"steps": []})

        _run_async(kernel._execute_flow_internal("test_flow"))

        profiler = get_profiler()
        stats = profiler.get_stats("flow.test_flow")
        assert stats is not None
        assert stats["count"] == 1
        assert stats["total_time"] >= 0

    def test_step_execution_records_profiler_data(self):
        """_execute_handler_step_async で step.{handler_key} が Profiler に記録されること。"""
        kernel = TestKernel()

        def mock_handler(args, ctx):
            return {"output": "ok"}

        kernel.interface_registry.register("my.handler", mock_handler)
        step = {"handler": "my.handler", "output": "result"}
        ctx = {"_flow_id": "test", "_flow_execution_id": "exec1"}

        _run_async(kernel._execute_handler_step_async(step, ctx))

        profiler = get_profiler()
        stats = profiler.get_stats("step.my.handler")
        assert stats is not None
        assert stats["count"] == 1

    def test_step_error_still_records_profiler_data(self):
        """ステップが例外を投げても Profiler に記録されること。"""
        kernel = TestKernel()

        def failing_handler(args, ctx):
            raise ValueError("boom")

        kernel.interface_registry.register("fail.handler", failing_handler)
        step = {"handler": "fail.handler"}
        ctx = {"_flow_id": "test", "_flow_execution_id": "exec1"}

        with pytest.raises(ValueError, match="boom"):
            _run_async(kernel._execute_handler_step_async(step, ctx))

        profiler = get_profiler()
        stats = profiler.get_stats("step.fail.handler")
        assert stats is not None
        assert stats["count"] == 1

    def test_profiler_error_does_not_break_flow(self):
        """Profiler の _record が例外を投げても Flow 実行は成功すること。"""
        kernel = TestKernel()
        kernel.interface_registry.register("flow.safe_flow", {"steps": []})

        with patch.object(Profiler, "_record", side_effect=RuntimeError("profiler broken")):
            result = _run_async(kernel._execute_flow_internal("safe_flow"))

        # Flow は正常に完了しているはず
        assert "_error" not in result

    def test_multiple_flows_accumulate_profiler_stats(self):
        """複数回の Flow 実行で Profiler の count が累積すること。"""
        kernel = TestKernel()
        kernel.interface_registry.register("flow.multi", {"steps": []})

        _run_async(kernel._execute_flow_internal("multi"))
        _run_async(kernel._execute_flow_internal("multi"))
        _run_async(kernel._execute_flow_internal("multi"))

        stats = get_profiler().get_stats("flow.multi")
        assert stats is not None
        assert stats["count"] == 3


# ============================================================
# 3. MetricsCollector 計測検証
# ============================================================

class TestMetricsIntegration:
    """MetricsCollector によるカウント記録の検証。"""

    def test_flow_complete_metric_recorded(self):
        """Flow 完了時に flow.execution.complete が記録されること。"""
        kernel = TestKernel()
        kernel.interface_registry.register("flow.metric_flow", {"steps": []})

        _run_async(kernel._execute_flow_internal("metric_flow"))

        snap = get_metrics_collector().snapshot()
        counters = snap["counters"]
        assert "flow.execution.complete" in counters
        entries = counters["flow.execution.complete"]
        assert any(e["labels"].get("flow_id") == "metric_flow" for e in entries)

    def test_step_success_metric_recorded(self):
        """ステップ成功時に flow.step.success が記録されること。"""
        kernel = TestKernel()

        def ok_handler(args, ctx):
            return "done"

        kernel.interface_registry.register("ok.handler", ok_handler)
        step = {"handler": "ok.handler"}
        ctx = {"_flow_id": "t", "_flow_execution_id": "e1"}

        _run_async(kernel._execute_handler_step_async(step, ctx))

        snap = get_metrics_collector().snapshot()
        counters = snap["counters"]
        assert "flow.step.success" in counters
        entries = counters["flow.step.success"]
        assert any(e["labels"].get("handler") == "ok.handler" for e in entries)

    def test_step_error_metric_recorded(self):
        """ステップ失敗時に flow.step.error が記録されること。"""
        kernel = TestKernel()

        def bad_handler(args, ctx):
            raise RuntimeError("fail")

        kernel.interface_registry.register("bad.handler", bad_handler)
        step = {"handler": "bad.handler"}
        ctx = {"_flow_id": "t", "_flow_execution_id": "e1"}

        with pytest.raises(RuntimeError):
            _run_async(kernel._execute_handler_step_async(step, ctx))

        snap = get_metrics_collector().snapshot()
        counters = snap["counters"]
        assert "flow.step.error" in counters
        entries = counters["flow.step.error"]
        assert any(e["labels"].get("handler") == "bad.handler" for e in entries)

    def test_metrics_error_does_not_break_step(self):
        """MetricsCollector の increment が例外を投げてもステップは成功すること。"""
        kernel = TestKernel()

        def ok_handler(args, ctx):
            return "done"

        kernel.interface_registry.register("safe.handler", ok_handler)
        step = {"handler": "safe.handler"}
        ctx = {"_flow_id": "t", "_flow_execution_id": "e1"}

        with patch.object(MetricsCollector, "increment", side_effect=RuntimeError("metrics broken")):
            result_ctx, result_val = _run_async(kernel._execute_handler_step_async(step, ctx))

        # ステップは正常に完了しているはず
        assert result_val == "done"

    def test_flow_not_found_does_not_record_complete_metric(self):
        """Flow が見つからない場合は flow.execution.complete が記録されないこと。"""
        kernel = TestKernel()

        result = _run_async(kernel._execute_flow_internal("nonexistent"))

        assert "_error" in result
        snap = get_metrics_collector().snapshot()
        counters = snap["counters"]
        assert "flow.execution.complete" not in counters

    def test_step_success_count_accumulates(self):
        """複数ステップ成功で flow.step.success の count が累積すること。"""
        kernel = TestKernel()

        def handler(args, ctx):
            return "ok"

        kernel.interface_registry.register("acc.handler", handler)

        for _ in range(5):
            step = {"handler": "acc.handler"}
            ctx = {"_flow_id": "t", "_flow_execution_id": "e1"}
            _run_async(kernel._execute_handler_step_async(step, ctx))

        snap = get_metrics_collector().snapshot()
        entries = snap["counters"]["flow.step.success"]
        total = sum(e["value"] for e in entries if e["labels"].get("handler") == "acc.handler")
        assert total == 5


# ============================================================
# 4. depends_on 基本動作
# ============================================================

class TestDependsOn:
    """depends_on の基本動作が壊れていないことの検証。"""

    def test_get_step_depends_on_dict(self):
        """dict ステップから depends_on を取得できること。"""
        step = {"id": "s1", "depends_on": ["s0"]}
        assert KernelFlowExecutionMixin._get_step_depends_on(step) == ["s0"]

    def test_get_step_depends_on_object(self):
        """オブジェクトステップから depends_on を取得できること。"""
        step = types.SimpleNamespace(id="s1", depends_on=["s0"])
        assert KernelFlowExecutionMixin._get_step_depends_on(step) == ["s0"]

    def test_get_step_depends_on_missing(self):
        """depends_on が存在しないステップで None が返ること。"""
        step = {"id": "s1"}
        assert KernelFlowExecutionMixin._get_step_depends_on(step) is None

    def test_check_depends_on_no_deps(self):
        """depends_on なし → (True, [])。"""
        kernel = TestKernel()
        ok, missing = kernel._check_depends_on({"id": "s1"}, set())
        assert ok is True
        assert missing == []

    def test_check_depends_on_all_satisfied(self):
        """全依存が満足 → (True, [])。"""
        kernel = TestKernel()
        step = {"id": "s2", "depends_on": ["s0", "s1"]}
        ok, missing = kernel._check_depends_on(step, {"s0", "s1"})
        assert ok is True
        assert missing == []

    def test_check_depends_on_missing(self):
        """依存が不足 → (False, [missing])。"""
        kernel = TestKernel()
        step = {"id": "s2", "depends_on": ["s0", "s1"]}
        ok, missing = kernel._check_depends_on(step, {"s0"})
        assert ok is False
        assert "s1" in missing

    def test_depends_on_skip_in_async_flow(self):
        """async flow で depends_on 不満足時にステップがスキップされること。"""
        kernel = TestKernel()

        def handler_a(args, ctx):
            return "a_result"

        kernel.interface_registry.register("handler.a", handler_a)

        steps = [
            {"id": "step_b", "handler": "handler.a", "depends_on": ["step_a"]},
        ]
        ctx = {"_flow_id": "test", "_flow_execution_id": "e1",
               "_flow_defaults": {"fail_soft": True}}

        result = _run_async(kernel._execute_steps_async(steps, ctx))

        # step_b は step_a が未実行なのでスキップされる
        skipped = [s for s in kernel.diagnostics.steps if "depends_on.skipped" in s.get("step_id", "")]
        assert len(skipped) >= 1


# ============================================================
# 5. Flow chain depth / recursive 検出
# ============================================================

class TestFlowChainAndRecursion:
    """Flow chain depth 制限と再帰検出の非破壊検証。"""

    def test_max_flow_chain_depth_value(self):
        """MAX_FLOW_CHAIN_DEPTH が 10 であること。"""
        assert MAX_FLOW_CHAIN_DEPTH == 10

    def test_chain_depth_limit(self):
        """call_stack が限界に達した場合にエラーが返ること。"""
        kernel = TestKernel()
        kernel.interface_registry.register("flow.deep", {"steps": []})
        fake_stack = [f"flow_{i}" for i in range(MAX_FLOW_CHAIN_DEPTH)]

        result = _run_async(
            kernel._execute_flow_internal("deep", context={"_flow_call_stack": fake_stack})
        )

        assert "_error" in result
        assert "depth limit" in result["_error"]

    def test_recursive_flow_detected(self):
        """再帰フローが検出されること。"""
        kernel = TestKernel()
        kernel.interface_registry.register("flow.loop", {"steps": []})

        result = _run_async(
            kernel._execute_flow_internal("loop", context={"_flow_call_stack": ["loop"]})
        )

        assert "_error" in result
        assert "Recursive" in result["_error"]


# ============================================================
# 6. 条件評価
# ============================================================

class TestEvalCondition:
    """_eval_condition の非破壊検証。"""

    def test_eq_match(self):
        """== 一致で True。"""
        kernel = TestKernel()
        ctx = {"status": "ok"}
        assert kernel._eval_condition("status == ok", ctx) is True

    def test_eq_mismatch(self):
        """== 不一致で False。"""
        kernel = TestKernel()
        ctx = {"status": "error"}
        assert kernel._eval_condition("status == ok", ctx) is False

    def test_neq_match(self):
        """!= で異なれば True。"""
        kernel = TestKernel()
        ctx = {"status": "error"}
        assert kernel._eval_condition("status != ok", ctx) is True

    def test_bool_true_conversion(self):
        """右辺 'true' が bool True に変換されること。"""
        kernel = TestKernel()
        ctx = {"flag": True}
        assert kernel._eval_condition("flag == true", ctx) is True

    def test_bool_false_conversion(self):
        """右辺 'false' が bool False に変換されること。"""
        kernel = TestKernel()
        ctx = {"flag": False}
        assert kernel._eval_condition("flag == false", ctx) is True

    def test_truthy_value(self):
        """演算子なしで truthy 値が True を返すこと。"""
        kernel = TestKernel()
        ctx = {"active": "yes"}
        assert kernel._eval_condition("active", ctx) is True


# ============================================================
# 7. handler step 基本動作
# ============================================================

class TestHandlerStepBasic:
    """_execute_handler_step_async の基本動作。"""

    def test_no_handler_key_returns_none(self):
        """handler キーなしで (ctx, None) が返ること。"""
        kernel = TestKernel()
        step = {}
        ctx = {}
        result_ctx, result_val = _run_async(kernel._execute_handler_step_async(step, ctx))
        assert result_val is None

    def test_handler_not_found_returns_none(self):
        """handler が見つからない場合に (ctx, None) が返ること。"""
        kernel = TestKernel()
        step = {"handler": "nonexistent.handler"}
        ctx = {}
        result_ctx, result_val = _run_async(kernel._execute_handler_step_async(step, ctx))
        assert result_val is None

    def test_handler_output_stored_in_ctx(self):
        """handler の出力が ctx[output] に格納されること。"""
        kernel = TestKernel()

        def my_handler(args, ctx):
            return {"value": 42}

        kernel.interface_registry.register("store.handler", my_handler)
        step = {"handler": "store.handler", "output": "my_result"}
        ctx = {"_flow_id": "t", "_flow_execution_id": "e1"}

        result_ctx, result_val = _run_async(kernel._execute_handler_step_async(step, ctx))
        assert result_ctx["my_result"] == {"value": 42}
