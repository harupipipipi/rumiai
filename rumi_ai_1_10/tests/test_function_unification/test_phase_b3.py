"""
test_phase_b3.py - Phase B-3 テスト: capability_executor 統一パス化

対象:
- _resolve_entry()
- _unified_execute()
- _legacy_execute()
- execute() の統合分岐

全テストは mock ベースで外部依存なし。
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch, MagicMock, call

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.capability_executor import (
    CapabilityExecutor,
    CapabilityResponse,
    SECRET_GET_PERMISSION_ID,
    FLOW_RUN_PERMISSION_ID,
    DOCKER_PERMISSION_IDS,
    _HandlerDefAdapter,
)


# =====================================================================
# Mock helpers (following existing test_capability_executor.py patterns)
# =====================================================================

@dataclass
class _MockFunctionEntry:
    """FunctionEntry の mock"""
    function_id: str = "test_func"
    pack_id: str = "test_pack"
    qualified_name: str = "test_pack:test_func"
    description: str = "test function"
    requires: List[str] = field(default_factory=list)
    caller_requires: List[str] = field(default_factory=list)
    host_execution: bool = False
    tags: List[str] = field(default_factory=list)
    function_dir: Any = "/fake/function_dir"
    main_py_path: Any = "/fake/function_dir/handler.py"
    manifest: Dict[str, Any] = field(default_factory=dict)
    entrypoint: Optional[str] = "handler.py:execute"
    risk: Optional[str] = None
    grant_config: Optional[Dict[str, Any]] = None
    vocab_aliases: Optional[List[str]] = None
    runtime: str = "python"
    main_binary_path: Any = None
    command: List[str] = field(default_factory=list)
    docker_image: str = ""
    extensions: Dict[str, Any] = field(default_factory=dict)


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


@dataclass
class _MockHandlerDef:
    handler_id: str = "test_handler"
    permission_id: str = "test.permission"
    handler_py_path: str = "/fake/handler.py"
    handler_dir: Path = None
    entrypoint: str = "handler.py:handle"
    is_builtin: bool = False

    def __post_init__(self):
        if self.handler_dir is None:
            self.handler_dir = Path("/fake")


def _make_executor(
    handler_registry=None,
    trust_store=None,
    grant_manager=None,
    function_registry=None,
    rate_limit: int = 60,
) -> CapabilityExecutor:
    """テスト用 CapabilityExecutor を生成し内部状態を mock 注入"""
    executor = CapabilityExecutor()
    executor._initialized = True
    executor._handler_registry = handler_registry or MagicMock()
    executor._trust_store = trust_store or MagicMock()
    executor._grant_manager = grant_manager or MagicMock()
    executor._function_registry = function_registry
    executor._secret_get_rate_limit = rate_limit
    return executor


# =====================================================================
# _resolve_entry tests
# =====================================================================

class TestResolveEntryFound(unittest.TestCase):
    """test 1: 登録済み alias で FunctionEntry が返ること"""

    def test_resolve_entry_found(self):
        entry = _MockFunctionEntry(vocab_aliases=["test.perm"])
        fr = MagicMock()
        fr.resolve_by_alias.return_value = entry

        executor = _make_executor(function_registry=fr)
        result = executor._resolve_entry("test.perm")

        self.assertIs(result, entry)
        fr.resolve_by_alias.assert_called_once_with("test.perm")


class TestResolveEntryNotFound(unittest.TestCase):
    """test 2: 未登録 alias で None が返ること"""

    def test_resolve_entry_not_found(self):
        fr = MagicMock()
        fr.resolve_by_alias.return_value = None

        executor = _make_executor(function_registry=fr)
        result = executor._resolve_entry("unknown.perm")

        self.assertIsNone(result)


class TestResolveEntryRegistryUnavailable(unittest.TestCase):
    """test 3: FunctionRegistry が利用不可の場合 None が返ること"""

    def test_resolve_entry_registry_unavailable(self):
        executor = _make_executor(function_registry=None)
        result = executor._resolve_entry("any.perm")

        self.assertIsNone(result)


# =====================================================================
# _unified_execute tests
# =====================================================================

class TestUnifiedExecuteBuiltinTrustBypass(unittest.TestCase):
    """test 4: core pack の entry で Trust チェックがバイパスされること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_builtin_trust_bypass(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        entry = _MockFunctionEntry(
            pack_id="core_test",
            qualified_name="core_test:test_func",
            vocab_aliases=["test.perm"],
            entrypoint="handler.py:execute",
            function_dir="/fake/dir",
        )

        trust_store = MagicMock()
        grant_manager = MagicMock()
        executor = _make_executor(trust_store=trust_store, grant_manager=grant_manager)

        # Mock subprocess for execution
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
                resp = executor._unified_execute(
                    entry, "principal_a",
                    {"permission_id": "test.perm", "args": {}},
                    start_time=time.time(),
                )

        # Trust store should NOT be called (builtin bypass)
        trust_store.is_trusted.assert_not_called()
        self.assertTrue(resp.success)


class TestUnifiedExecuteNonBuiltinTrustCheck(unittest.TestCase):
    """test 5: 非 core pack の entry で sha256 検証が実行されること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch("core_runtime.capability_executor.compute_file_sha256", return_value="sha256_abc")
    def test_unified_execute_non_builtin_trust_check(self, mock_sha, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        entry = _MockFunctionEntry(
            pack_id="user_pack",
            qualified_name="user_pack:test_func",
            vocab_aliases=["test.perm"],
            main_py_path="/fake/handler.py",
        )

        trust_store = MagicMock()
        trust_store.is_trusted.return_value = _MockTrustResult(trusted=False, reason="not in allowlist")

        executor = _make_executor(trust_store=trust_store)

        with patch("pathlib.Path.is_file", return_value=True):
            resp = executor._unified_execute(
                entry, "principal_a",
                {"permission_id": "test.perm", "args": {}},
                start_time=time.time(),
            )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "trust_denied")
        trust_store.is_trusted.assert_called_once_with("user_pack:test_func", "sha256_abc")


class TestUnifiedExecuteGrantCheckOptIn(unittest.TestCase):
    """test 6: grant_config がある entry で Grant チェックが実行されること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_grant_check_opt_in(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        entry = _MockFunctionEntry(
            pack_id="core_test",
            qualified_name="core_test:test_func",
            vocab_aliases=["test.perm"],
            grant_config={"some": "config"},
        )

        grant_manager = MagicMock()
        grant_manager.check.return_value = _MockGrantResult(allowed=False, reason="No grant")

        executor = _make_executor(grant_manager=grant_manager)

        resp = executor._unified_execute(
            entry, "principal_a",
            {"permission_id": "test.perm", "args": {}},
            start_time=time.time(),
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "grant_denied")
        grant_manager.check.assert_called_once_with("principal_a", "test.perm")


class TestUnifiedExecuteGrantCheckSkip(unittest.TestCase):
    """test 7: grant_config が None の entry で Grant チェックがスキップされること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_grant_check_skip(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        entry = _MockFunctionEntry(
            pack_id="core_test",
            qualified_name="core_test:test_func",
            vocab_aliases=["test.perm"],
            grant_config=None,
            entrypoint="handler.py:execute",
            function_dir="/fake/dir",
        )

        grant_manager = MagicMock()
        executor = _make_executor(grant_manager=grant_manager)

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
                resp = executor._unified_execute(
                    entry, "principal_a",
                    {"permission_id": "test.perm", "args": {}},
                    start_time=time.time(),
                )

        # Grant manager should NOT be called (grant_config is None)
        grant_manager.check.assert_not_called()


class TestUnifiedExecuteFlowRunDispatch(unittest.TestCase):
    """test 8: vocab_aliases に "flow.run" を含む entry で _execute_flow_run が呼ばれること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_flow_run_dispatch(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        entry = _MockFunctionEntry(
            pack_id="core_flow",
            qualified_name="core_flow:run",
            vocab_aliases=["flow.run"],
        )

        executor = _make_executor()
        executor._kernel = MagicMock()
        executor._kernel.execute_flow_sync.return_value = {"status": "done"}

        resp = executor._unified_execute(
            entry, "principal_a",
            {"permission_id": "flow.run", "args": {"flow_id": "my_flow", "inputs": {}}},
            start_time=time.time(),
        )

        self.assertTrue(resp.success)
        executor._kernel.execute_flow_sync.assert_called_once()


class TestUnifiedExecuteSubprocessDispatch(unittest.TestCase):
    """test 9: 通常の entry で _execute_handler_subprocess が呼ばれること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_unified_execute_subprocess_dispatch(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        entry = _MockFunctionEntry(
            pack_id="core_test",
            qualified_name="core_test:test_func",
            vocab_aliases=["test.perm"],
            entrypoint="handler.py:execute",
            function_dir="/fake/dir",
        )

        executor = _make_executor()

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
                resp = executor._unified_execute(
                    entry, "principal_a",
                    {"permission_id": "test.perm", "args": {}},
                    start_time=time.time(),
                )

        # Should succeed via subprocess path
        self.assertTrue(resp.success)


# =====================================================================
# _legacy_execute tests
# =====================================================================

class TestLegacyExecuteWarningLog(unittest.TestCase):
    """test 10: _legacy_execute が警告ログを出力すること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch("core_runtime.capability_executor.logger")
    def test_legacy_execute_warning_log(self, mock_logger, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        registry = MagicMock()
        registry.get_by_permission_id.return_value = None

        executor = _make_executor(handler_registry=registry)

        resp = executor._legacy_execute(
            "principal_a",
            {"permission_id": "test.perm", "args": {}},
            start_time=time.time(),
        )

        # Check that warning was logged
        mock_logger.warning.assert_called()
        warning_call_args = mock_logger.warning.call_args
        self.assertIn("Legacy handler path used", warning_call_args[0][0])


class TestLegacyExecuteStrictModeRejects(unittest.TestCase):
    """test 11: RUMI_STRICT_LEGACY=1 でエラーが返ること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch.dict(os.environ, {"RUMI_STRICT_LEGACY": "1"})
    def test_legacy_execute_strict_mode_rejects(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        executor = _make_executor()

        resp = executor._legacy_execute(
            "principal_a",
            {"permission_id": "test.perm", "args": {}},
            start_time=time.time(),
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "legacy_path_disabled")


class TestLegacyExecuteNormalModePasses(unittest.TestCase):
    """test 12: RUMI_STRICT_LEGACY=0（デフォルト）で既存処理が実行されること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    @patch.dict(os.environ, {"RUMI_STRICT_LEGACY": "0"}, clear=False)
    def test_legacy_execute_normal_mode_passes(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        registry = MagicMock()
        registry.get_by_permission_id.return_value = None

        executor = _make_executor(handler_registry=registry)

        resp = executor._legacy_execute(
            "principal_a",
            {"permission_id": "test.perm", "args": {}},
            start_time=time.time(),
        )

        # Should fall through to handler_not_found (not strict rejection)
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "handler_not_found")


# =====================================================================
# execute() integration tests
# =====================================================================

class TestExecuteFunctionCallUnchanged(unittest.TestCase):
    """test 13: function.call リクエストが既存パスを通ること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_execute_function_call_unchanged(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        executor = _make_executor()

        # Mock _execute_function_call to verify it's called
        mock_fc = MagicMock(return_value=CapabilityResponse(success=True, output="fc_result"))
        executor._execute_function_call = mock_fc

        resp = executor.execute(
            "principal_a",
            {"type": "function.call", "qualified_name": "pk:fn", "args": {}},
        )

        self.assertTrue(resp.success)
        self.assertEqual(resp.output, "fc_result")
        mock_fc.assert_called_once()


class TestExecuteResolvedEntryUsesUnified(unittest.TestCase):
    """test 14: permission_id が FunctionRegistry で解決される場合に _unified_execute が使われること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_execute_resolved_entry_uses_unified(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        entry = _MockFunctionEntry(vocab_aliases=["test.perm"])
        fr = MagicMock()
        fr.resolve_by_alias.return_value = entry

        executor = _make_executor(function_registry=fr)

        # Mock _unified_execute to verify it's called
        mock_unified = MagicMock(
            return_value=CapabilityResponse(success=True, output="unified_result")
        )
        executor._unified_execute = mock_unified

        resp = executor.execute(
            "principal_a",
            {"permission_id": "test.perm", "args": {}},
        )

        self.assertTrue(resp.success)
        self.assertEqual(resp.output, "unified_result")
        mock_unified.assert_called_once()
        # Verify entry was passed as first arg
        call_args = mock_unified.call_args
        self.assertIs(call_args[0][0], entry)


class TestExecuteUnresolvedFallsBackToLegacy(unittest.TestCase):
    """test 15: permission_id が解決できない場合に _legacy_execute が使われること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_execute_unresolved_falls_back_to_legacy(self, mock_audit_module):
        mock_audit_module.return_value = MagicMock()

        fr = MagicMock()
        fr.resolve_by_alias.return_value = None

        executor = _make_executor(function_registry=fr)

        # Mock _legacy_execute to verify it's called
        mock_legacy = MagicMock(
            return_value=CapabilityResponse(success=False, error="legacy", error_type="handler_not_found")
        )
        executor._legacy_execute = mock_legacy

        resp = executor.execute(
            "principal_a",
            {"permission_id": "unknown.perm", "args": {}},
        )

        self.assertFalse(resp.success)
        mock_legacy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
