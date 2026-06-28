"""
test_wave25_5_user_function.py - W25.5 user function subprocess execution tests

Tests:
- User function Docker container execution (mocked subprocess)
- User function host fallback execution
- host_execution function execution
- Error handling (timeout, invalid JSON, missing files, etc.)
- Regression tests for existing capability paths
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock
import tempfile
import shutil
import re

# Ensure project root is in path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.capability_executor import (
    CapabilityExecutor,
    CapabilityResponse,
    FUNCTION_RUNNER_PATH,
    MAX_RESPONSE_SIZE,
    DEFAULT_FUNCTION_TIMEOUT,
)
from core_runtime.function_registry import FunctionEntry

_CE_MODULE = CapabilityExecutor.__module__


def _patch_executor_globals(**values):
    return patch.dict(CapabilityExecutor._execute_user_function.__globals__, values)


# =====================================================================
# Helper: create a FunctionEntry mock
# =====================================================================

def _make_entry(
    pack_id="test_pack",
    function_id="test_func",
    host_execution=False,
    function_dir=None,
    main_py_path=None,
    manifest=None,
):
    """Create a FunctionEntry for testing."""
    if function_dir is None:
        function_dir = Path(tempfile.mkdtemp())
    else:
        function_dir = Path(function_dir)
    if main_py_path is None:
        mp = function_dir / "main.py"
        mp.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
        main_py_path = mp
    else:
        main_py_path = Path(main_py_path)
    return FunctionEntry(
        function_id=function_id,
        pack_id=pack_id,
        host_execution=host_execution,
        function_dir=function_dir,
        main_py_path=main_py_path,
        manifest=manifest or {},
    )


def _make_executor():
    """Create a minimally-initialized CapabilityExecutor for testing."""
    executor = CapabilityExecutor()
    executor._initialized = True
    executor._function_registry = MagicMock()
    executor._approval_manager = MagicMock()
    executor._permission_manager = MagicMock()
    executor._handler_registry = MagicMock()
    executor._trust_store = MagicMock()
    executor._grant_manager = MagicMock()

    # approval_manager: always approved
    executor._approval_manager.is_pack_approved_and_verified.return_value = (True, None)
    # permission_manager: always allow
    executor._permission_manager.has_permission.return_value = True
    executor._permission_manager.check_caller_requires.return_value = True

    return executor


def _make_subprocess_result(returncode=0, stdout="", stderr=""):
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# =====================================================================
# Tests
# =====================================================================

class TestUserFunctionDockerExecution(unittest.TestCase):
    """Test user function execution via Docker container."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_w255_")
        self.executor = _make_executor()
        self.executor._entry_requires_managed_sandbox = MagicMock(return_value=False)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    def test_user_function_docker_success(self, mock_shutil, mock_subprocess):
        """User function normal execution via Docker (returncode=0, valid JSON stdout)."""
        mock_shutil.which.return_value = "/usr/bin/docker"
        output_json = json.dumps({"result": "hello"})
        mock_subprocess.run.return_value = _make_subprocess_result(
            returncode=0, stdout=output_json
        )
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(
            pack_id="mypk", function_id="myfn",
            function_dir=self.tmpdir,
        )
        # Write main.py
        (Path(self.tmpdir) / "main.py").write_text(
            "def run(ctx, args): return {'result': 'hello'}\n"
        )
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={"x": 1},
                request_id="r1", start_time=time.time(),
            )
        self.assertTrue(resp.success)
        self.assertEqual(resp.output, {"result": "hello"})

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    def test_user_function_docker_mounts_only_runner_file_not_runtime_root(self, mock_shutil, mock_subprocess):
        """Docker user functions do not receive a bind mount for the runtime root/user_data tree."""
        mock_shutil.which.return_value = "/usr/bin/docker"
        mock_subprocess.run.return_value = _make_subprocess_result(returncode=0, stdout="{}")
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(pack_id="mypk", function_id="myfn", function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): return {}\n", encoding="utf-8")
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )

        self.assertTrue(resp.success)
        cmd = mock_subprocess.run.call_args.args[0]
        volumes = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-v"]
        runtime_root = str(Path(__file__).resolve().parents[1])
        self.assertNotIn(f"{runtime_root}:/runtime:ro", volumes)
        self.assertIn(f"{FUNCTION_RUNNER_PATH.resolve()}:/tmp/function_runner.py:ro", volumes)
        self.assertIn("/tmp/function_runner.py", cmd)

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    def test_user_function_docker_returncode_nonzero(self, mock_shutil, mock_subprocess):
        """User function execution error (returncode != 0)."""
        mock_shutil.which.return_value = "/usr/bin/docker"
        mock_subprocess.run.return_value = _make_subprocess_result(
            returncode=1, stderr="some error"
        )
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): pass\n")
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "function_execution_error")
        self.assertIn("some error", resp.error)

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    def test_user_function_docker_timeout(self, mock_shutil, mock_subprocess):
        """User function execution timeout."""
        mock_shutil.which.return_value = "/usr/bin/docker"
        mock_subprocess.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
        mock_subprocess.run.side_effect = mock_subprocess.TimeoutExpired()

        entry = _make_entry(function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): pass\n")
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "timeout")

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    def test_user_function_docker_invalid_json_stdout(self, mock_shutil, mock_subprocess):
        """User function stdout is not valid JSON."""
        mock_shutil.which.return_value = "/usr/bin/docker"
        mock_subprocess.run.return_value = _make_subprocess_result(
            returncode=0, stdout="not json at all"
        )
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): pass\n")
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "invalid_json_output")

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    def test_user_function_docker_empty_stdout(self, mock_shutil, mock_subprocess):
        """User function stdout is empty (success, output=None)."""
        mock_shutil.which.return_value = "/usr/bin/docker"
        mock_subprocess.run.return_value = _make_subprocess_result(
            returncode=0, stdout=""
        )
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): pass\n")
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertTrue(resp.success)
        self.assertIsNone(resp.output)

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    def test_user_function_docker_response_too_large(self, mock_shutil, mock_subprocess):
        """User function response exceeds MAX_RESPONSE_SIZE."""
        mock_shutil.which.return_value = "/usr/bin/docker"
        huge_output = "x" * (MAX_RESPONSE_SIZE + 100)
        mock_subprocess.run.return_value = _make_subprocess_result(
            returncode=0, stdout=huge_output
        )
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): pass\n")
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "response_too_large")

    def test_user_function_function_dir_not_found(self):
        """function_dir does not exist."""
        entry = FunctionEntry(
            function_id="test_func",
            pack_id="test_pack",
            function_dir=Path("/nonexistent/dir_w255"),
            main_py_path=Path("/nonexistent/dir_w255/main.py"),
            manifest={},
        )

        resp = self.executor._execute_user_function(
            principal_id="p1", entry=entry, args={},
            request_id="r1", start_time=time.time(),
        )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "function_dir_not_found")

    def test_user_function_main_py_not_found(self):
        """main_py_path does not exist but function_dir does."""
        entry = _make_entry(function_dir=self.tmpdir)
        entry.main_py_path = Path(self.tmpdir) / "nonexistent_main.py"

        resp = self.executor._execute_user_function(
            principal_id="p1", entry=entry, args={},
            request_id="r1", start_time=time.time(),
        )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "main_py_not_found")


