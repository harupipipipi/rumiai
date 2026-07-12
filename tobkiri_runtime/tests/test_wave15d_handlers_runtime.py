"""
test_wave15d_handlers_runtime.py - Wave 15-D handlers_runtime 統合テスト

kernel_handlers_runtime.py に追加された:
  - StructuredLogger (_logger)
  - MetricsCollector 計測
の動作を検証する。最低15テスト。
"""
from __future__ import annotations

import types
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_metrics():
    """各テスト後に MetricsCollector をリセット"""
    yield
    try:
        from core_runtime.metrics import reset_metrics_collector
        reset_metrics_collector()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_logger_cache():
    """各テスト後にロガーキャッシュをリセット"""
    yield
    try:
        from core_runtime.logging_utils import reset_logger_cache
        reset_logger_cache()
    except Exception:
        pass


# ------------------------------------------------------------------
# Mock helpers
# ------------------------------------------------------------------

class FakeDiagnostics:
    """diagnostics.record_step() を記録するフェイク"""

    def __init__(self):
        self.steps: List[Dict[str, Any]] = []

    def record_step(self, **kwargs):
        self.steps.append(kwargs)


class FakeInterfaceRegistry:
    """interface_registry.register() を記録するフェイク"""

    def __init__(self):
        self.registered: Dict[str, Any] = {}

    def register(self, key, value, meta=None):
        self.registered[key] = {"value": value, "meta": meta}

    def get(self, key, default=None):
        entry = self.registered.get(key)
        return entry["value"] if entry else default


class FakeExecutionResult:
    """python_file_executor の実行結果フェイク"""

    def __init__(self, success=True, output=None, error=None,
                 error_type=None, execution_mode="docker",
                 execution_time_ms=42.5, warnings=None):
        self.success = success
        self.output = output or {}
        self.error = error
        self.error_type = error_type
        self.execution_mode = execution_mode
        self.execution_time_ms = execution_time_ms
        self.warnings = warnings or []


class FakeGrant:
    """network grant のフェイク"""

    def to_dict(self):
        return {"pack_id": "test-pack", "allowed_domains": ["example.com"]}


def _build_mixin_instance():
    """KernelRuntimeHandlersMixin を独立インスタンスとして構築"""
    from core_runtime.kernel_handlers_runtime import KernelRuntimeHandlersMixin

    class FakeKernel(KernelRuntimeHandlersMixin):
        def __init__(self):
            self.diagnostics = FakeDiagnostics()
            self.interface_registry = FakeInterfaceRegistry()

        def _now_ts(self):
            return "2026-01-01T00:00:00Z"

        def _resolve_value(self, value, ctx):
            return value

        def _get_uds_proxy_manager(self):
            return None

        def _get_capability_proxy(self):
            return None

        def execute_flow_sync(self, flow_id, ctx, timeout=None):
            return {"status": "ok"}

    return FakeKernel()


# ==================================================================
# Test 1: _logger is a StructuredLogger instance
# ==================================================================

class TestLoggerInstance:
    def test_logger_is_structured_logger(self):
        from core_runtime.kernel_handlers_runtime import _logger
        from core_runtime.logging_utils import StructuredLogger
        assert isinstance(_logger, StructuredLogger)

    def test_logger_name(self):
        from core_runtime.kernel_handlers_runtime import _logger
        assert _logger.name == "rumi.kernel.handlers.runtime"


# ==================================================================
# Test: _h_flow_load_all logging + metrics
# ==================================================================

