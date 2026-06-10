"""
test_capability_executor_security.py - CapabilityExecutor セキュリティ修正のユニットテスト

対象: core_runtime/capability_executor.py (Wave 1-1 〜 1-4)
pytest ベース。mock/monkeypatch で環境変数を制御。
"""
from __future__ import annotations

import os
import sys
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.contract

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.capability_executor import (
    CapabilityExecutor,
    CapabilityResponse,
    _sanitize_error,
    _get_secure_tmp_dir,
)


# ---------------------------------------------------------------------------
# テスト用 FunctionEntry モック
# ---------------------------------------------------------------------------
@dataclass
class _MockFunctionEntry:
    """FunctionEntry の必要フィールドを模倣"""
    pack_id: str = "test_pack"
    function_id: str = "test_func"
    qualified_name: str = "test_pack.test_func"
    function_dir: Optional[str] = "/tmp/test_func_dir"
    main_py_path: Optional[str] = "/tmp/test_func_dir/main.py"
    main_binary_path: Optional[str] = None
    entrypoint: Optional[str] = "main.py:run"
    calling_convention: Optional[str] = None
    runtime: str = "python"
    host_execution: bool = False
    manifest: Optional[Dict] = None
    grant_config: Optional[Dict] = None
    vocab_aliases: Optional[List[str]] = None
    requires: Optional[List[str]] = None
    caller_requires: Optional[List[str]] = None
    docker_image: str = ""
    command: Optional[List[str]] = None

    def __post_init__(self):
        if self.manifest is None:
            self.manifest = {}
        if self.vocab_aliases is None:
            self.vocab_aliases = []


def _make_test_executor() -> CapabilityExecutor:
    """テスト用 CapabilityExecutor を生成"""
    executor = CapabilityExecutor()
    executor._initialized = True
    executor._trust_store = MagicMock()
    executor._grant_manager = MagicMock()
    executor._function_registry = MagicMock()
    executor._approval_manager = None
    executor._permission_manager = None
    return executor


# ===========================================================================
# Wave 1-1: Docker 未使用時フォールバック禁止
# ===========================================================================
class TestDockerFallbackBlocked:
    """RUMI_ALLOW_HOST_FALLBACK 未設定時にフォールバックがブロックされること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_fallback_blocked_without_env(self, mock_audit, monkeypatch):
        """RUMI_ALLOW_HOST_FALLBACK 未設定 → docker_unavailable エラー"""
        monkeypatch.delenv("RUMI_ALLOW_HOST_FALLBACK", raising=False)
        executor = _make_test_executor()
        entry = _MockFunctionEntry(
            host_execution=False,
            runtime="python",
            function_dir="/tmp/test_func_dir",
            main_py_path="/tmp/test_func_dir/main.py",
        )
        # Docker unavailable をシミュレート
        with patch.object(executor, "_is_docker_available", return_value=False):
            with patch("core_runtime.capability_executor._DockerRunBuilder", None):
                with patch("pathlib.Path.is_dir", return_value=True):
                    with patch("pathlib.Path.is_file", return_value=True):
                        resp = executor._execute_user_function(
                            principal_id="test_principal",
                            entry=entry,
                            args={},
                            request_id="req_001",
                            start_time=time.time(),
                        )
        assert not resp.success
        assert resp.error_type == "docker_unavailable"
        assert "RUMI_ALLOW_HOST_FALLBACK" in resp.error


class TestDockerFallbackAllowed:
    """RUMI_ALLOW_HOST_FALLBACK=true 時にフォールバックが許可されること"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_fallback_allowed_with_env(self, mock_audit, monkeypatch, tmp_path):
        """RUMI_ALLOW_HOST_FALLBACK=true → _execute_user_function_host が呼ばれる"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_FALLBACK", "true")
        executor = _make_test_executor()

        func_dir = tmp_path / "test_func"
        func_dir.mkdir()
        main_py = func_dir / "main.py"
        main_py.write_text('def run(ctx, args): return {"ok": True}', encoding="utf-8")

        entry = _MockFunctionEntry(
            host_execution=False,
            runtime="python",
            function_dir=str(func_dir),
            main_py_path=str(main_py),
        )
        mock_resp = CapabilityResponse(success=True, output={"ok": True})
        with patch.object(executor, "_is_docker_available", return_value=False):
            with patch("core_runtime.capability_executor._DockerRunBuilder", None):
                with patch.object(executor, "_execute_user_function_host", return_value=mock_resp) as mock_host:
                    resp = executor._execute_user_function(
                        principal_id="test_principal",
                        entry=entry,
                        args={},
                        request_id="req_002",
                        start_time=time.time(),
                    )
        assert resp.success
        mock_host.assert_called_once()


class TestDockerStrictBoundary:
    """strict policy 時は Docker 不可で host fallback しないこと"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_strict_mode_blocks_host_fallback_even_when_env_allows(self, mock_audit, monkeypatch, tmp_path):
        monkeypatch.setenv("RUMI_ALLOW_HOST_FALLBACK", "true")
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        executor = _make_test_executor()

        func_dir = tmp_path / "test_func"
        func_dir.mkdir()
        main_py = func_dir / "main.py"
        main_py.write_text('def run(ctx, args): return {"ok": True}', encoding="utf-8")

        entry = _MockFunctionEntry(
            host_execution=False,
            runtime="python",
            function_dir=str(func_dir),
            main_py_path=str(main_py),
        )
        with patch.object(executor, "_is_docker_available", return_value=False):
            with patch("core_runtime.capability_executor._DockerRunBuilder", None):
                with patch.object(executor, "_execute_user_function_host") as mock_host:
                    resp = executor._execute_user_function(
                        principal_id="test_principal",
                        entry=entry,
                        args={},
                        request_id="req_strict",
                        start_time=time.time(),
                    )

        assert resp.success is False
        assert resp.error_type == "docker_unavailable"
        assert "strict function isolation" in resp.error
        mock_host.assert_not_called()


