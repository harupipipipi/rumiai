"""
test_wave26_dx_approval_warning.py
W26-DX: approval ステータス起因の component skip に WARNING 通知が出ることを検証
"""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# =====================================================================
# _h_approval_scan tests (stderr WARNING)
# =====================================================================

class TestApprovalScanWarning:
    """_h_approval_scan の WARNING 出力テスト"""

    def _make_kernel(self):
        from core_runtime.kernel_handlers_system import KernelSystemHandlersMixin

        class FakeKernel(KernelSystemHandlersMixin):
            pass

        k = FakeKernel()
        k.diagnostics = MagicMock()
        return k

    def _make_am(self, packs, statuses, verify_results):
        am = MagicMock()
        am.scan_packs.return_value = packs
        am.get_status.side_effect = lambda pid: statuses.get(pid)
        am.verify_hash.side_effect = lambda pid: verify_results.get(pid, True)
        return am

    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_modified_pack_warns_stderr(self, mock_get_am, capsys):
        """modified Pack 検出時に stderr に WARNING が出る"""
        from core_runtime.approval_manager import PackStatus

        k = self._make_kernel()
        am = self._make_am(
            ["pack-a"],
            {"pack-a": PackStatus.APPROVED},
            {"pack-a": False},
        )
        mock_get_am.return_value = am

        ctx = {}
        k._h_approval_scan({"check_hash": True}, ctx)

        captured = capsys.readouterr()
        assert "[Rumi] WARNING" in captured.err
        assert "pack-a" in captured.err
        assert "modified" in captured.err.lower() or "Re-approve" in captured.err

    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_pending_pack_warns_stderr(self, mock_get_am, capsys):
        """pending Pack 検出時に stderr に WARNING が出る"""
        from core_runtime.approval_manager import PackStatus

        k = self._make_kernel()
        am = self._make_am(
            ["pack-b"],
            {"pack-b": PackStatus.PENDING},
            {},
        )
        mock_get_am.return_value = am

        ctx = {}
        k._h_approval_scan({"check_hash": True}, ctx)

        captured = capsys.readouterr()
        assert "[Rumi] WARNING" in captured.err
        assert "pack-b" in captured.err
        assert "awaiting approval" in captured.err.lower()

    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_no_warning_when_all_approved(self, mock_get_am, capsys):
        """modified も pending もなければ WARNING が出ない"""
        from core_runtime.approval_manager import PackStatus

        k = self._make_kernel()
        am = self._make_am(
            ["pack-c"],
            {"pack-c": PackStatus.APPROVED},
            {"pack-c": True},
        )
        mock_get_am.return_value = am

        ctx = {}
        k._h_approval_scan({"check_hash": True}, ctx)

        captured = capsys.readouterr()
        assert "[Rumi] WARNING" not in captured.err


# =====================================================================
# _run_phase_for_component tests (logger.warning)
# =====================================================================

