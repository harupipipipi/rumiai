"""
test_capability_executor.py - CapabilityExecutor ユニットテスト

対象: core_runtime/capability_executor.py
全テストは mock ベースで外部依存なし。
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

pytestmark = pytest.mark.contract

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.capability_executor import (
    CapabilityExecutor,
    CapabilityResponse,
    MAX_FLOW_CALL_DEPTH,
    get_capability_executor,
    _flow_call_stack_local,
)


def _make_executor(
    handler_registry=None,
    trust_store=None,
    grant_manager=None,
    function_registry=None,
    approval_manager=None,
    permission_manager=None,
    rate_limit: int = 60,
) -> CapabilityExecutor:
    """テスト用 CapabilityExecutor を生成し内部状態を mock 注入"""
    executor = CapabilityExecutor()
    executor._initialized = True
    executor._handler_registry = handler_registry or MagicMock()
    executor._trust_store = trust_store or MagicMock()
    executor._grant_manager = grant_manager or MagicMock()
    executor._function_registry = function_registry
    executor._approval_manager = approval_manager
    executor._permission_manager = permission_manager
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
    pack_id: str = ""


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


def _make_function_entry(
    pack_id: str,
    *,
    function_id: str = "test_func",
    requires: Optional[List[str]] = None,
    caller_requires: Optional[List[str]] = None,
    **extra,
):
    default_main_py = str(Path(__file__).resolve())
    default_function_dir = str(Path(default_main_py).parent)
    entry = SimpleNamespace(
        pack_id=pack_id,
        function_id=function_id,
        qualified_name=f"{pack_id}:{function_id}",
        requires=list(requires or []),
        caller_requires=list(caller_requires or []),
        host_execution=False,
        calling_convention=None,
        function_dir=default_function_dir,
        main_py_path=default_main_py,
        entrypoint="main.py:run",
        grant_config={},
        manifest={},
        vocab_aliases=[],
    )
    for key, value in extra.items():
        setattr(entry, key, value)
    return entry


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
        tmp_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_ctx.cleanup)
        handler_dir = Path(tmp_ctx.name)
        handler_path = handler_dir / "handler.py"
        handler_path.write_text("def handle(ctx, args): return {'result': 'ok'}\n", encoding="utf-8")
        handler_def = _MockHandlerDef(
            handler_py_path=str(handler_path),
            handler_dir=handler_dir,
            entrypoint="handler.py:handle",
            is_builtin=True,
        )
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

        with patch.object(executor, "_handler_def_requires_managed_sandbox", return_value=False):
            with patch.object(executor, "_entry_requires_managed_sandbox", return_value=False):
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
        executor._rate_limit_store = MagicMock()
        executor._rate_limit_store.allow.side_effect = [True] * limit + [False]

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


class TestFunctionCallBuiltinTrustScope(unittest.TestCase):
    """builtin pack bypass is limited to the bundled runtime copy"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_bundled_defaultspack_bypasses_builtin_checks(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("defaultspack", requires=["tool.write"])
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        approval_manager._is_trusted_builtin_pack.return_value = True

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = False

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
        )

        success_response = CapabilityResponse(success=True, output={"ok": True})
        with patch.object(executor, "_execute_user_function", return_value=success_response) as mock_exec:
            resp = executor.execute(
                "defaultspack",
                {"type": "function.call", "qualified_name": "defaultspack:test_func"},
            )

        self.assertTrue(resp.success)
        permission_manager.has_permission.assert_not_called()
        mock_exec.assert_called_once()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_nonbundled_defaultspack_checks_pack_requires(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("defaultspack", requires=["tool.write"])
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        approval_manager._is_trusted_builtin_pack.return_value = False

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = False

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
        )

        resp = executor.execute(
            "principal_a",
            {"type": "function.call", "qualified_name": "defaultspack:test_func"},
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "requires_denied")
        permission_manager.has_permission.assert_called_once_with("defaultspack", "tool.write")

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_repo_defaultspack_path_is_treated_as_trusted_builtin(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("defaultspack", requires=["ai.route.model"])
        entry.function_dir = str(_project_root / "ecosystem" / "defaultspack" / "functions" / "ai_route_model")
        entry.main_py_path = str(Path(entry.function_dir) / "main.py")
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        approval_manager._is_trusted_builtin_pack.return_value = False

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = False

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
        )

        success_response = CapabilityResponse(success=True, output={"ok": True})
        with patch.object(executor, "_execute_user_function", return_value=success_response) as mock_exec:
            resp = executor.execute(
                "defaultspack",
                {"type": "function.call", "qualified_name": "defaultspack:test_func"},
            )

        self.assertTrue(resp.success)
        permission_manager.has_permission.assert_not_called()
        mock_exec.assert_called_once()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_dev_auto_reapproves_stale_pack(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("defaultspack")
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.side_effect = [
            (False, "hash_mismatch"),
            (True, None),
        ]
        approval_manager.approve.return_value = SimpleNamespace(success=True)
        approval_manager._is_trusted_builtin_pack.return_value = False

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = True

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
        )

        success_response = CapabilityResponse(success=True, output={"ok": True})
        with (
            patch.dict("os.environ", {"RUMI_ENVIRONMENT": "development", "RUMI_AUTO_APPROVE_LOCAL": "true"}),
            patch.object(executor, "_execute_user_function", return_value=success_response) as mock_exec,
        ):
            resp = executor.execute(
                "principal_a",
                {"type": "function.call", "qualified_name": "defaultspack:test_func"},
            )

        self.assertTrue(resp.success)
        approval_manager.scan_packs.assert_called_once()
        approval_manager.approve.assert_called_once_with("defaultspack")
        self.assertEqual(approval_manager.is_pack_approved_and_verified.call_count, 2)
        mock_exec.assert_called_once()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_nonbundled_defaultspack_checks_caller_permission(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("custom_pack")
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        approval_manager._is_trusted_builtin_pack.return_value = False

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = False

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
        )

        resp = executor.execute(
            "defaultspack",
            {"type": "function.call", "qualified_name": "custom_pack:test_func"},
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "permission_denied")
        permission_manager.has_permission.assert_called_once_with("defaultspack", "function.call")

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_grant_manager_fulfills_pack_requires_when_permission_manager_denies(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("defaultspack", requires=["tool.write"])
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        approval_manager._is_trusted_builtin_pack.return_value = False

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = False

        grant_manager = MagicMock()
        grant_manager.check.side_effect = [
            _MockGrantResult(allowed=True),
            _MockGrantResult(allowed=True),
            _MockGrantResult(allowed=True),
        ]

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
            grant_manager=grant_manager,
        )

        success_response = CapabilityResponse(success=True, output={"ok": True})
        with patch.object(executor, "_execute_user_function", return_value=success_response) as mock_exec:
            resp = executor.execute(
                "principal_a",
                {"type": "function.call", "qualified_name": "defaultspack:test_func"},
            )

        self.assertTrue(resp.success)
        permission_manager.has_permission.assert_any_call("defaultspack", "tool.write")
        permission_manager.has_permission.assert_any_call("principal_a", "function.call")
        grant_manager.check.assert_any_call("defaultspack", "tool.write")
        grant_manager.check.assert_any_call("principal_a", "function.call")
        grant_manager.check.assert_any_call("defaultspack", "defaultspack:test_func")
        mock_exec.assert_called_once()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_grant_manager_fulfills_caller_permission_when_permission_manager_denies(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("custom_pack")
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        approval_manager._is_trusted_builtin_pack.return_value = False

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = False

        grant_manager = MagicMock()
        grant_manager.check.return_value = _MockGrantResult(allowed=True)

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
            grant_manager=grant_manager,
        )

        success_response = CapabilityResponse(success=True, output={"ok": True})
        with patch.object(executor, "_execute_user_function", return_value=success_response) as mock_exec:
            resp = executor.execute(
                "rumi_default_tools_pack",
                {"type": "function.call", "qualified_name": "custom_pack:test_func"},
            )

        self.assertTrue(resp.success)
        permission_manager.has_permission.assert_called_once_with("rumi_default_tools_pack", "function.call")
        grant_manager.check.assert_any_call("rumi_default_tools_pack", "function.call")
        grant_manager.check.assert_any_call("custom_pack", "custom_pack:test_func")
        mock_exec.assert_called_once()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_function_call_enforces_function_trust_for_nonbuiltin_packs(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry(
            "custom_pack",
            manifest={"trust_required": True},
        )
        function_registry = MagicMock()
        function_registry.get.return_value = entry

        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        approval_manager._is_trusted_builtin_pack.return_value = False

        permission_manager = MagicMock()
        permission_manager.has_permission.return_value = True

        trust_store = MagicMock()
        trust_store.is_trusted.return_value = _MockTrustResult(
            trusted=False,
            reason="not trusted",
        )

        executor = _make_executor(
            function_registry=function_registry,
            approval_manager=approval_manager,
            permission_manager=permission_manager,
            trust_store=trust_store,
        )

        resp = executor.execute(
            "principal_a",
            {"type": "function.call", "qualified_name": "custom_pack:test_func"},
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "trust_denied")


class TestUnifiedExecuteCallingConventionTrust(unittest.TestCase):
    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_denies_unapproved_pack_before_dispatch(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry("custom_pack", calling_convention="subprocess")
        approval_manager = MagicMock()
        approval_manager.is_pack_approved_and_verified.return_value = (False, "hash_mismatch")
        approval_manager._is_trusted_builtin_pack.return_value = False
        executor = _make_executor(approval_manager=approval_manager)

        with patch.object(executor, "_dispatch_by_calling_convention") as mock_dispatch:
            resp = executor._unified_execute(
                entry,
                "principal_a",
                {"args": {}, "request_id": "req-approval"},
                time.time(),
            )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "pack_not_approved")
        mock_dispatch.assert_not_called()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_host_convention_requires_grant_without_manifest_config(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            host_path = tmp_path / "host.py"
            host_path.write_text("def run(*args): return {'ok': True}", encoding="utf-8")
            entry = _make_function_entry(
                "custom_pack",
                calling_convention="python_host",
                main_py_path=str(host_path),
                function_dir=str(tmp_path),
                grant_config=None,
            )
            approval_manager = MagicMock()
            approval_manager.is_pack_approved_and_verified.return_value = (True, None)
            approval_manager._is_trusted_builtin_pack.return_value = False
            trust_store = MagicMock()
            trust_store.is_trusted.return_value = _MockTrustResult(trusted=True, reason="ok")
            grant_manager = MagicMock()
            grant_manager.check.return_value = _MockGrantResult(allowed=False, reason="missing grant")
            executor = _make_executor(
                trust_store=trust_store,
                grant_manager=grant_manager,
                approval_manager=approval_manager,
            )

            with patch.object(executor, "_dispatch_by_calling_convention") as mock_dispatch:
                resp = executor._unified_execute(
                    entry,
                    "principal_a",
                    {"args": {}, "request_id": "req-host"},
                    time.time(),
                )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "grant_denied")
        grant_manager.check.assert_any_call("custom_pack", "custom_pack:test_func")
        mock_dispatch.assert_not_called()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_binary_entry_uses_binary_trust_path(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            binary_path = tmp_path / "tool.bin"
            binary_path.write_text("binary", encoding="utf-8")
            entry = _make_function_entry(
                "custom_pack",
                calling_convention="binary",
                main_py_path=None,
                main_binary_path=str(binary_path),
                function_dir=str(tmp_path),
                grant_config=None,
            )
            approval_manager = MagicMock()
            approval_manager._is_trusted_builtin_pack.return_value = False
            trust_store = MagicMock()
            trust_store.is_trusted.return_value = _MockTrustResult(trusted=True, reason="ok")
            executor = _make_executor(
                trust_store=trust_store,
                grant_manager=MagicMock(),
                approval_manager=approval_manager,
            )
            executor._grant_manager.check.return_value = _MockGrantResult(allowed=True)
            success = CapabilityResponse(success=True, output={"ok": True})

            with patch.object(executor, "_dispatch_by_calling_convention", return_value=success) as mock_dispatch:
                resp = executor._unified_execute(
                    entry,
                    "principal_a",
                    {"args": {}, "request_id": "req-bin"},
                    time.time(),
                )

        self.assertTrue(resp.success)
        mock_dispatch.assert_called_once()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_command_entry_requires_absolute_executable_path(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        entry = _make_function_entry(
            "custom_pack",
            calling_convention="command",
            main_py_path=None,
            command=["bash", "-lc", "echo hi"],
            grant_config=None,
        )
        approval_manager = MagicMock()
        approval_manager._is_trusted_builtin_pack.return_value = False
        executor = _make_executor(
            trust_store=MagicMock(),
            grant_manager=MagicMock(),
            approval_manager=approval_manager,
        )

        resp = executor._unified_execute(
            entry,
            "principal_a",
            {"args": {}, "request_id": "req-cmd"},
            time.time(),
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "trust_denied")


class TestHandlerSubprocessEntrypointCompatibility(unittest.TestCase):
    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_execute_handler_subprocess_defaults_callable_when_entrypoint_has_no_colon(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()
        executor = _make_executor()
        tmp_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_ctx.cleanup)
        handler_dir = Path(tmp_ctx.name)
        handler_path = handler_dir / "handler.py"
        handler_path.write_text("def run(ctx, args): return {'ok': True}\n", encoding="utf-8")
        handler_def = _MockHandlerDef(
            handler_py_path=str(handler_path),
            handler_dir=handler_dir,
            entrypoint="handler.py",
            is_builtin=True,
        )
        success = CapabilityResponse(success=True, output={"ok": True})

        with patch.object(executor, "_handler_def_requires_managed_sandbox", return_value=False):
            with patch.object(executor, "_run_runner_on_host", return_value=success) as mock_run:
                resp = executor._execute_handler_subprocess(
                    handler_def=handler_def,
                    principal_id="principal_a",
                    permission_id="perm.test",
                    grant_config={},
                    args={},
                    timeout_seconds=5,
                    request_id="req-subproc",
                    start_time=time.time(),
                )

        self.assertTrue(resp.success)
        mock_run.assert_called_once()


def test_get_capability_executor_initializes_cached_container_instance(monkeypatch):
    class _FakeContainer:
        def __init__(self, executor):
            self._executor = executor

        def get(self, name):
            assert name == "capability_executor"
            return self._executor

    executor = CapabilityExecutor()
    assert executor._initialized is False
    initialize_calls = {"count": 0}

    def fake_initialize():
        initialize_calls["count"] += 1
        executor._initialized = True
        return True

    monkeypatch.setattr(executor, "initialize", fake_initialize)

    monkeypatch.setattr(
        "core_runtime.di_container.get_container",
        lambda: _FakeContainer(executor),
    )

    resolved = get_capability_executor()

    assert resolved is executor
    assert resolved._initialized is True
    assert initialize_calls["count"] == 1


if __name__ == "__main__":
    unittest.main()
