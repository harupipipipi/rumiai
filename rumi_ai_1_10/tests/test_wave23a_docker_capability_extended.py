"""Tests for DockerCapabilityHandler W23-A extensions.

handle_exec, handle_stop, handle_logs, handle_list,
post-build assertion のテスト。
subprocess.run を mock して Docker が無い環境でも全テスト実行可能。
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from core_runtime.docker_capability import DockerCapabilityHandler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def handler() -> DockerCapabilityHandler:
    """新しい DockerCapabilityHandler インスタンスを返す。"""
    return DockerCapabilityHandler()


@pytest.fixture
def handler_with_containers() -> DockerCapabilityHandler:
    """コンテナが登録済みの DockerCapabilityHandler を返す。"""
    h = DockerCapabilityHandler()
    h._active_containers = {
        "rumi-cap-pack001-aaa": "pack-001",
        "rumi-cap-pack001-bbb": "pack-001",
        "rumi-cap-pack002-ccc": "pack-002",
    }
    return h


@pytest.fixture
def base_grant() -> dict:
    """基本的な grant_config を返す。"""
    return {
        "allowed_images": ["python:3.*-slim"],
        "max_memory": "512m",
        "max_cpus": "1.0",
        "max_pids": 100,
        "network_allowed": False,
        "max_containers": 3,
        "max_execution_time": 120,
    }


def _mock_completed(
    returncode: int = 0, stdout: str = "ok", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# handle_exec
# ---------------------------------------------------------------------------

class TestHandleExec:
    """handle_exec のテスト。"""

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed(stdout="hello"))
    def test_exec_success(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """所有コンテナへの exec が成功する。"""
        args = {
            "container_name": "rumi-cap-pack001-aaa",
            "command": ["echo", "hello"],
        }
        result = handler_with_containers.handle_exec("pack-001", args, {})
        assert "error" not in result
        assert result["exit_code"] == 0
        assert result["stdout"] == "hello"
        cmd = mock_run.call_args[0][0]
        assert cmd[0:2] == ["docker", "exec"]
        assert "rumi-cap-pack001-aaa" in cmd
        assert "echo" in cmd
        assert "hello" in cmd

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_exec_other_principal_denied(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """他の principal のコンテナへの exec は拒否される。"""
        args = {
            "container_name": "rumi-cap-pack002-ccc",
            "command": ["echo", "hi"],
        }
        result = handler_with_containers.handle_exec("pack-001", args, {})
        assert "error" in result
        assert "Access denied" in result["error"]
        mock_run.assert_not_called()

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_exec_nonexistent_container(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """存在しないコンテナへの exec はエラーになる。"""
        args = {
            "container_name": "nonexistent-container",
            "command": ["echo"],
        }
        result = handler_with_containers.handle_exec("pack-001", args, {})
        assert "error" in result
        assert "not found" in result["error"]
        mock_run.assert_not_called()

    @patch("core_runtime.docker_capability.subprocess.run",
           side_effect=subprocess.TimeoutExpired(cmd=[], timeout=5))
    def test_exec_timeout(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """exec の timeout 超過でエラーになる。"""
        args = {
            "container_name": "rumi-cap-pack001-aaa",
            "command": ["sleep", "999"],
            "timeout": 5,
        }
        result = handler_with_containers.handle_exec("pack-001", args, {})
        assert "error" in result
        assert result["error"] == "timeout"
        assert result["exit_code"] == -1

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_exec_with_working_dir(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """working_dir が docker exec に渡される。"""
        args = {
            "container_name": "rumi-cap-pack001-aaa",
            "command": ["ls"],
            "working_dir": "/app",
        }
        result = handler_with_containers.handle_exec("pack-001", args, {})
        assert "error" not in result
        cmd = mock_run.call_args[0][0]
        assert "-w" in cmd
        w_idx = cmd.index("-w")
        assert cmd[w_idx + 1] == "/app"


# ---------------------------------------------------------------------------
# handle_stop
# ---------------------------------------------------------------------------

class TestHandleStop:
    """handle_stop のテスト。"""

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_stop_success(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """所有コンテナの停止が成功し、_active_containers から除去される。"""
        args = {"container_name": "rumi-cap-pack001-aaa"}
        result = handler_with_containers.handle_stop("pack-001", args, {})
        assert result["stopped"] is True
        assert result["container_name"] == "rumi-cap-pack001-aaa"
        assert "rumi-cap-pack001-aaa" not in handler_with_containers._active_containers

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_stop_other_principal_denied(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """他の principal のコンテナの停止は拒否される。"""
        args = {"container_name": "rumi-cap-pack002-ccc"}
        result = handler_with_containers.handle_stop("pack-001", args, {})
        assert "error" in result
        assert "Access denied" in result["error"]
        mock_run.assert_not_called()
        assert "rumi-cap-pack002-ccc" in handler_with_containers._active_containers

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_stop_then_list_empty(
        self, mock_run: MagicMock,
    ) -> None:
        """停止後に handle_list で表示されないこと。"""
        h = DockerCapabilityHandler()
        h._active_containers = {"rumi-cap-pack001-xxx": "pack-001"}
        args_stop = {"container_name": "rumi-cap-pack001-xxx"}
        h.handle_stop("pack-001", args_stop, {})
        result = h.handle_list("pack-001", {}, {})
        assert result["containers"] == []


# ---------------------------------------------------------------------------
# handle_logs
# ---------------------------------------------------------------------------

class TestHandleLogs:
    """handle_logs のテスト。"""

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed(stdout="line1", stderr=""))
    def test_logs_success(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """所有コンテナのログ取得が成功する。"""
        args = {"container_name": "rumi-cap-pack001-aaa"}
        result = handler_with_containers.handle_logs("pack-001", args, {})
        assert "error" not in result
        assert "stdout" in result
        assert "stderr" in result

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_logs_tail_param(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """tail パラメータが docker logs コマンドに渡される。"""
        args = {"container_name": "rumi-cap-pack001-aaa", "tail": 50}
        handler_with_containers.handle_logs("pack-001", args, {})
        cmd = mock_run.call_args[0][0]
        assert "--tail=50" in cmd

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_logs_since_param(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """since パラメータが docker logs コマンドに渡される。"""
        args = {
            "container_name": "rumi-cap-pack001-aaa",
            "since": "2025-01-01T00:00:00",
        }
        handler_with_containers.handle_logs("pack-001", args, {})
        cmd = mock_run.call_args[0][0]
        assert "--since=2025-01-01T00:00:00" in cmd

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_logs_other_principal_denied(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """他の principal のコンテナのログ取得は拒否される。"""
        args = {"container_name": "rumi-cap-pack002-ccc"}
        result = handler_with_containers.handle_logs("pack-001", args, {})
        assert "error" in result
        assert "Access denied" in result["error"]
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# handle_list
# ---------------------------------------------------------------------------

class TestHandleList:
    """handle_list のテスト。"""

    def test_list_own_containers(
        self, handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """自分のコンテナのみ返される。"""
        result = handler_with_containers.handle_list("pack-001", {}, {})
        names = [c["name"] for c in result["containers"]]
        assert "rumi-cap-pack001-aaa" in names
        assert "rumi-cap-pack001-bbb" in names
        assert "rumi-cap-pack002-ccc" not in names
        assert len(result["containers"]) == 2
        for c in result["containers"]:
            assert c["status"] == "running"

    def test_list_empty(
        self, handler: DockerCapabilityHandler,
    ) -> None:
        """コンテナがない場合は空リストが返る。"""
        result = handler.handle_list("pack-001", {}, {})
        assert result["containers"] == []


# ---------------------------------------------------------------------------
# Post-build assertion
# ---------------------------------------------------------------------------

class TestPostBuildAssertion:
    """handle_run の post-build assertion のテスト。"""

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_normal_command_passes(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """正常なコマンドは post-build assertion を通過する。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        result = handler.handle_run("pack-001", args, base_grant)
        assert "error" not in result
        mock_run.assert_called_once()

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_privileged_rejected(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """--privileged を含むコマンドは拒否される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd.insert(3, "--privileged")
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            result = handler.handle_run("pack-001", args, base_grant)
            assert "error" in result
            assert "privileged" in result["error"]
            mock_run.assert_not_called()
        finally:
            drb.DockerRunBuilder.build = original_build

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_docker_sock_rejected(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """/var/run/docker.sock を含むコマンドは拒否される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd.insert(3, "-v")
            cmd.insert(4, "/var/run/docker.sock:/var/run/docker.sock")
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            result = handler.handle_run("pack-001", args, base_grant)
            assert "error" in result
            assert "docker.sock" in result["error"]
            mock_run.assert_not_called()
        finally:
            drb.DockerRunBuilder.build = original_build

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_net_host_rejected(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """--net=host を含むコマンドは拒否される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd = [x if x != "--network=none" else "--net=host" for x in cmd]
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            result = handler.handle_run("pack-001", args, base_grant)
            assert "error" in result
            assert "net=host" in result["error"]
            mock_run.assert_not_called()
        finally:
            drb.DockerRunBuilder.build = original_build

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_cap_add_rejected(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """--cap-add を含むコマンドは拒否される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd.insert(3, "--cap-add=SYS_ADMIN")
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            result = handler.handle_run("pack-001", args, base_grant)
            assert "error" in result
            assert "cap-add" in result["error"]
            mock_run.assert_not_called()
        finally:
            drb.DockerRunBuilder.build = original_build

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_pid_host_rejected(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """--pid=host を含むコマンドは拒否される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd.insert(3, "--pid=host")
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            result = handler.handle_run("pack-001", args, base_grant)
            assert "error" in result
            assert "pid=host" in result["error"]
            mock_run.assert_not_called()
        finally:
            drb.DockerRunBuilder.build = original_build

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_ipc_host_rejected(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """--ipc=host を含むコマンドは拒否される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd.insert(3, "--ipc=host")
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            result = handler.handle_run("pack-001", args, base_grant)
            assert "error" in result
            assert "ipc=host" in result["error"]
            mock_run.assert_not_called()
        finally:
            drb.DockerRunBuilder.build = original_build

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_network_host_rejected(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """--network=host を含むコマンドは拒否される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd = [x if x != "--network=none" else "--network=host" for x in cmd]
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            result = handler.handle_run("pack-001", args, base_grant)
            assert "error" in result
            assert "network=host" in result["error"]
            mock_run.assert_not_called()
        finally:
            drb.DockerRunBuilder.build = original_build


# ---------------------------------------------------------------------------
# Post-build assertion: critical 監査ログ確認
# ---------------------------------------------------------------------------

class TestPostBuildAudit:
    """post-build assertion で critical 監査ログが記録されることを確認。"""

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_privileged_critical_audit(
        self, mock_run: MagicMock,
        handler: DockerCapabilityHandler, base_grant: dict,
    ) -> None:
        """--privileged 検出時に severity=critical の監査ログが記録される。"""
        args = {
            "image": "python:3.11-slim",
            "command": ["python", "-c", "print(1)"],
        }
        import core_runtime.docker_run_builder as drb
        original_build = drb.DockerRunBuilder.build
        def patched_build(self_builder):
            cmd = original_build(self_builder)
            cmd.insert(3, "--privileged")
            return cmd
        drb.DockerRunBuilder.build = patched_build
        try:
            with patch.object(handler, "_audit_log") as mock_al:
                result = handler.handle_run("pack-001", args, base_grant)
                assert "error" in result
                critical_calls = [
                    c for c in mock_al.call_args_list
                    if c[0][0] == "critical"
                ]
                assert len(critical_calls) >= 1
                assert "post_build_assertion_failed" in critical_calls[0][0][1]
        finally:
            drb.DockerRunBuilder.build = original_build


# ---------------------------------------------------------------------------
# 監査ログ (各操作)
# ---------------------------------------------------------------------------

class TestAuditLogging:
    """各操作で監査ログが記録されることを確認。"""

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_exec_audit(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """handle_exec で監査ログが記録される。"""
        with patch.object(handler_with_containers, "_audit_log") as mock_al:
            args = {
                "container_name": "rumi-cap-pack001-aaa",
                "command": ["echo"],
            }
            handler_with_containers.handle_exec("pack-001", args, {})
            assert mock_al.called

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_stop_audit(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """handle_stop で監査ログが記録される。"""
        with patch.object(handler_with_containers, "_audit_log") as mock_al:
            args = {"container_name": "rumi-cap-pack001-aaa"}
            handler_with_containers.handle_stop("pack-001", args, {})
            assert mock_al.called

    @patch("core_runtime.docker_capability.subprocess.run",
           return_value=_mock_completed())
    def test_logs_audit(
        self, mock_run: MagicMock,
        handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """handle_logs で監査ログが記録される。"""
        with patch.object(handler_with_containers, "_audit_log") as mock_al:
            args = {"container_name": "rumi-cap-pack001-aaa"}
            handler_with_containers.handle_logs("pack-001", args, {})
            assert mock_al.called

    def test_list_audit(
        self, handler_with_containers: DockerCapabilityHandler,
    ) -> None:
        """handle_list で監査ログが記録される。"""
        with patch.object(handler_with_containers, "_audit_log") as mock_al:
            handler_with_containers.handle_list("pack-001", {}, {})
            assert mock_al.called
