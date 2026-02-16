"""
test_capability_executor.py - CapabilityExecutor ユニットテスト

対象: core_runtime/capability_executor.py
全テストは mock ベースで外部依存なし。
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass
from typing import Any, Dict, Optional

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.capability_executor import (
    CapabilityExecutor,
    CapabilityResponse,
    MAX_FLOW_CALL_DEPTH,
    _flow_call_stack_local,
)


def _make_executor(
    handler_registry=None,
    trust_store=None,
    grant_manager=None,
    rate_limit: int = 60,
) -> CapabilityExecutor:
    """テスト用 CapabilityExecutor を生成し内部状態を mock 注入"""
    executor = CapabilityExecutor()
    executor._initialized = True
    executor._handler_registry = handler_registry or MagicMock()
    executor._trust_store = trust_store or MagicMock()
    executor._grant_manager = grant_manager or MagicMock()
    executor._secret_get_rate_limit = rate_limit
    return executor


@dataclass
class _MockHandlerDef:
    handler_id: str = "test_handler"
    permission_id: str = "test.permission"
    handler_py_path: str = "/fake/handler.py"
    handler_dir: Path = Path("/fake")
    entrypoint: str = "handler.py:handle"
    is_builtin: bool = False


@dataclass
class _MockTrustResult:
    trusted: bool = True
    reason: str = ""


@dataclass
class _MockGrantResult:
    allowed: bool = True
    reason: str = "Granted"
    config: Dict[str, Any] = None

    def __post_init__(self):
        if self.config is None:
            self.config = {}


class TestExecuteMissingPermissionId(unittest.TestCase):
    """permission_id なしで invalid_request"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_execute_missing_permission_id(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        executor = _make_executor()
        resp = executor.execute("principal_a", {"args": {}})
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "invalid_request")
        self.assertIn("permission_id", resp.error.lower())


class TestExecuteHandlerNotFound(unittest.TestCase):
    """未登録 permission_id で handler_not_found"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_execute_handler_not_found(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        registry = MagicMock()
        registry.get_by_permission_id.return_value = None
        executor = _make_executor(handler_registry=registry)
        resp = executor.execute("principal_a", {"permission_id": "unknown.perm"})
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "handler_not_found")


class TestExecuteTrustDenied(unittest.TestCase):
    """trust 検証失敗で trust_denied"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch("core_runtime.capability_executor.compute_file_sha256", return_value="sha256_abc")
    def test_execute_trust_denied(self, mock_sha, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        handler_def = _MockHandlerDef(is_builtin=False)
        registry = MagicMock()
        registry.get_by_permission_id.return_value = handler_def

        trust_store = MagicMock()
        trust_store.is_trusted.return_value = _MockTrustResult(trusted=False, reason="not in allowlist")

        executor = _make_executor(handler_registry=registry, trust_store=trust_store)
        resp = executor.execute("principal_a", {"permission_id": "test.permission"})
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "trust_denied")


class TestExecuteGrantDenied(unittest.TestCase):
    """grant 検証失敗で grant_denied"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch("core_runtime.capability_executor.compute_file_sha256", return_value="sha256_abc")
    def test_execute_grant_denied(self, mock_sha, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        handler_def = _MockHandlerDef(is_builtin=True)
        registry = MagicMock()
        registry.get_by_permission_id.return_value = handler_def

        grant_manager = MagicMock()
        grant_manager.check.return_value = _MockGrantResult(allowed=False, reason="No grant")

        executor = _make_executor(handler_registry=registry, grant_manager=grant_manager)
        resp = executor.execute("principal_a", {"permission_id": "test.permission"})
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "grant_denied")


class TestExecuteSuccess(unittest.TestCase):
    """全チェック通過で成功"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch("core_runtime.capability_executor.compute_file_sha256", return_value="sha256_abc")
    def test_execute_success(self, mock_sha, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        handler_def = _MockHandlerDef(is_builtin=True)
        registry = MagicMock()
        registry.get_by_permission_id.return_value = handler_def

        grant_manager = MagicMock()
        grant_manager.check.return_value = _MockGrantResult(allowed=True)

        executor = _make_executor(handler_registry=registry, grant_manager=grant_manager)

        # subprocess 実行を mock
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"result": "ok"}'
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            with patch("tempfile.NamedTemporaryFile") as mock_tmpfile:
                mock_tmpfile.return_value.__enter__ = MagicMock(
                    return_value=MagicMock(name="/tmp/fake_runner.py")
                )
                mock_tmpfile.return_value.__exit__ = MagicMock(return_value=False)
                resp = executor.execute("principal_a", {"permission_id": "test.permission"})

        self.assertTrue(resp.success)