class TestFlowLoadAllLogging:

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_flow_load_all_success_logs_info(self, mock_mc, mock_logger):
        """成功時に _logger.info が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()

        # flow_loader / modifier のモック
        mock_flow_loader = MagicMock()
        mock_flow_loader.load_all_flows.return_value = {}
        mock_flow_loader.get_load_errors.return_value = []
        mock_flow_loader.get_skipped_flows.return_value = []

        mock_modifier_loader = MagicMock()
        mock_modifier_loader.load_all_modifiers.return_value = {}
        mock_modifier_loader.get_load_errors.return_value = []
        mock_modifier_loader.get_skipped_modifiers.return_value = []

        mock_applier = MagicMock()

        with patch("core_runtime.kernel_handlers_runtime.get_flow_loader",
                    return_value=mock_flow_loader, create=True) as p1, \
             patch("core_runtime.kernel_handlers_runtime.get_modifier_loader",
                    return_value=mock_modifier_loader, create=True) as p2, \
             patch("core_runtime.kernel_handlers_runtime.get_modifier_applier",
                    return_value=mock_applier, create=True) as p3, \
             patch("core_runtime.kernel_handlers_runtime.get_audit_logger",
                    return_value=MagicMock(), create=True) as p4:
            # 関数内 local import をパッチするには別の方法が必要
            pass

        # local import のため、直接的なパッチは難しい
        # flow_loader 等は関数内で from .flow_loader import get_flow_loader される
        # → モジュールレベルでパッチ
        with patch("core_runtime.flow_loader.get_flow_loader",
                    return_value=mock_flow_loader), \
             patch("core_runtime.flow_modifier.get_modifier_loader",
                    return_value=mock_modifier_loader), \
             patch("core_runtime.flow_modifier.get_modifier_applier",
                    return_value=mock_applier), \
             patch("core_runtime.audit_logger.get_audit_logger",
                    return_value=MagicMock()):
            result = kernel._h_flow_load_all({}, {})

        assert result["_kernel_step_status"] == "success"
        mock_logger.info.assert_called()
        # "Flow load completed" が含まれる呼び出しがあるか
        info_calls = [c for c in mock_logger.info.call_args_list
                      if "Flow load completed" in str(c)]
        assert len(info_calls) >= 1

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_flow_load_all_success_sets_gauge(self, mock_mc, mock_logger):
        """成功時に set_gauge("flows.registered", ...) が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()

        mock_flow_loader = MagicMock()
        mock_flow_loader.load_all_flows.return_value = {}
        mock_flow_loader.get_load_errors.return_value = []
        mock_flow_loader.get_skipped_flows.return_value = []

        mock_modifier_loader = MagicMock()
        mock_modifier_loader.load_all_modifiers.return_value = {}
        mock_modifier_loader.get_load_errors.return_value = []
        mock_modifier_loader.get_skipped_modifiers.return_value = []

        mock_applier = MagicMock()

        with patch("core_runtime.flow_loader.get_flow_loader",
                    return_value=mock_flow_loader), \
             patch("core_runtime.flow_modifier.get_modifier_loader",
                    return_value=mock_modifier_loader), \
             patch("core_runtime.flow_modifier.get_modifier_applier",
                    return_value=mock_applier), \
             patch("core_runtime.audit_logger.get_audit_logger",
                    return_value=MagicMock()):
            result = kernel._h_flow_load_all({}, {})

        assert result["_kernel_step_status"] == "success"
        mock_collector.set_gauge.assert_called_once_with("flows.registered", 0)

    @patch("core_runtime.kernel_handlers_runtime._logger")
    def test_flow_load_all_failure_logs_error(self, mock_logger):
        """失敗時に _logger.error が呼ばれる"""
        kernel = _build_mixin_instance()

        # flow_loader が例外を投げるケース
        with patch("core_runtime.flow_loader.get_flow_loader",
                    side_effect=RuntimeError("boom")):
            result = kernel._h_flow_load_all({}, {})

        assert result["_kernel_step_status"] == "failed"
        mock_logger.error.assert_called()
        error_calls = [c for c in mock_logger.error.call_args_list
                       if "Flow load failed" in str(c)]
        assert len(error_calls) >= 1


# ==================================================================
# Test: _h_python_file_call logging + metrics
# ==================================================================