class TestHostExecutionFunction(unittest.TestCase):
    """Test host_execution function execution."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_w255_host_")
        self.executor = _make_executor()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch.dict(os.environ, {"RUMI_ALLOW_HOST_EXECUTION": "1"})
    @patch(f"{_CE_MODULE}.subprocess")
    def test_host_function_success(self, mock_subprocess):
        """host_execution function normal execution."""
        output_json = json.dumps({"host_result": True})
        mock_subprocess.run.return_value = _make_subprocess_result(
            returncode=0, stdout=output_json
        )
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(
            host_execution=True,
            function_dir=self.tmpdir,
        )
        (Path(self.tmpdir) / "main.py").write_text(
            "def run(ctx, args): return {'host_result': True}\n"
        )
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess):
            resp = self.executor._execute_host_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertTrue(resp.success)
        self.assertEqual(resp.output, {"host_result": True})

    def test_host_function_disabled_by_default(self):
        """host_execution function is rejected when RUMI_ALLOW_HOST_EXECUTION is not set."""
        # Ensure the env var is NOT set
        env = os.environ.copy()
        env.pop("RUMI_ALLOW_HOST_EXECUTION", None)
        with patch.dict(os.environ, env, clear=True):
            entry = _make_entry(host_execution=True, function_dir=self.tmpdir)
            (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): pass\n")
            entry.main_py_path = Path(self.tmpdir) / "main.py"

            resp = self.executor._execute_host_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
            self.assertFalse(resp.success)
            self.assertEqual(resp.error_type, "host_execution_disabled")

    @patch.dict(os.environ, {"RUMI_ALLOW_HOST_EXECUTION": "true"})
    @patch(f"{_CE_MODULE}.subprocess")
    def test_host_function_timeout(self, mock_subprocess):
        """host_execution function timeout."""
        mock_subprocess.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
        mock_subprocess.run.side_effect = mock_subprocess.TimeoutExpired()

        entry = _make_entry(host_execution=True, function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text("def run(ctx, args): pass\n")
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess):
            resp = self.executor._execute_host_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "timeout")


class TestDockerFallback(unittest.TestCase):
    """Test Docker unavailable fallback to host subprocess."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_w255_fb_")
        self.executor = _make_executor()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch(f"{_CE_MODULE}.subprocess")
    @patch(f"{_CE_MODULE}.shutil")
    @patch.dict(os.environ, {"RUMI_ALLOW_HOST_FALLBACK": "1"})
    def test_docker_unavailable_fallback(self, mock_shutil, mock_subprocess):
        """When Docker is not available, user function fails closed at the managed sandbox boundary."""
        mock_shutil.which.return_value = None  # Docker not available
        output_json = json.dumps({"fallback": True})
        mock_subprocess.run.return_value = _make_subprocess_result(
            returncode=0, stdout=output_json
        )
        mock_subprocess.TimeoutExpired = TimeoutError

        entry = _make_entry(function_dir=self.tmpdir)
        (Path(self.tmpdir) / "main.py").write_text(
            "def run(ctx, args): return {'fallback': True}\n"
        )
        entry.main_py_path = Path(self.tmpdir) / "main.py"

        with _patch_executor_globals(subprocess=mock_subprocess, shutil=mock_shutil):
            resp = self.executor._execute_user_function(
                principal_id="p1", entry=entry, args={},
                request_id="r1", start_time=time.time(),
            )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "SANDBOX_RUNTIME_UNAVAILABLE")
        mock_subprocess.run.assert_not_called()