class TestHighRiskApprovalCallerRequires:
    """user.approved.high_risk は permissive permission では満たせないこと"""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_permissive_permission_manager_does_not_satisfy_high_risk_approval(self, mock_audit):
        executor = _make_test_executor()
        func_dir = _project_root / "ecosystem" / "rumi_default_tools_pack" / "functions" / "computer_use"
        entry = _MockFunctionEntry(
            pack_id="rumi_default_tools_pack",
            function_id="computer_use",
            qualified_name="rumi_default_tools_pack:computer_use",
            function_dir=str(func_dir),
            main_py_path=str(func_dir / "main.py"),
            caller_requires=["user.approved.high_risk"],
        )
        executor._function_registry.get.return_value = entry
        executor._permission_manager = MagicMock()
        executor._permission_manager.has_permission.return_value = True
        executor._permission_manager.check_caller_requires.return_value = True

        resp = executor.execute(
            "rumi_default_tools_pack",
            {
                "type": "function.call",
                "qualified_name": "rumi_default_tools_pack:computer_use",
                "args": {"action": "click"},
            },
        )

        assert resp.success is False
        assert resp.error_type == "caller_requires_denied"
        executor._permission_manager.check_caller_requires.assert_not_called()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_direct_alias_enforces_high_risk_caller_requires(self, mock_audit, tmp_path):
        executor = _make_test_executor()
        func_dir = tmp_path / "coding_terminal_exec"
        func_dir.mkdir()
        main_py = func_dir / "main.py"
        main_py.write_text('def run(context, args): return {"ok": True}', encoding="utf-8")
        entry = _MockFunctionEntry(
            pack_id="rumi_default_tools_pack",
            function_id="coding_terminal_exec",
            qualified_name="rumi_default_tools_pack:coding_terminal_exec",
            function_dir=str(func_dir),
            main_py_path=str(main_py),
            calling_convention="subprocess",
            grant_config=None,
            vocab_aliases=["defaults.coding.terminal_exec"],
            caller_requires=["user.approved.high_risk"],
        )
        executor._function_registry.get_by_permission_id.return_value = None
        executor._function_registry.resolve_by_alias.return_value = entry
        executor._trust_store.is_trusted.return_value = SimpleNamespace(trusted=True, reason="trusted")
        executor._permission_manager = MagicMock()
        executor._permission_manager.has_permission.return_value = True
        executor._permission_manager.check_caller_requires.return_value = True

        with patch.object(executor, "_dispatch_by_calling_convention") as mock_dispatch:
            resp = executor.execute(
                "low_privilege_pack",
                {
                    "permission_id": "defaults.coding.terminal_exec",
                    "args": {"command": "cat /dev/null; python3 -c 'print(1)'"},
                },
            )

        assert resp.success is False
        assert resp.error_type == "caller_requires_denied"
        executor._permission_manager.check_caller_requires.assert_not_called()
        mock_dispatch.assert_not_called()

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_direct_alias_enforces_manifest_requires(self, mock_audit, tmp_path):
        executor = _make_test_executor()
        func_dir = tmp_path / "coding_terminal_exec"
        func_dir.mkdir()
        main_py = func_dir / "main.py"
        main_py.write_text('def run(context, args): return {"ok": True}', encoding="utf-8")
        entry = _MockFunctionEntry(
            pack_id="third_party_pack",
            function_id="coding_terminal_exec",
            qualified_name="third_party_pack:coding_terminal_exec",
            function_dir=str(func_dir),
            main_py_path=str(main_py),
            calling_convention="subprocess",
            grant_config=None,
            vocab_aliases=["third_party.coding_terminal_exec"],
            requires=["coding.terminal.exec"],
        )
        executor._function_registry.get_by_permission_id.return_value = None
        executor._function_registry.resolve_by_alias.return_value = entry
        executor._trust_store.is_trusted.return_value = SimpleNamespace(trusted=True, reason="trusted")
        executor._permission_manager = MagicMock()
        executor._permission_manager.has_permission.return_value = False
        executor._grant_manager.check.return_value = SimpleNamespace(allowed=False, reason="not granted", config={})

        with patch.object(executor, "_dispatch_by_calling_convention") as mock_dispatch:
            resp = executor.execute(
                "low_privilege_pack",
                {
                    "permission_id": "third_party.coding_terminal_exec",
                    "args": {"command": "pwd"},
                },
            )

        assert resp.success is False
        assert resp.error_type == "requires_denied"
        mock_dispatch.assert_not_called()



