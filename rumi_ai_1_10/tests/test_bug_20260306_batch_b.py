"""
test_bug_20260306_batch_b.py

BUG-20260306-BATCH-B:
- 候補1: 初期化ハンドラのサイレント失敗修正
- 候補3: 遅延初期化の無限リトライ修正
"""
import logging
import types
from unittest.mock import MagicMock, patch, PropertyMock
import pytest


# ======================================================================
# Helpers: lightweight stub for KernelSystemHandlersMixin
# ======================================================================

def _make_handler_mixin():
    """
    KernelSystemHandlersMixin のインスタンスを模擬する。
    self.diagnostics, self.interface_registry, self.lifecycle を MagicMock で注入。
    """
    from core_runtime.kernel_handlers_system import KernelSystemHandlersMixin

    obj = object.__new__(KernelSystemHandlersMixin)
    obj.diagnostics = MagicMock()
    obj.interface_registry = MagicMock()
    obj.lifecycle = MagicMock()
    obj.event_bus = MagicMock()
    obj._now_ts = lambda: "2026-03-06T00:00:00Z"
    return obj


# ======================================================================
# Helpers: lightweight stub for KernelCore proxy methods
# ======================================================================

def _make_kernel_core_stub():
    """
    KernelCore の proxy 関連メソッドをテストするための軽量スタブ。
    __init__ を呼ばず、必要な属性だけ手動で設定する。
    """
    from core_runtime.kernel_core import KernelCore

    obj = object.__new__(KernelCore)
    obj.diagnostics = MagicMock()
    obj._capability_proxy = None
    obj._capability_proxy_init_failed = False
    obj._uds_proxy_manager = None
    obj._uds_proxy_init_failed = False
    return obj


# ======================================================================
# 候補1: ハンドラのサイレント失敗修正テスト
# ======================================================================

class TestMountsInitHandler:
    """_h_mounts_init のテスト"""

    @patch("core_runtime.kernel_handlers_system.Path")
    @patch("backend_core.ecosystem.mounts.initialize_mounts")
    @patch("backend_core.ecosystem.mounts.get_mount_manager")
    @patch("backend_core.ecosystem.mounts.DEFAULT_MOUNTS", {"default": True})
    def test_success_returns_mount_manager(self, mock_get_mm, mock_init, mock_path_cls):
        """正常系: mount manager オブジェクトが返ること"""
        mixin = _make_handler_mixin()
        mock_mm = MagicMock(name="mount_manager")
        mock_get_mm.return_value = mock_mm
        mock_path_inst = MagicMock()
        mock_path_inst.exists.return_value = True
        mock_path_cls.return_value = mock_path_inst

        result = mixin._h_mounts_init({"mounts_file": "test.json"}, {})
        assert result is mock_mm

    def test_failure_returns_step_status_failed(self):
        """異常系: _kernel_step_status='failed' を含む dict が返ること"""
        mixin = _make_handler_mixin()

        with patch.dict("sys.modules", {"backend_core": MagicMock(),
                                         "backend_core.ecosystem": MagicMock(),
                                         "backend_core.ecosystem.mounts": MagicMock(
                                             initialize_mounts=MagicMock(side_effect=RuntimeError("mount fail")),
                                             DEFAULT_MOUNTS={},
                                             get_mount_manager=MagicMock()
                                         )}):
            # Force exception inside the try block
            with patch("core_runtime.kernel_handlers_system.Path") as mock_path_cls:
                mock_path_inst = MagicMock()
                mock_path_inst.exists.return_value = True
                mock_path_cls.return_value = mock_path_inst
                # Make initialize_mounts raise
                import sys
                sys.modules["backend_core.ecosystem.mounts"].initialize_mounts.side_effect = RuntimeError("mount fail")

                result = mixin._h_mounts_init({"mounts_file": "test.json"}, {})

        assert isinstance(result, dict)
        assert result["_kernel_step_status"] == "failed"
        assert "mount fail" in result["_kernel_step_error"]
        assert result["_kernel_step_meta"]["handler"] == "kernel:mounts.init"
        # diagnostics と logger は呼ばれている
        mixin.diagnostics.record_step.assert_called()