class TestRunPhaseWarning:
    """_run_phase_for_component の logger.warning テスト"""

    def _make_executor(self):
        from core_runtime.component_lifecycle import ComponentLifecycleExecutor
        return ComponentLifecycleExecutor(
            diagnostics=MagicMock(),
            install_journal=MagicMock(),
        )

    def _make_component(self, pack_id="test-pack", comp_id="comp1"):
        return SimpleNamespace(
            full_id=f"{pack_id}:plugin:{comp_id}",
            pack_id=pack_id,
            type="plugin",
            id=comp_id,
            path="/tmp/nonexistent_w26_test",
        )

    @patch("core_runtime.component_lifecycle.logger")
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_not_approved_warns(self, mock_get_am, mock_logger):
        """未承認 Pack のコンポーネント skip 時に logger.warning が呼ばれる"""
        from core_runtime.approval_manager import PackStatus

        am = MagicMock()
        am._initialized = True
        am.get_status.return_value = PackStatus.PENDING
        mock_get_am.return_value = am

        executor = self._make_executor()
        comp = self._make_component(pack_id="my-pack")
        executor._run_phase_for_component("setup", comp)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        msg = call_args[0][0]
        assert "skipped" in msg.lower()
        # %s placeholders are filled with positional args
        assert call_args[0][1] == "my-pack:plugin:comp1"  # comp_id
        assert call_args[0][2] == "my-pack"  # pack_id

    @patch("core_runtime.component_lifecycle.logger")
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_hash_mismatch_warns(self, mock_get_am, mock_logger):
        """verify_hash 失敗時に logger.warning が呼ばれる"""
        from core_runtime.approval_manager import PackStatus

        am = MagicMock()
        am._initialized = True
        am.get_status.return_value = PackStatus.APPROVED
        am.verify_hash.return_value = False
        mock_get_am.return_value = am

        executor = self._make_executor()
        comp = self._make_component(pack_id="changed-pack")
        executor._run_phase_for_component("setup", comp)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        msg = call_args[0][0]
        assert "changed after approval" in msg.lower() or "Re-approve" in msg
        assert call_args[0][1] == "changed-pack:plugin:comp1"
        assert call_args[0][2] == "changed-pack"

    @patch("core_runtime.component_lifecycle.logger")
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_approved_and_hash_ok_no_warning(self, mock_get_am, mock_logger):
        """approved + hash OK の正常パスでは logger.warning が呼ばれない"""
        from core_runtime.approval_manager import PackStatus

        am = MagicMock()
        am._initialized = True
        am.get_status.return_value = PackStatus.APPROVED
        am.verify_hash.return_value = True
        mock_get_am.return_value = am

        executor = self._make_executor()
        comp = self._make_component()
        executor._run_phase_for_component("setup", comp)

        mock_logger.warning.assert_not_called()


# =====================================================================
# Cross-cutting tests
# =====================================================================

class TestWarningMessageQuality:
    """WARNING メッセージの品質テスト"""

    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_warning_contains_dynamic_pack_id(self, mock_get_am, capsys):
        """WARNING に動的な Pack ID が含まれ、特定 Pack 名のハードコードでないことを確認"""
        from core_runtime.kernel_handlers_system import KernelSystemHandlersMixin
        from core_runtime.approval_manager import PackStatus

        class FK(KernelSystemHandlersMixin):
            pass

        k = FK()
        k.diagnostics = MagicMock()

        am = MagicMock()
        am.scan_packs.return_value = ["unique-id-12345"]
        am.get_status.return_value = PackStatus.MODIFIED
        am.verify_hash.return_value = True
        mock_get_am.return_value = am

        k._h_approval_scan({"check_hash": True}, {})
        captured = capsys.readouterr()
        assert "unique-id-12345" in captured.err


class TestSecurityRegressionGuard:
    """セキュリティロジックが変更されていないことの回帰テスト"""

    @patch("core_runtime.component_lifecycle.logger")
    @patch("core_runtime.approval_manager.get_approval_manager")
    def test_mark_modified_still_called_on_hash_failure(
        self, mock_get_am, mock_logger
    ):
        """verify_hash 失敗時に mark_modified が依然として呼ばれること"""
        from core_runtime.approval_manager import PackStatus
        from core_runtime.component_lifecycle import ComponentLifecycleExecutor

        am = MagicMock()
        am._initialized = True
        am.get_status.return_value = PackStatus.APPROVED
        am.verify_hash.return_value = False
        mock_get_am.return_value = am

        executor = ComponentLifecycleExecutor(
            diagnostics=MagicMock(),
            install_journal=MagicMock(),
        )
        comp = SimpleNamespace(
            full_id="sec-pack:plugin:sec-comp",
            pack_id="sec-pack",
            type="plugin",
            id="sec-comp",
            path="/tmp/nonexistent_w26_test",
        )
        executor._run_phase_for_component("setup", comp)

        am.mark_modified.assert_called_once_with("sec-pack")