class TestTrustedBuiltinPackIdentity:
    """Reserved built-in pack IDs must resolve to shipped built-in paths."""

    @patch("core_runtime.capability_executor.get_audit_logger", new_callable=MagicMock)
    def test_spoofed_builtin_pack_id_from_noncanonical_path_is_rejected(self, mock_audit, tmp_path):
        executor = _make_test_executor()
        evil_dir = tmp_path / "00evil" / "functions" / "spoof"
        evil_dir.mkdir(parents=True)
        entry = _MockFunctionEntry(
            pack_id="defaultspack",
            function_id="spoof",
            qualified_name="defaultspack:spoof",
            function_dir=str(evil_dir),
            main_py_path=str(evil_dir / "main.py"),
            requires=["definitely.not.granted"],
        )
        executor._function_registry.get.return_value = entry
        executor._approval_manager = MagicMock()
        executor._approval_manager.is_pack_approved_and_verified.return_value = (True, None)
        executor._permission_manager = MagicMock()
        executor._permission_manager.has_permission.return_value = True

        resp = executor.execute(
            "defaultspack",
            {
                "type": "function.call",
                "qualified_name": "defaultspack:spoof",
                "args": {},
            },
        )

        assert resp.success is False
        assert resp.error_type == "pack_not_approved"
        executor._approval_manager.is_pack_approved_and_verified.assert_not_called()
        executor._permission_manager.has_permission.assert_not_called()

# ===========================================================================
# Wave 1-2: _execute_command_function ガード
# ===========================================================================
class TestCommandFunctionHostExecutionGuard:
    """_execute_command_function の RUMI_ALLOW_HOST_EXECUTION ガードが機能すること"""

    def test_command_blocked_without_host_execution_env(self, monkeypatch):
        """RUMI_ALLOW_HOST_EXECUTION 未設定 → host_execution_disabled"""
        monkeypatch.delenv("RUMI_ALLOW_HOST_EXECUTION", raising=False)
        executor = _make_test_executor()
        entry = _MockFunctionEntry(command=["echo", "hello"])
        resp = executor._execute_command_function(
            principal_id="test_principal",
            entry=entry,
            args={},
            request_id="req_003",
            start_time=time.time(),
        )
        assert not resp.success
        assert resp.error_type == "host_execution_disabled"