class TestRegistryLoadHandler:
    """_h_registry_load のテスト"""

    def test_success_returns_registry(self):
        """正常系: registry オブジェクトが返ること"""
        mixin = _make_handler_mixin()
        mock_reg = MagicMock(name="registry")
        mock_reg.load_all_packs = MagicMock()

        mock_regmod = MagicMock()
        mock_Registry = MagicMock(return_value=mock_reg)

        with patch.dict("sys.modules", {
            "backend_core": MagicMock(),
            "backend_core.ecosystem": MagicMock(),
            "backend_core.ecosystem.registry": mock_regmod,
        }):
            mock_regmod.Registry = mock_Registry
            # Patch the import inside the handler
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (
                mock_regmod if name == "backend_core.ecosystem.registry" else __import__(name, *a, **kw)
            )):
                # Direct approach: mock the import machinery
                import importlib
                with patch.object(importlib, "import_module", return_value=mock_regmod):
                    # Simplest: just call with pre-populated sys.modules
                    result = mixin._h_registry_load({"ecosystem_dir": "eco"}, {})

        assert result is mock_reg

    def test_failure_returns_step_status_failed(self):
        """異常系: _kernel_step_status='failed' を含む dict が返ること"""
        mixin = _make_handler_mixin()

        mock_regmod = MagicMock()
        mock_regmod.Registry = MagicMock(side_effect=RuntimeError("reg fail"))

        with patch.dict("sys.modules", {
            "backend_core": MagicMock(),
            "backend_core.ecosystem": MagicMock(),
            "backend_core.ecosystem.registry": mock_regmod,
        }):
            result = mixin._h_registry_load({"ecosystem_dir": "eco"}, {})

        assert isinstance(result, dict)
        assert result["_kernel_step_status"] == "failed"
        assert "reg fail" in result["_kernel_step_error"]
        assert result["_kernel_step_meta"]["handler"] == "kernel:registry.load"


class TestActiveEcosystemLoadHandler:
    """_h_active_ecosystem_load のテスト"""

    def test_success_returns_manager(self):
        """正常系: manager オブジェクトが返ること"""
        mixin = _make_handler_mixin()
        mock_mgr = MagicMock(name="aem")

        mock_amod = MagicMock()
        mock_amod.ActiveEcosystemManager = MagicMock(return_value=mock_mgr)

        with patch.dict("sys.modules", {
            "backend_core": MagicMock(),
            "backend_core.ecosystem": MagicMock(),
            "backend_core.ecosystem.active_ecosystem": mock_amod,
        }):
            result = mixin._h_active_ecosystem_load({"config_file": "test.json"}, {})

        assert result is mock_mgr

    def test_failure_returns_step_status_failed(self):
        """異常系: _kernel_step_status='failed' を含む dict が返ること"""
        mixin = _make_handler_mixin()

        mock_amod = MagicMock()
        mock_amod.ActiveEcosystemManager = MagicMock(side_effect=RuntimeError("aem fail"))

        with patch.dict("sys.modules", {
            "backend_core": MagicMock(),
            "backend_core.ecosystem": MagicMock(),
            "backend_core.ecosystem.active_ecosystem": mock_amod,
        }):
            result = mixin._h_active_ecosystem_load({"config_file": "test.json"}, {})

        assert isinstance(result, dict)
        assert result["_kernel_step_status"] == "failed"
        assert "aem fail" in result["_kernel_step_error"]
        assert result["_kernel_step_meta"]["handler"] == "kernel:active_ecosystem.load"


# ======================================================================
# 候補3: 遅延初期化の無限リトライ修正テスト
# ======================================================================

