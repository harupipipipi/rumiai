"""
test_wave15c_handlers_system.py - Wave 15-C: kernel_handlers_system.py テスト

検証項目:
- _logger が StructuredLogger インスタンスであること
- MetricsCollector への記録が行われること
- 既存ハンドラの基本動作が壊れていないこと
- MetricsCollector エラーでもハンドラが失敗しないこと
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core_runtime.kernel_handlers_system import (
    KernelSystemHandlersMixin,
    _logger,
)
from core_runtime.logging_utils import StructuredLogger, reset_logger_cache
from core_runtime.metrics import get_metrics_collector, reset_metrics_collector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _StubMixin(KernelSystemHandlersMixin):
    """テスト用の具象クラス。Mixin が要求する self 属性をモックで提供する。"""

    def __init__(self):
        self.diagnostics = MagicMock()
        self.interface_registry = MagicMock()
        self.event_bus = MagicMock()
        self.lifecycle = MagicMock()
        self.install_journal = MagicMock()
        self._flow = None
        self._now_ts = MagicMock(return_value="2026-01-01T00:00:00Z")

    # _resolve_value / _resolve_args は KernelCore 側で定義されるヘルパー
    def _resolve_value(self, value, ctx):
        return value

    def _resolve_args(self, args, ctx):
        return args


@pytest.fixture()
def mixin():
    return _StubMixin()


@pytest.fixture(autouse=True)
def _reset_metrics():
    """各テストの前後で MetricsCollector をリセットする。"""
    reset_metrics_collector()
    yield
    reset_metrics_collector()


# ---------------------------------------------------------------------------
# 1. _logger が StructuredLogger であること
# ---------------------------------------------------------------------------

class TestLoggerInstance:
    def test_logger_is_structured_logger(self):
        assert isinstance(_logger, StructuredLogger)

    def test_logger_name(self):
        assert _logger.name == "rumi.kernel.handlers.system"


# ---------------------------------------------------------------------------
# 2. _h_security_init
# ---------------------------------------------------------------------------

class TestSecurityInit:
    def test_success(self, mixin):
        result = mixin._h_security_init({}, {})
        assert result["_kernel_step_status"] == "success"

    def test_strict_mode_in_ctx(self, mixin):
        ctx = {}
        mixin._h_security_init({"strict_mode": False}, ctx)
        assert ctx["_strict_mode"] is False

    def test_exception_returns_failed(self, mixin):
        mixin.diagnostics.record_step.side_effect = RuntimeError("boom")
        result = mixin._h_security_init({}, {})
        assert result["_kernel_step_status"] == "failed"
        assert "boom" in result["_kernel_step_meta"]["error"]


# ---------------------------------------------------------------------------
# 3. _h_docker_check
# ---------------------------------------------------------------------------

class TestDockerCheck:
    def test_docker_available(self, mixin):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("core_runtime.kernel_handlers_system.subprocess.run", return_value=mock_result):
            ctx = {}
            result = mixin._h_docker_check({}, ctx)
        assert result["_kernel_step_status"] == "success"
        assert result["_kernel_step_meta"]["docker_available"] is True
        assert ctx["_docker_available"] is True
        # MetricsCollector に gauge が記録されていること
        snap = get_metrics_collector().snapshot()
        assert "docker.available" in snap["gauges"]
        gauge_val = snap["gauges"]["docker.available"][0]["value"]
        assert gauge_val == 1.0

    def test_docker_not_available_required(self, mixin):
        with patch("core_runtime.kernel_handlers_system.subprocess.run",
                    side_effect=FileNotFoundError("no docker")):
            ctx = {}
            result = mixin._h_docker_check({"required": True}, ctx)
        assert result["_kernel_step_status"] == "failed"
        snap = get_metrics_collector().snapshot()
        assert snap["gauges"]["docker.available"][0]["value"] == 0.0

    def test_docker_not_available_not_required(self, mixin):
        with patch("core_runtime.kernel_handlers_system.subprocess.run",
                    side_effect=FileNotFoundError("no docker")):
            ctx = {}
            result = mixin._h_docker_check({"required": False}, ctx)
        assert result["_kernel_step_status"] == "success"
        assert ctx["_docker_available"] is False


# ---------------------------------------------------------------------------
# 4. _h_approval_init
# ---------------------------------------------------------------------------

class TestApprovalInit:
    def test_success(self, mixin):
        mock_am = MagicMock()
        with patch("core_runtime.kernel_handlers_system.initialize_approval_manager"), \
             patch("core_runtime.kernel_handlers_system.get_approval_manager", return_value=mock_am):
            ctx = {}
            result = mixin._h_approval_init({}, ctx)
        assert result["_kernel_step_status"] == "success"
        assert ctx["approval_manager"] is mock_am

    def test_import_error_returns_failed(self, mixin):
        with patch.dict("sys.modules", {"core_runtime.approval_manager": None}):
            ctx = {}
            result = mixin._h_approval_init({}, ctx)
        assert result["_kernel_step_status"] == "failed"


# ---------------------------------------------------------------------------
# 5. _h_container_start_approved
# ---------------------------------------------------------------------------

class TestContainerStartApproved:
    def test_no_approved(self, mixin):
        result = mixin._h_container_start_approved({}, {})
        assert result["_kernel_step_status"] == "success"
        assert result["_kernel_step_meta"]["started"] == 0

    def test_no_orchestrator(self, mixin):
        ctx = {"_packs_approved": ["pack-a"]}
        result = mixin._h_container_start_approved({}, ctx)
        assert result["_kernel_step_status"] == "skipped"

    def test_start_success(self, mixin):
        mock_co = MagicMock()
        mock_co.start_container.return_value = SimpleNamespace(success=True)
        ctx = {"_packs_approved": ["pack-a", "pack-b"], "container_orchestrator": mock_co}
        result = mixin._h_container_start_approved({}, ctx)
        assert result["_kernel_step_status"] == "success"
        assert result["_kernel_step_meta"]["started"] == ["pack-a", "pack-b"]
        # MetricsCollector 検証
        snap = get_metrics_collector().snapshot()
        assert snap["counters"]["container.start.success"][0]["value"] == 2
        assert snap["counters"]["container.start.failure"][0]["value"] == 0

    def test_start_partial_failure(self, mixin):
        mock_co = MagicMock()
        mock_co.start_container.side_effect = [
            SimpleNamespace(success=True),
            RuntimeError("container error"),
        ]
        ctx = {"_packs_approved": ["pack-a", "pack-b"], "container_orchestrator": mock_co}
        result = mixin._h_container_start_approved({}, ctx)
        assert len(result["_kernel_step_meta"]["started"]) == 1
        assert len(result["_kernel_step_meta"]["failed"]) == 1


# ---------------------------------------------------------------------------
# 6. _h_component_discover
# ---------------------------------------------------------------------------

class TestComponentDiscover:
    def test_exception_returns_failed(self, mixin):
        with patch("core_runtime.kernel_handlers_system.get_registry",
                    side_effect=ImportError("no registry")):
            ctx = {"_packs_approved": []}
            result = mixin._h_component_discover({}, ctx)
        assert result["_kernel_step_status"] == "failed"


# ---------------------------------------------------------------------------
# 7. _h_mounts_init / _h_registry_load エラーパスのロガー
# ---------------------------------------------------------------------------

class TestMountsInitErrorLogging:
    def test_error_returns_none(self, mixin):
        with patch("core_runtime.kernel_handlers_system.Path"):
            # backend_core が無い環境では ImportError
            result = mixin._h_mounts_init({}, {})
        assert result is None
        mixin.diagnostics.record_step.assert_called_once()


class TestRegistryLoadErrorLogging:
    def test_error_returns_none(self, mixin):
        result = mixin._h_registry_load({}, {})
        assert result is None
        mixin.diagnostics.record_step.assert_called_once()


# ---------------------------------------------------------------------------
# 8. ctx ハンドラの基本動作
# ---------------------------------------------------------------------------

class TestCtxHandlers:
    def test_ctx_set_and_get(self, mixin):
        ctx = {}
        mixin._h_ctx_set({"key": "color", "value": "blue"}, ctx)
        assert ctx["color"] == "blue"
        result = mixin._h_ctx_get({"key": "color"}, ctx)
        assert result["value"] == "blue"

    def test_ctx_get_missing_key_returns_failed(self, mixin):
        result = mixin._h_ctx_get({}, {})
        assert result["_kernel_step_status"] == "failed"


# ---------------------------------------------------------------------------
# 9. _h_noop
# ---------------------------------------------------------------------------

class TestNoop:
    def test_noop(self, mixin):
        result = mixin._h_noop({}, {})
        assert result["_kernel_step_status"] == "success"
        assert result["_kernel_step_meta"]["handler"] == "noop"


# ---------------------------------------------------------------------------
# 10. MetricsCollector エラーでもハンドラが失敗しないこと
# ---------------------------------------------------------------------------

class TestMetricsCollectorResilience:
    def test_docker_check_survives_metrics_error(self, mixin):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("core_runtime.kernel_handlers_system.subprocess.run", return_value=mock_result), \
             patch("core_runtime.kernel_handlers_system.get_metrics_collector",
                    side_effect=RuntimeError("metrics broken")):
            ctx = {}
            result = mixin._h_docker_check({}, ctx)
        # メトリクス障害があってもハンドラ自体は成功する
        assert result["_kernel_step_status"] == "success"

    def test_container_start_survives_metrics_error(self, mixin):
        mock_co = MagicMock()
        mock_co.start_container.return_value = SimpleNamespace(success=True)
        ctx = {"_packs_approved": ["p1"], "container_orchestrator": mock_co}
        with patch("core_runtime.kernel_handlers_system.get_metrics_collector",
                    side_effect=RuntimeError("metrics broken")):
            result = mixin._h_container_start_approved({}, ctx)
        assert result["_kernel_step_status"] == "success"


# ---------------------------------------------------------------------------
# 11. _register_system_handlers がハンドラ辞書を返すこと
# ---------------------------------------------------------------------------

class TestRegisterSystemHandlers:
    def test_returns_dict(self, mixin):
        handlers = mixin._register_system_handlers()
        assert isinstance(handlers, dict)
        assert "kernel:docker.check" in handlers
        assert "kernel:security.init" in handlers
        assert "kernel:noop" in handlers
        assert len(handlers) >= 20