class TestContainerNameFormat(unittest.TestCase):
    """Test container name format for user functions."""

    def test_container_name_pattern(self):
        """Container name follows rumi-func-{pack_id}-{function_id}-{uuid[:8]} pattern."""
        import uuid as uuid_mod
        pack_id = "my-pack"
        function_id = "my-func"
        hex8 = uuid_mod.uuid4().hex[:8]
        name = f"rumi-func-{pack_id}-{function_id}-{hex8}"
        pattern = re.compile(r'^rumi-func-[\w-]+-[\w-]+-[0-9a-f]{8}$')
        self.assertRegex(name, pattern)


class TestRegressionCoreFunction(unittest.TestCase):
    """Regression: core function still routes to _dispatch_core_function."""

    def setUp(self):
        self.executor = _make_executor()

    def test_core_function_routes_to_dispatch(self):
        """core_pack function.call routes to _dispatch_core_function."""
        entry = _make_entry(pack_id="core_docker_capability", function_id="run")
        self.executor._function_registry.get.return_value = entry

        # Mock _dispatch_core_function
        self.executor._dispatch_core_function = MagicMock(
            return_value=CapabilityResponse(success=True, output={"dispatched": True})
        )

        request = {
            "type": "function.call",
            "qualified_name": "core_docker_capability:run",
            "args": {},
        }
        resp = self.executor.execute(principal_id="p1", request=request)
        self.assertTrue(resp.success)
        self.executor._dispatch_core_function.assert_called_once()


