"""
test_python_file_executor.py - PythonFileExecutor ユニットテスト

対象: core_runtime/python_file_executor.py
全テストは mock ベースで外部依存なし。
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.python_file_executor import (
    PythonFileExecutor,
    ExecutionContext,
    ExecutionResult,
    PathValidator,
)


def _make_context(**kwargs) -> ExecutionContext:
    """テスト用 ExecutionContext を生成"""
    defaults = {
        "flow_id": "test_flow",
        "step_id": "test_step",
        "phase": "startup",
        "ts": "2025-01-01T00:00:00Z",
        "owner_pack": "test_pack",
        "inputs": {},
    }
    defaults.update(kwargs)
    return ExecutionContext(**defaults)


class TestPathValidationTraversal(unittest.TestCase):
    """パストラバーサル拒否"""

    def test_path_validation_traversal(self):
        """../../etc/passwd のようなパストラバーサルは拒否される"""
        executor = PythonFileExecutor()

        ctx = _make_context(owner_pack="my_pack")

        # PathValidator を mock して traversal を検出
        mock_validator = MagicMock()
        mock_validator.validate.return_value = (
            False,
            "Path outside allowed roots: /etc/passwd",
            None,
        )
        executor._path_validator = mock_validator

        # approval_checker も mock（承認済みにする）
        mock_approval = MagicMock()
        mock_approval.is_approved.return_value = (True, None)
        mock_approval.verify_hash.return_value = (True, None)
        executor._approval_checker = mock_approval

        with patch.object(executor, '_audit', MagicMock()):
            result = executor.execute(
                file_path="../../etc/passwd",
                owner_pack="my_pack",
                input_data={},
                context=ctx,
            )

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "path_rejected")
        self.assertEqual(result.execution_mode, "rejected")


class TestApprovalCheckFailure(unittest.TestCase):
    """未承認 Pack の実行拒否"""

    def test_approval_check_failure(self):
        """未承認 Pack の python_file_call は拒否される"""
        executor = PythonFileExecutor()

        ctx = _make_context(owner_pack="unapproved_pack")

        # approval_checker を mock して未承認を返す
        mock_approval = MagicMock()
        mock_approval.is_approved.return_value = (
            False,
            "Pack 'unapproved_pack' is not approved (status: pending)",
        )
        executor._approval_checker = mock_approval

        with patch.object(executor, '_audit', MagicMock()):
            result = executor.execute(
                file_path="run.py",
                owner_pack="unapproved_pack",
                input_data={},
                context=ctx,
            )

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "approval_rejected")
        self.assertEqual(result.execution_mode, "rejected")


class TestDockerExecutionSuccess(unittest.TestCase):
    """Docker モードの正常実行（subprocess mock）"""

    def test_docker_execution_success(self):
        """Docker コンテナ実行が正常に完了するケース"""
        executor = PythonFileExecutor()
        executor._security_mode = "strict"

        ctx = _make_context(owner_pack="my_pack")

        # approval_checker mock
        mock_approval = MagicMock()
        mock_approval.is_approved.return_value = (True, None)
        mock_approval.verify_hash.return_value = (True, None)
        executor._approval_checker = mock_approval

        # path_validator mock
        resolved_path = Path("/fake/ecosystem/my_pack/run.py")
        mock_validator = MagicMock()
        mock_validator.validate.return_value = (True, None, resolved_path)
        executor._path_validator = mock_validator

        # docker available
        with patch.object(executor, '_check_docker_available', return_value=True):
            # UDS proxy mock
            mock_uds = MagicMock()
            mock_uds.ensure_pack_socket.return_value = (True, None, Path("/run/rumi/egress.sock"))
            executor._uds_proxy_manager = mock_uds

            # _execute_in_container を mock して成功を返す
            mock_result = ExecutionResult(
                success=True,
                output={"status": "ok"},
                execution_mode="container",
            )
            with patch.object(executor, '_execute_in_container', return_value=mock_result):
                with patch.object(executor, '_audit', MagicMock()):
                    result = executor.execute(
                        file_path="run.py",
                        owner_pack="my_pack",
                        input_data={"key": "val"},
                        context=ctx,
                    )

        self.assertTrue(result.success)
        self.assertEqual(result.execution_mode, "container")
        self.assertEqual(result.output, {"status": "ok"})


class TestHostExecutionTimeout(unittest.TestCase):
    """ホスト実行のタイムアウト"""

    def test_host_execution_timeout(self):
        """permissive モードでのホスト実行がタイムアウトする"""
        executor = PythonFileExecutor()
        executor._security_mode = "permissive"

        ctx = _make_context(owner_pack="my_pack")

        # approval_checker mock
        mock_approval = MagicMock()
        mock_approval.is_approved.return_value = (True, None)
        mock_approval.verify_hash.return_value = (True, None)
        executor._approval_checker = mock_approval

        # path_validator mock
        resolved_path = Path("/fake/ecosystem/my_pack/slow.py")
        mock_validator = MagicMock()
        mock_validator.validate.return_value = (True, None, resolved_path)
        executor._path_validator = mock_validator

        # docker unavailable → host execution
        with patch.object(executor, '_check_docker_available', return_value=False):
            # _execute_on_host を mock してタイムアウト結果を返す
            timeout_result = ExecutionResult(
                success=False,
                error="Host execution timed out after 0.1s",
                error_type="timeout",
                execution_mode="host_permissive",
            )
            with patch.object(executor, '_execute_on_host', return_value=timeout_result):
                with patch.object(executor, '_audit', MagicMock()):
                    result = executor.execute(
                        file_path="slow.py",
                        owner_pack="my_pack",
                        input_data={},
                        context=ctx,
                        timeout_seconds=0.1,
                    )

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "timeout")
        self.assertIn("timed out", result.error.lower())


if __name__ == "__main__":
    unittest.main()
