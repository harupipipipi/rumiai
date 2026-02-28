"""
test_wave23c_docker_dispatch_extended.py - W23-C docker.* dispatch 拡張テスト

CapabilityExecutor の docker.exec / docker.stop / docker.logs / docker.list dispatch と
ApprovalManager のデッドコード削除を検証する。
"""
from __future__ import annotations

import inspect
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from core_runtime.capability_executor import (
    CapabilityExecutor,
    CapabilityResponse,
    DOCKER_PERMISSION_IDS,
    DOCKER_RUN_PERMISSION_ID,
    DOCKER_METHOD_MAP,
)
from core_runtime.approval_manager import ApprovalManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeHandlerDef:
    handler_id: str = "docker_handler"
    handler_py_path: str = "/fake/handler.py"
    is_builtin: bool = True
    entrypoint: str = "handler.py:handle"
    handler_dir: str = "/fake"


@dataclass
class FakeGrantResult:
    allowed: bool = True
    reason: str = "Granted"
    config: Dict[str, Any] = field(default_factory=dict)


def _make_executor(
    *,
    handler_def: Any = None,
    grant_result: Any = None,
) -> CapabilityExecutor:
    """Pre-initialised executor with mocked internals."""
    ex = CapabilityExecutor()
    ex._initialized = True

    registry = MagicMock()
    if handler_def is None:
        handler_def = FakeHandlerDef()
    registry.get_by_permission_id.return_value = handler_def
    ex._handler_registry = registry

    ex._trust_store = MagicMock()

    gm = MagicMock()
    if grant_result is None:
        grant_result = FakeGrantResult()
    gm.check.return_value = grant_result
    ex._grant_manager = gm

    ex._audit = MagicMock()

    return ex


_patch_sha = patch(
    "core_runtime.capability_handler_registry.compute_file_sha256",
    return_value="fakehash",
)


def _patch_di(mock_handler):
    """Return a context-manager that patches get_container to serve mock_handler."""
    mock_container = MagicMock()
    mock_container.get_or_none.return_value = mock_handler
    return patch(
        "core_runtime.di_container.get_container",
        return_value=mock_container,
    )


# ===========================================================================
# 1. docker.exec が handle_exec に dispatch される
# ===========================================================================

class TestDockerExecDispatched:
    def test_docker_exec_dispatched(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_exec.return_value = {"exit_code": 0, "stdout": "ok"}

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_a", {
                "permission_id": "docker.exec",
                "args": {"container": "c1", "command": ["ls"]},
            })

        assert resp.success is True
        mock_handler.handle_exec.assert_called_once()


# ===========================================================================
# 2. docker.stop が handle_stop に dispatch される
# ===========================================================================

class TestDockerStopDispatched:
    def test_docker_stop_dispatched(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_stop.return_value = {"stopped": True}

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_b", {
                "permission_id": "docker.stop",
                "args": {"container": "c1"},
            })

        assert resp.success is True
        mock_handler.handle_stop.assert_called_once()


# ===========================================================================
# 3. docker.logs が handle_logs に dispatch される
# ===========================================================================

class TestDockerLogsDispatched:
    def test_docker_logs_dispatched(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_logs.return_value = {"logs": "line1"}

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_c", {
                "permission_id": "docker.logs",
                "args": {"container": "c1"},
            })

        assert resp.success is True
        mock_handler.handle_logs.assert_called_once()


# ===========================================================================
# 4. docker.list が handle_list に dispatch される
# ===========================================================================

class TestDockerListDispatched:
    def test_docker_list_dispatched(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_list.return_value = {"containers": []}

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_d", {
                "permission_id": "docker.list",
                "args": {},
            })

        assert resp.success is True
        mock_handler.handle_list.assert_called_once()


# ===========================================================================
# 5. docker.exec で principal_id, args, grant_config が正しく渡される
# ===========================================================================

class TestDockerExecCorrectArgs:
    def test_docker_exec_correct_args(self):
        grant_cfg = {"allowed_containers": ["c1"]}
        ex = _make_executor(grant_result=FakeGrantResult(config=grant_cfg))
        mock_handler = MagicMock()
        mock_handler.handle_exec.return_value = {"exit_code": 0}

        req_args = {"container": "c1", "command": ["whoami"]}

        with _patch_sha, _patch_di(mock_handler):
            ex.execute("pack_e", {
                "permission_id": "docker.exec",
                "args": req_args,
            })

        kw = mock_handler.handle_exec.call_args.kwargs
        assert kw["principal_id"] == "pack_e"
        assert kw["args"] == req_args
        assert kw["grant_config"] == grant_cfg


# ===========================================================================
# 6. docker.stop で principal_id, args, grant_config が正しく渡される
# ===========================================================================