class TestRegressionPermissionBasedExecution(unittest.TestCase):
    """Regression: permission_id based execute() still works."""

    def setUp(self):
        self.executor = _make_executor()

    def test_permission_id_request_unaffected(self):
        """Permission-based requests (not function.call) still work via normal path."""
        handler_def = MagicMock()
        handler_def.handler_id = "test.handler.v1"
        handler_def.entrypoint = "handler.py:execute"
        handler_def.handler_dir = Path("/tmp/fake_handler")
        handler_def.handler_py_path = Path("/tmp/fake_handler/handler.py")
        handler_def.is_builtin = True

        self.executor._handler_registry.get_by_permission_id.return_value = handler_def
        self.executor._handler_registry.is_loaded.return_value = True

        # Trust: built-in bypass
        # Grant: allowed
        grant_result = MagicMock()
        grant_result.allowed = True
        grant_result.config = {}
        self.executor._grant_manager.check.return_value = grant_result

        # Mock subprocess execution
        self.executor._execute_handler_subprocess = MagicMock(
            return_value=CapabilityResponse(success=True, output={"ok": True})
        )

        request = {
            "permission_id": "test.echo",
            "args": {},
        }
        resp = self.executor.execute(principal_id="p1", request=request)
        self.assertTrue(resp.success)


class TestGenerateFunctionRunnerScript(unittest.TestCase):
    """Test _generate_function_runner_script method."""

    def test_script_is_valid_python(self):
        """Generated runner script is valid Python."""
        executor = CapabilityExecutor()
        script = executor._generate_function_runner_script()
        # Should compile without syntax errors
        compile(script, "<runner>", "exec")

    def test_script_contains_run_call(self):
        """Generated script calls run(context, args)."""
        executor = CapabilityExecutor()
        script = executor._generate_function_runner_script()
        self.assertIn("run", script)
        self.assertIn("context", script)
        self.assertIn("args", script)


class TestFunctionRunnerSubprocessEncoding(unittest.TestCase):
    """Regression coverage for Windows non-ASCII workspace paths."""

    def test_run_runner_on_host_uses_utf8_text_encoding(self):
        executor = CapabilityExecutor()
        mock_proc = _make_subprocess_result(returncode=0, stdout='{"result": "ok"}')
        payload = (
            '{"module_path": '
            '"C:\\\\Users\\\\ai\\\\OneDrive\\\\\\u30c9\\u30ad\\u30e5\\u30e1\\u30f3\\u30c8\\\\handler.py"}'
        )

        with patch(f"{_CE_MODULE}.subprocess.run", return_value=mock_proc) as mock_run:
            resp = executor._run_runner_on_host(
                payload=payload,
                cwd=".",
                timeout=5,
                start_time=time.time(),
                failure_prefix="Handler execution failed",
            )

        self.assertTrue(resp.success)
        self.assertEqual(mock_run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(mock_run.call_args.kwargs["errors"], "replace")

    def test_nonzero_runner_response_uses_stdout_json_error_when_stderr_is_empty(self):
        executor = CapabilityExecutor()
        proc = _make_subprocess_result(
            returncode=1,
            stdout='{"error": "utf-8 decode failed", "error_type": "UnicodeDecodeError"}',
            stderr="",
        )

        resp = executor._response_from_completed_process(
            proc,
            time.time(),
            "Handler execution failed",
        )

        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "function_execution_error")
        self.assertIn("utf-8 decode failed", resp.error)


class TestGetFunctionTimeout(unittest.TestCase):
    """Test _get_function_timeout method."""

    def test_default_timeout(self):
        """Default timeout when manifest has no grant_config."""
        executor = CapabilityExecutor()
        entry = _make_entry(manifest={})
        t = executor._get_function_timeout(entry)
        self.assertEqual(t, DEFAULT_FUNCTION_TIMEOUT)

    def test_custom_timeout_from_manifest(self):
        """Custom timeout from manifest grant_config."""
        executor = CapabilityExecutor()
        entry = _make_entry(manifest={"grant_config": {"timeout": 15}})
        t = executor._get_function_timeout(entry)
        self.assertEqual(t, 15.0)

    def test_timeout_capped_at_max(self):
        """Timeout is capped at MAX_TIMEOUT."""
        executor = CapabilityExecutor()
        entry = _make_entry(manifest={"grant_config": {"timeout": 9999}})
        t = executor._get_function_timeout(entry)
        # MAX_TIMEOUT is 300
        self.assertLessEqual(t, 300.0)


if __name__ == "__main__":
    unittest.main()