class TestPythonFileCallLogging:

    @patch("core_runtime.kernel_handlers_runtime._logger")
    def test_python_file_call_missing_file_returns_failed(self, mock_logger):
        """file 引数なし時に failed を返す"""
        kernel = _build_mixin_instance()
        result = kernel._h_python_file_call({}, {})
        assert result["_kernel_step_status"] == "failed"

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_python_file_call_success_logs_start_and_complete(
        self, mock_mc, mock_logger
    ):
        """成功時に start と completed の info ログが出る"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()
        fake_result = FakeExecutionResult(success=True, execution_time_ms=100.0)

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fake_result

        with patch("core_runtime.python_file_executor.get_python_file_executor",
                    return_value=mock_executor):
            result = kernel._h_python_file_call(
                {"file": "test.py", "_step_id": "s1", "_phase": "test"}, {}
            )

        assert result["_kernel_step_status"] == "success"
        info_msgs = [str(c) for c in mock_logger.info.call_args_list]
        assert any("python_file_call start" in m for m in info_msgs)
        assert any("python_file_call completed" in m for m in info_msgs)

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_python_file_call_success_observes_duration(
        self, mock_mc, mock_logger
    ):
        """成功時に observe("python_file_call.duration_ms", ...) が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()
        fake_result = FakeExecutionResult(success=True, execution_time_ms=55.5)

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fake_result

        with patch("core_runtime.python_file_executor.get_python_file_executor",
                    return_value=mock_executor):
            kernel._h_python_file_call(
                {"file": "test.py", "_step_id": "s1", "_phase": "test"}, {}
            )

        mock_collector.observe.assert_called_once_with(
            "python_file_call.duration_ms", 55.5
        )

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_python_file_call_failure_logs_error(self, mock_mc, mock_logger):
        """失敗時に _logger.error が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()
        fake_result = FakeExecutionResult(
            success=False, error="timeout", error_type="timeout"
        )

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fake_result

        with patch("core_runtime.python_file_executor.get_python_file_executor",
                    return_value=mock_executor):
            result = kernel._h_python_file_call(
                {"file": "test.py", "_step_id": "s1", "_phase": "test"}, {}
            )

        assert result["_kernel_step_status"] == "failed"
        error_msgs = [str(c) for c in mock_logger.error.call_args_list]
        assert any("python_file_call failed" in m for m in error_msgs)

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_python_file_call_metrics_error_does_not_break_handler(
        self, mock_mc, mock_logger
    ):
        """MetricsCollector が例外を投げてもハンドラは成功する"""
        mock_collector = MagicMock()
        mock_collector.observe.side_effect = RuntimeError("metrics boom")
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()
        fake_result = FakeExecutionResult(success=True, execution_time_ms=10.0)

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fake_result

        with patch("core_runtime.python_file_executor.get_python_file_executor",
                    return_value=mock_executor):
            result = kernel._h_python_file_call(
                {"file": "test.py", "_step_id": "s1", "_phase": "test"}, {}
            )

        # メトリクスのエラーに関わらず成功
        assert result["_kernel_step_status"] == "success"

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_python_file_call_none_execution_time_skips_observe(
        self, mock_mc, mock_logger
    ):
        """execution_time_ms が None なら observe を呼ばない"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()
        fake_result = FakeExecutionResult(success=True, execution_time_ms=None)

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fake_result

        with patch("core_runtime.python_file_executor.get_python_file_executor",
                    return_value=mock_executor):
            kernel._h_python_file_call(
                {"file": "test.py", "_step_id": "s1", "_phase": "test"}, {}
            )

        mock_collector.observe.assert_not_called()


# ==================================================================
# Test: _h_network_grant logging + metrics
# ==================================================================

class TestNetworkGrantLogging:

    def test_network_grant_missing_pack_id(self):
        """pack_id なしで failed を返す"""
        kernel = _build_mixin_instance()
        result = kernel._h_network_grant({}, {})
        assert result["_kernel_step_status"] == "failed"

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_network_grant_success_logs_info(self, mock_mc, mock_logger):
        """成功時に _logger.info("Network access granted", ...) が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()

        mock_ngm = MagicMock()
        mock_ngm.grant_network_access.return_value = FakeGrant()

        with patch("core_runtime.network_grant_manager.get_network_grant_manager",
                    return_value=mock_ngm):
            result = kernel._h_network_grant(
                {"pack_id": "p1", "allowed_domains": ["example.com"]}, {}
            )

        assert result["_kernel_step_status"] == "success"
        info_msgs = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Network access granted" in m for m in info_msgs)

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_network_grant_success_increments_counter(self, mock_mc, mock_logger):
        """成功時に increment("network.grant.count") が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()

        mock_ngm = MagicMock()
        mock_ngm.grant_network_access.return_value = FakeGrant()

        with patch("core_runtime.network_grant_manager.get_network_grant_manager",
                    return_value=mock_ngm):
            kernel._h_network_grant(
                {"pack_id": "p1", "allowed_domains": ["example.com"]}, {}
            )

        mock_collector.increment.assert_called_once_with("network.grant.count")

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_network_grant_failure_logs_error(self, mock_mc, mock_logger):
        """例外時に _logger.error が呼ばれる"""
        mock_mc.return_value = MagicMock()

        kernel = _build_mixin_instance()

        with patch("core_runtime.network_grant_manager.get_network_grant_manager",
                    side_effect=RuntimeError("ngm boom")):
            result = kernel._h_network_grant(
                {"pack_id": "p1", "allowed_domains": ["example.com"]}, {}
            )

        assert result["_kernel_step_status"] == "failed"
        error_msgs = [str(c) for c in mock_logger.error.call_args_list]
        assert any("Network grant failed" in m for m in error_msgs)