class TestDockerStopCorrectArgs:
    def test_docker_stop_correct_args(self):
        grant_cfg = {"timeout": 10}
        ex = _make_executor(grant_result=FakeGrantResult(config=grant_cfg))
        mock_handler = MagicMock()
        mock_handler.handle_stop.return_value = {"stopped": True}

        req_args = {"container": "c2"}

        with _patch_sha, _patch_di(mock_handler):
            ex.execute("pack_f", {
                "permission_id": "docker.stop",
                "args": req_args,
            })

        kw = mock_handler.handle_stop.call_args.kwargs
        assert kw["principal_id"] == "pack_f"
        assert kw["args"] == req_args
        assert kw["grant_config"] == grant_cfg


# ===========================================================================
# 7. Grant がない permission_id はエラーレスポンス
# ===========================================================================

class TestNoGrantError:
    def test_docker_exec_no_grant(self):
        ex = _make_executor(
            grant_result=FakeGrantResult(allowed=False, reason="No grant"),
        )

        with _patch_sha:
            resp = ex.execute("pack_g", {
                "permission_id": "docker.exec",
                "args": {},
            })

        assert resp.success is False
        assert resp.error_type == "grant_denied"


# ===========================================================================
# 8. DockerCapabilityHandler が DI 未登録ならエラー
# ===========================================================================

class TestHandlerNotRegisteredError:
    def test_docker_exec_handler_not_registered(self):
        ex = _make_executor()

        with _patch_sha, _patch_di(None):
            resp = ex.execute("pack_h", {
                "permission_id": "docker.exec",
                "args": {},
            })

        assert resp.success is False
        assert "not available" in resp.error
        assert resp.error_type == "initialization_error"


# ===========================================================================
# 9. handle_* が例外を投げた場合は安全なエラーレスポンス
# ===========================================================================

class TestHandleExceptionSafe:
    def test_docker_exec_exception_safe(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_exec.side_effect = RuntimeError("container not found")

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_i", {
                "permission_id": "docker.exec",
                "args": {"container": "missing"},
            })

        assert resp.success is False
        assert "container not found" in resp.error
        assert resp.error_type == "docker_execution_error"


# ===========================================================================
# 10. 非 docker の permission_id は従来のサブプロセスパスを通る（回帰テスト）
# ===========================================================================

class TestNonDockerRegression:
    def test_non_docker_subprocess_path(self):
        hdef = FakeHandlerDef(handler_id="file_read_handler")
        ex = _make_executor(handler_def=hdef)
        ex._execute_handler_subprocess = MagicMock(
            return_value=CapabilityResponse(success=True, output={"data": "ok"}),
        )

        with _patch_sha:
            resp = ex.execute("pack_j", {
                "permission_id": "file.read",
                "args": {"path": "/tmp/test.txt"},
            })

        assert resp.success is True
        ex._execute_handler_subprocess.assert_called_once()


# ===========================================================================
# 11. docker.run が引き続き動作する（回帰テスト）
# ===========================================================================

class TestDockerRunRegression:
    def test_docker_run_still_works(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = {
            "exit_code": 0,
            "stdout": "hello",
            "stderr": "",
            "container_name": "rumi-cap-test-abc",
        }

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_k", {
                "permission_id": "docker.run",
                "args": {"image": "alpine", "command": ["echo", "hi"]},
            })

        assert resp.success is True
        mock_handler.handle_run.assert_called_once()


# ===========================================================================
# 12. DOCKER_METHOD_MAP が全 DOCKER_PERMISSION_IDS をカバーしている
# ===========================================================================

class TestMethodMapCoversAll:
    def test_method_map_covers_all_permission_ids(self):
        assert set(DOCKER_METHOD_MAP.keys()) == set(DOCKER_PERMISSION_IDS)


# ===========================================================================
# 13. is_pack_approved_and_verified に core_pack チェックの重複がない
# ===========================================================================

class TestNoDuplicateCoreCheck:
    def test_no_duplicate_core_pack_check(self):
        source = inspect.getsource(
            ApprovalManager.is_pack_approved_and_verified
        )
        count = source.count("_is_core_pack")
        assert count == 1, (
            f"Expected exactly 1 call to _is_core_pack, found {count}"
        )


# ===========================================================================
# 14. core_ プレフィックスの pack_id が引き続き (True, None) を返す
# ===========================================================================

class TestCorePackStillApproved:
    def test_core_pack_returns_true_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ApprovalManager(
                packs_dir=tmpdir,
                grants_dir=os.path.join(tmpdir, "grants"),
                secret_key="test_secret_key",
            )
            mgr.initialize()
            result = mgr.is_pack_approved_and_verified("core_system")
            assert result == (True, None)


# ===========================================================================
# 15. 通常の pack_id が従来通り (False, "not_found") を返す
# ===========================================================================

class TestNormalPackNotFound:
    def test_normal_pack_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ApprovalManager(
                packs_dir=tmpdir,
                grants_dir=os.path.join(tmpdir, "grants"),
                secret_key="test_secret_key",
            )
            mgr.initialize()
            result = mgr.is_pack_approved_and_verified("my_custom_pack")
            assert result == (False, "not_found")