class TestRateLimitSecretGet(unittest.TestCase):
    """secrets.get を rate limit 上限+1 で rate_limited"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_rate_limit_secret_get(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        limit = 2
        executor = _make_executor(rate_limit=limit)

        # rate limit 内のリクエスト（handler 未登録なので handler_not_found で停止する）
        for _ in range(limit):
            resp = executor.execute("principal_a", {"permission_id": "secrets.get"})
            # handler_not_found になるはずだが rate_limited ではない
            self.assertNotEqual(resp.error_type, "rate_limited")

        # rate limit 超過
        resp = executor.execute("principal_a", {"permission_id": "secrets.get"})
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "rate_limited")


class TestFlowRunRecursive(unittest.TestCase):
    """flow.run の循環検出"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch("core_runtime.capability_executor.compute_file_sha256", return_value="sha256_abc")
    def test_flow_run_recursive(self, mock_sha, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        handler_def = _MockHandlerDef(
            permission_id="flow.run",
            is_builtin=True,
        )
        registry = MagicMock()
        registry.get_by_permission_id.return_value = handler_def

        grant_manager = MagicMock()
        grant_manager.check.return_value = _MockGrantResult(allowed=True)

        mock_kernel = MagicMock()
        executor = _make_executor(handler_registry=registry, grant_manager=grant_manager)
        executor._kernel = mock_kernel

        # スレッドローカルを初期化して循環をシミュレート
        if not hasattr(_flow_call_stack_local, "stack"):
            _flow_call_stack_local.stack = []
        _flow_call_stack_local.stack = ["my_flow"]  # 既に my_flow がスタックに存在

        try:
            resp = executor.execute(
                "principal_a",
                {
                    "permission_id": "flow.run",
                    "args": {"flow_id": "my_flow"},
                },
            )
            self.assertFalse(resp.success)
            self.assertEqual(resp.error_type, "recursive_flow")
        finally:
            _flow_call_stack_local.stack = []


class TestFlowRunDepthExceeded(unittest.TestCase):
    """flow.run の深さ制限超過"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch("core_runtime.capability_executor.compute_file_sha256", return_value="sha256_abc")
    def test_flow_run_depth_exceeded(self, mock_sha, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        handler_def = _MockHandlerDef(
            permission_id="flow.run",
            is_builtin=True,
        )
        registry = MagicMock()
        registry.get_by_permission_id.return_value = handler_def

        grant_manager = MagicMock()
        grant_manager.check.return_value = _MockGrantResult(allowed=True)

        mock_kernel = MagicMock()
        executor = _make_executor(handler_registry=registry, grant_manager=grant_manager)
        executor._kernel = mock_kernel

        # スレッドローカルを深さ制限まで積む
        if not hasattr(_flow_call_stack_local, "stack"):
            _flow_call_stack_local.stack = []
        _flow_call_stack_local.stack = [f"flow_{i}" for i in range(MAX_FLOW_CALL_DEPTH)]

        try:
            resp = executor.execute(
                "principal_a",
                {
                    "permission_id": "flow.run",
                    "args": {"flow_id": "new_flow"},
                },
            )
            self.assertFalse(resp.success)
            self.assertEqual(resp.error_type, "flow_depth_exceeded")
        finally:
            _flow_call_stack_local.stack = []


if __name__ == "__main__":
    unittest.main()