# ==================================================================
# Test: _h_network_revoke logging + metrics
# ==================================================================

class TestNetworkRevokeLogging:

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_network_revoke_success_logs_info(self, mock_mc, mock_logger):
        """成功時に _logger.info("Network access revoked", ...) が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()

        mock_ngm = MagicMock()
        mock_ngm.revoke_network_access.return_value = True

        with patch("core_runtime.network_grant_manager.get_network_grant_manager",
                    return_value=mock_ngm):
            result = kernel._h_network_revoke({"pack_id": "p1"}, {})

        assert result["_kernel_step_status"] == "success"
        info_msgs = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Network access revoked" in m for m in info_msgs)

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_network_revoke_success_increments_counter(self, mock_mc, mock_logger):
        """成功時に increment("network.revoke.count") が呼ばれる"""
        mock_collector = MagicMock()
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()

        mock_ngm = MagicMock()
        mock_ngm.revoke_network_access.return_value = True

        with patch("core_runtime.network_grant_manager.get_network_grant_manager",
                    return_value=mock_ngm):
            kernel._h_network_revoke({"pack_id": "p1"}, {})

        mock_collector.increment.assert_called_once_with("network.revoke.count")

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_network_revoke_failure_logs_error(self, mock_mc, mock_logger):
        """例外時に _logger.error が呼ばれる"""
        mock_mc.return_value = MagicMock()

        kernel = _build_mixin_instance()

        with patch("core_runtime.network_grant_manager.get_network_grant_manager",
                    side_effect=RuntimeError("revoke boom")):
            result = kernel._h_network_revoke({"pack_id": "p1"}, {})

        assert result["_kernel_step_status"] == "failed"
        error_msgs = [str(c) for c in mock_logger.error.call_args_list]
        assert any("Network revoke failed" in m for m in error_msgs)


# ==================================================================
# Test: metrics resilience (additional)
# ==================================================================

class TestMetricsResilience:

    @patch("core_runtime.kernel_handlers_runtime._logger")
    @patch("core_runtime.kernel_handlers_runtime.get_metrics_collector")
    def test_flow_load_all_metrics_error_does_not_break(self, mock_mc, mock_logger):
        """flow_load_all で MetricsCollector 例外でもハンドラ成功"""
        mock_collector = MagicMock()
        mock_collector.set_gauge.side_effect = RuntimeError("gauge boom")
        mock_mc.return_value = mock_collector

        kernel = _build_mixin_instance()

        mock_flow_loader = MagicMock()
        mock_flow_loader.load_all_flows.return_value = {}
        mock_flow_loader.get_load_errors.return_value = []
        mock_flow_loader.get_skipped_flows.return_value = []

        mock_modifier_loader = MagicMock()
        mock_modifier_loader.load_all_modifiers.return_value = {}
        mock_modifier_loader.get_load_errors.return_value = []
        mock_modifier_loader.get_skipped_modifiers.return_value = []

        mock_applier = MagicMock()

        with patch("core_runtime.flow_loader.get_flow_loader",
                    return_value=mock_flow_loader), \
             patch("core_runtime.flow_modifier.get_modifier_loader",
                    return_value=mock_modifier_loader), \
             patch("core_runtime.flow_modifier.get_modifier_applier",
                    return_value=mock_applier), \
             patch("core_runtime.audit_logger.get_audit_logger",
                    return_value=MagicMock()):
            result = kernel._h_flow_load_all({}, {})

        assert result["_kernel_step_status"] == "success"