class TestCommandFunctionPathTraversal:
    """_execute_command_function のパストラバーサル検証が機能すること"""

    def test_command_path_traversal_blocked(self, monkeypatch, tmp_path):
        """command[0] が function_dir の外を指す絶対パス → security_violation"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
        executor = _make_test_executor()

        func_dir = tmp_path / "func"
        func_dir.mkdir()
        outside_command = tmp_path / "evil_script"

        entry = _MockFunctionEntry(
            command=[str(outside_command)],
            function_dir=str(func_dir),
        )
        resp = executor._execute_command_function(
            principal_id="test_principal",
            entry=entry,
            args={},
            request_id="req_004",
            start_time=time.time(),
        )
        assert not resp.success
        assert resp.error_type == "security_violation"
        assert "escapes" in resp.error.lower()

    def test_python_command_cannot_use_inline_code(self, monkeypatch, tmp_path):
        """sys.executable + -c は function_dir 境界を回避できないこと"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
        executor = _make_test_executor()

        func_dir = tmp_path / "func"
        func_dir.mkdir()

        entry = _MockFunctionEntry(
            command=[sys.executable, "-c", "print('pwned')"],
            function_dir=str(func_dir),
        )
        resp = executor._execute_command_function(
            principal_id="test_principal",
            entry=entry,
            args={},
            request_id="req_005",
            start_time=time.time(),
        )
        assert not resp.success
        assert resp.error_type == "security_violation"
        assert "inside function directory" in resp.error.lower()

    def test_python_command_outside_script_blocked(self, monkeypatch, tmp_path):
        """sys.executable + function_dir 外のスクリプトは拒否されること"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
        executor = _make_test_executor()

        func_dir = tmp_path / "func"
        func_dir.mkdir()
        outside_script = tmp_path / "outside.py"
        outside_script.write_text("print('pwned')")

        entry = _MockFunctionEntry(
            command=[sys.executable, str(outside_script)],
            function_dir=str(func_dir),
        )
        resp = executor._execute_command_function(
            principal_id="test_principal",
            entry=entry,
            args={},
            request_id="req_006",
            start_time=time.time(),
        )
        assert not resp.success
        assert resp.error_type == "security_violation"
        assert "escapes" in resp.error.lower()


# ===========================================================================
# Wave 1-3: _sanitize_error
# ===========================================================================
class TestSanitizeErrorRemovesPaths:
    """_sanitize_error() がファイルパスを除去すること"""

    def test_sanitize_removes_unix_path(self, monkeypatch):
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        msg = 'Error at /home/user/project/src/main.py: something failed'
        result = _sanitize_error(msg)
        assert "/home/user/" not in result
        assert "<path>" in result

    def test_sanitize_removes_traceback(self, monkeypatch):
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        msg = 'File "/home/user/project/main.py", line 42, in foo'
        result = _sanitize_error(msg)
        assert "<traceback>" in result
        assert "line 42" not in result

    def test_sanitize_removes_env_vars(self, monkeypatch):
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        msg = "Config error: DATABASE_URL=postgres://secret@host/db"
        result = _sanitize_error(msg)
        assert "DATABASE_URL=" not in result
        assert "<env>" in result


class TestSanitizeErrorDevelopmentSkip:
    """_sanitize_error() が development 環境ではスキップされること"""

    def test_sanitize_skipped_in_development(self, monkeypatch):
        monkeypatch.setenv("RUMI_ENVIRONMENT", "development")
        msg = 'Error at /home/user/project/src/main.py: something failed'
        result = _sanitize_error(msg)
        assert result == msg  # サニタイズされない


# ===========================================================================
# Wave 1-4: 一時ファイルの安全化
# ===========================================================================
class TestSecureTmpDir:
    """一時ファイルが user_data/tmp/ に作成されること"""

    def test_get_secure_tmp_dir_creates_directory(self, monkeypatch, tmp_path):
        """_get_secure_tmp_dir が user_data/tmp/ を作成する"""
        import core_runtime.capability_executor as mod

        # グローバル変数をリセット
        original = mod._SECURE_TMP_DIR
        mod._SECURE_TMP_DIR = None

        # __file__ をモック用の場所に設定して user_data/tmp/ の基準パスを制御
        fake_core_runtime = tmp_path / "rumi_ai_1_10" / "core_runtime"
        fake_core_runtime.mkdir(parents=True)
        fake_file = fake_core_runtime / "capability_executor.py"
        fake_file.touch()

        expected_tmp = tmp_path / "rumi_ai_1_10" / "user_data" / "tmp"

        with patch.object(mod, "__file__", str(fake_file)):
            result = _get_secure_tmp_dir()

        assert Path(result) == expected_tmp
        assert expected_tmp.is_dir()
        # パーミッション確認 (Unix のみ)
        if os.name != "nt" and hasattr(os, "stat"):
            mode = oct(os.stat(str(expected_tmp)).st_mode & 0o777)
            assert mode == "0o700"

        # クリーンアップ
        mod._SECURE_TMP_DIR = original

    def test_mkstemp_uses_secure_dir(self, monkeypatch, tmp_path):
        """mkstemp が _get_secure_tmp_dir() のディレクトリを使用する"""
        secure_dir = tmp_path / "secure_tmp"
        secure_dir.mkdir(mode=0o700)

        with patch("core_runtime.capability_executor._get_secure_tmp_dir", return_value=str(secure_dir)):
            fd, path = tempfile.mkstemp(suffix=".py", dir=str(secure_dir))
            try:
                assert Path(path).parent == secure_dir
            finally:
                os.close(fd)
                os.unlink(path)
