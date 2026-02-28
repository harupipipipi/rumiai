"""
test_wave22e_docker_dispatch.py - W22-E docker.run in-process dispatch テスト

CapabilityExecutor の docker.* ディスパッチ機能をテストする。
DockerCapabilityHandler / GrantManager / DI コンテナは全てモック。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from core_runtime.capability_executor import (
    CapabilityExecutor,
    CapabilityResponse,
    DOCKER_PERMISSION_IDS,
    DOCKER_RUN_PERMISSION_ID,
    FLOW_RUN_PERMISSION_ID,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeHandlerDef:
    handler_id: str = "docker_run_handler"
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

    # mock _audit to avoid real file I/O
    ex._audit = MagicMock()

    return ex


# Shared patch for compute_file_sha256 (builtin handler sha256 calc)
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


# ---------------------------------------------------------------------------
# 1. docker.run が in-process dispatch される
# ---------------------------------------------------------------------------

class TestDockerRunDispatched:
    def test_docker_run_dispatched_in_process(self):
        """docker.run は _execute_docker_dispatch 経由で処理される"""
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = {
            "exit_code": 0,
            "stdout": "hello",
            "stderr": "",
            "container_name": "rumi-cap-test-abc",
        }

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_a", {
                "permission_id": "docker.run",
                "args": {"image": "alpine", "command": ["echo", "hi"]},
            })

        assert resp.success is True
        mock_handler.handle_run.assert_called_once()


# ---------------------------------------------------------------------------
# 2. handle_run が呼ばれる
# ---------------------------------------------------------------------------

class TestHandleRunCalled:
    def test_docker_run_calls_handle_run(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = {
            "exit_code": 0, "stdout": "", "stderr": "",
            "container_name": "c1",
        }

        with _patch_sha, _patch_di(mock_handler):
            ex.execute("pack_b", {
                "permission_id": "docker.run",
                "args": {"image": "ubuntu", "command": ["ls"]},
            })

        assert mock_handler.handle_run.call_count == 1


# ---------------------------------------------------------------------------
# 3. handle_run に正しい引数が渡される
# ---------------------------------------------------------------------------

class TestCorrectArgsPassed:
    def test_docker_run_correct_args_passed(self):
        grant_cfg = {"allowed_images": ["alpine"], "max_memory": "512m"}
        ex = _make_executor(grant_result=FakeGrantResult(config=grant_cfg))
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = {
            "exit_code": 0, "stdout": "", "stderr": "",
            "container_name": "c1",
        }

        req_args = {"image": "alpine", "command": ["echo", "ok"]}

        with _patch_sha, _patch_di(mock_handler):
            ex.execute("pack_c", {
                "permission_id": "docker.run",
                "args": req_args,
            })

        call_kwargs = mock_handler.handle_run.call_args
        assert call_kwargs.kwargs["principal_id"] == "pack_c"
        assert call_kwargs.kwargs["args"] == req_args
        assert call_kwargs.kwargs["grant_config"] == grant_cfg


# ---------------------------------------------------------------------------
# 4. 成功レスポンスが CapabilityResponse に正しく変換される
# ---------------------------------------------------------------------------

class TestSuccessResponse:
    def test_docker_run_success_response(self):
        ex = _make_executor()
        result_dict = {
            "exit_code": 0,
            "stdout": "output",
            "stderr": "",
            "container_name": "rumi-cap-x-123",
        }
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = result_dict

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_d", {
                "permission_id": "docker.run",
                "args": {"image": "alpine", "command": ["echo"]},
            })

        assert resp.success is True
        assert resp.output == result_dict
        assert resp.error is None


# ---------------------------------------------------------------------------
# 5. handle_run がエラーを返した場合の CapabilityResponse
# ---------------------------------------------------------------------------

class TestErrorResponse:
    def test_docker_run_error_response(self):
        ex = _make_executor()
        error_result = {"error": "Image not allowed: evil"}
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = error_result

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_e", {
                "permission_id": "docker.run",
                "args": {"image": "evil", "command": ["rm", "-rf", "/"]},
            })

        assert resp.success is False
        assert resp.error == "Image not allowed: evil"
        assert resp.error_type == "docker_run_error"
        assert resp.output == error_result


# ---------------------------------------------------------------------------
# 6. DockerCapabilityHandler が DI コンテナに未登録の場合のエラー
# ---------------------------------------------------------------------------

class TestHandlerNotRegistered:
    def test_docker_handler_not_registered(self):
        ex = _make_executor()

        with _patch_sha, _patch_di(None):
            resp = ex.execute("pack_f", {
                "permission_id": "docker.run",
                "args": {"image": "alpine", "command": ["echo"]},
            })

        assert resp.success is False
        assert "not available" in resp.error
        assert resp.error_type == "initialization_error"


# ---------------------------------------------------------------------------
# 7. Grant がない場合のエラー
# ---------------------------------------------------------------------------

class TestNoGrant:
    def test_docker_run_no_grant(self):
        ex = _make_executor(
            grant_result=FakeGrantResult(
                allowed=False,
                reason="No capability grant for principal 'pack_g'",
            ),
        )

        with _patch_sha:
            resp = ex.execute("pack_g", {
                "permission_id": "docker.run",
                "args": {"image": "alpine", "command": ["echo"]},
            })

        assert resp.success is False
        assert resp.error_type == "grant_denied"


# ---------------------------------------------------------------------------
# 8. handle_run が例外を投げた場合の安全なエラーレスポンス
# ---------------------------------------------------------------------------

class TestExceptionHandling:
    def test_docker_run_exception_handling(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_run.side_effect = RuntimeError("Docker daemon crashed")

        with _patch_sha, _patch_di(mock_handler):
            resp = ex.execute("pack_h", {
                "permission_id": "docker.run",
                "args": {"image": "alpine", "command": ["echo"]},
            })

        assert resp.success is False
        assert "Docker daemon crashed" in resp.error
        assert resp.error_type == "docker_execution_error"


# ---------------------------------------------------------------------------
# 9. docker.exec 等の未実装 permission_id に対する「未実装」エラー
# ---------------------------------------------------------------------------

class TestNotImplemented:
    @pytest.mark.parametrize("perm_id", [
        "docker.exec", "docker.stop", "docker.logs", "docker.list",
    ])
    def test_docker_exec_not_implemented(self, perm_id):
        hdef = FakeHandlerDef(handler_id=f"{perm_id}_handler")
        ex = _make_executor(handler_def=hdef)

        with _patch_sha, _patch_di(MagicMock()):
            resp = ex.execute("pack_i", {
                "permission_id": perm_id,
                "args": {},
            })

        assert resp.success is False
        assert "not yet implemented" in resp.error
        assert resp.error_type == "not_implemented"


# ---------------------------------------------------------------------------
# 10. 通常の（非 docker）permission_id が従来のパスを通ること（回帰テスト）
# ---------------------------------------------------------------------------

class TestNonDockerRegression:
    def test_non_docker_permission_subprocess_path(self):
        """file.read 等はサブプロセス実行パスに到達する"""
        hdef = FakeHandlerDef(
            handler_id="file_read_handler",
            is_builtin=True,
            entrypoint="handler.py:handle",
        )
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


# ---------------------------------------------------------------------------
# 11. flow.run が従来のパスを通ること（回帰テスト）
# ---------------------------------------------------------------------------

class TestFlowRunRegression:
    def test_flow_run_still_works(self):
        """flow.run は _execute_flow_run に到達する"""
        hdef = FakeHandlerDef(handler_id="flow_run_handler")
        ex = _make_executor(handler_def=hdef)
        ex._execute_flow_run = MagicMock(
            return_value=CapabilityResponse(success=True, output={"result": "ok"}),
        )

        with _patch_sha:
            resp = ex.execute("pack_k", {
                "permission_id": "flow.run",
                "args": {"flow_id": "my_flow"},
            })

        assert resp.success is True
        ex._execute_flow_run.assert_called_once()


# ---------------------------------------------------------------------------
# 12. 監査ログが記録されること
# ---------------------------------------------------------------------------

class TestAuditLogged:
    def test_docker_run_audit_logged(self):
        ex = _make_executor()
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = {
            "exit_code": 0, "stdout": "", "stderr": "",
            "container_name": "c1",
        }

        with _patch_sha, _patch_di(mock_handler):
            ex.execute("pack_l", {
                "permission_id": "docker.run",
                "args": {"image": "alpine", "command": ["echo"]},
            })

        assert ex._audit.call_count >= 1
        call_args = ex._audit.call_args
        assert call_args[0][0] == "pack_l"         # principal_id
        assert call_args[0][1] == "docker.run"      # permission_id


# ---------------------------------------------------------------------------
# 13. grant_config がそのまま handle_run に転送される
# ---------------------------------------------------------------------------

class TestGrantConfigForwarded:
    def test_docker_run_grant_config_forwarded(self):
        custom_cfg = {
            "allowed_images": ["python:3.12-slim"],
            "max_memory": "128m",
            "max_cpus": "1.0",
            "network_allowed": False,
        }
        ex = _make_executor(grant_result=FakeGrantResult(config=custom_cfg))
        mock_handler = MagicMock()
        mock_handler.handle_run.return_value = {
            "exit_code": 0, "stdout": "", "stderr": "",
            "container_name": "c2",
        }

        with _patch_sha, _patch_di(mock_handler):
            ex.execute("pack_m", {
                "permission_id": "docker.run",
                "args": {"image": "python:3.12-slim", "command": ["python", "-c", "1"]},
            })

        passed_cfg = mock_handler.handle_run.call_args.kwargs["grant_config"]
        assert passed_cfg == custom_cfg