class TestGetCapabilityProxy:
    """_get_capability_proxy のテスト"""

    def test_success_returns_proxy(self):
        """初期化成功: プロキシオブジェクトが返ること"""
        stub = _make_kernel_core_stub()
        mock_proxy = MagicMock()
        mock_proxy.initialize = MagicMock()

        with patch("core_runtime.kernel_core.get_capability_proxy", return_value=mock_proxy):
            with patch("core_runtime.kernel_core.get_capability_executor" if hasattr(
                __import__("core_runtime.kernel_core"), "get_capability_executor"
            ) else "core_runtime.capability_executor.get_capability_executor") as mock_get_exec:
                mock_exec = MagicMock()
                mock_get_exec.return_value = mock_exec
                # Need to patch the import inside the method
                with patch.dict("sys.modules", {
                    "core_runtime.capability_executor": MagicMock(
                        get_capability_executor=MagicMock(return_value=mock_exec)
                    ),
                }):
                    from core_runtime.kernel_core import KernelCore
                    result = KernelCore._get_capability_proxy(stub)

        assert result is mock_proxy
        assert stub._capability_proxy_init_failed is False

    def test_failure_sets_flag_and_returns_none(self):
        """初期化失敗: None が返り、フラグが True になること"""
        stub = _make_kernel_core_stub()

        with patch("core_runtime.kernel_core.get_capability_proxy", side_effect=RuntimeError("cap fail")):
            from core_runtime.kernel_core import KernelCore
            result = KernelCore._get_capability_proxy(stub)

        assert result is None
        assert stub._capability_proxy_init_failed is True
        stub.diagnostics.record_step.assert_called_once()

    def test_retry_blocked_after_failure(self):
        """再呼び出し: フラグ True なら初期化を試みず None を返すこと"""
        stub = _make_kernel_core_stub()
        stub._capability_proxy_init_failed = True

        with patch("core_runtime.kernel_core.get_capability_proxy") as mock_get:
            from core_runtime.kernel_core import KernelCore
            result = KernelCore._get_capability_proxy(stub)

        assert result is None
        mock_get.assert_not_called()  # 初期化を試みていない


class TestGetUdsProxyManager:
    """_get_uds_proxy_manager のテスト"""

    def test_failure_and_retry_blocked(self):
        """初期化失敗 + 再呼び出し: フラグで初期化がブロックされること"""
        stub = _make_kernel_core_stub()

        mock_egress = MagicMock()
        mock_egress.initialize_uds_egress_proxy = MagicMock(side_effect=RuntimeError("uds fail"))
        mock_ngm_mod = MagicMock()
        mock_ngm_mod.get_network_grant_manager = MagicMock(return_value=MagicMock())
        mock_audit_mod = MagicMock()
        mock_audit_mod.get_audit_logger = MagicMock(return_value=MagicMock())

        with patch.dict("sys.modules", {
            "core_runtime.egress_proxy": mock_egress,
            "core_runtime.network_grant_manager": mock_ngm_mod,
            "core_runtime.audit_logger": mock_audit_mod,
        }):
            from core_runtime.kernel_core import KernelCore

            # First call: should fail and set flag
            result1 = KernelCore._get_uds_proxy_manager(stub)
            assert result1 is None
            assert stub._uds_proxy_init_failed is True
            call_count_1 = stub.diagnostics.record_step.call_count

            # Second call: should NOT attempt init again
            result2 = KernelCore._get_uds_proxy_manager(stub)
            assert result2 is None
            # diagnostics should NOT have been called again
            assert stub.diagnostics.record_step.call_count == call_count_1


class TestResetProxyInit:
    """reset_proxy_init のテスト"""

    def test_reset_clears_flags_and_instances(self):
        """フラグがリセットされ再初期化が可能になること"""
        stub = _make_kernel_core_stub()
        stub._capability_proxy_init_failed = True
        stub._uds_proxy_init_failed = True
        stub._capability_proxy = MagicMock()
        stub._uds_proxy_manager = MagicMock()

        from core_runtime.kernel_core import KernelCore
        KernelCore.reset_proxy_init(stub)

        assert stub._capability_proxy_init_failed is False
        assert stub._uds_proxy_init_failed is False
        assert stub._capability_proxy is None
        assert stub._uds_proxy_manager is None


class TestLogOnlyOnce:
    """異常系でログ出力が1回のみであることのテスト"""

    def test_capability_proxy_logs_once_on_failure(self):
        """_get_capability_proxy: 初期化失敗時にログが1回だけ出力されること"""
        stub = _make_kernel_core_stub()

        with patch("core_runtime.kernel_core.get_capability_proxy", side_effect=RuntimeError("cap fail")):
            with patch("core_runtime.kernel_core._logger") as mock_logger:
                from core_runtime.kernel_core import KernelCore

                # First call: should log
                KernelCore._get_capability_proxy(stub)
                assert mock_logger.error.call_count == 1

                # Second call: should NOT log (flag blocks it)
                KernelCore._get_capability_proxy(stub)
                assert mock_logger.error.call_count == 1  # still 1
