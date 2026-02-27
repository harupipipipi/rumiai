"""
test_wave20b_container_cleanup.py
W20-B: VULN-H03 - コンテナ停止時の自動 cleanup テスト
"""
from __future__ import annotations

import subprocess
import sys
import types

# paths.py の BASE_DIR 未定義問題を回避
if "core_runtime.paths" not in sys.modules:
    _mock_paths = types.ModuleType("core_runtime.paths")
    _mock_paths.ECOSYSTEM_DIR = "/tmp/test_ecosystem"
    sys.modules["core_runtime.paths"] = _mock_paths

from unittest.mock import patch, MagicMock, call

from core_runtime.container_orchestrator import ContainerOrchestrator, ContainerResult


class TestStopContainerAutoCleanup:
    """stop_container() の自動 cleanup テスト"""

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_stop_calls_docker_rm_after_stop(self, mock_run):
        """docker stop の後に docker rm が呼ばれること"""
        orch = ContainerOrchestrator()
        orch.stop_container("abc123")

        assert mock_run.call_count == 2
        first_cmd = mock_run.call_args_list[0][0][0]
        second_cmd = mock_run.call_args_list[1][0][0]
        assert first_cmd == ["docker", "stop", "rumi-pack-abc123"]
        assert second_cmd == ["docker", "rm", "rumi-pack-abc123"]

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_stop_success_both_succeed(self, mock_run):
        """docker stop 成功 + docker rm 成功 → success=True"""
        mock_run.return_value = MagicMock(returncode=0)
        orch = ContainerOrchestrator()
        result = orch.stop_container("abc123")

        assert result.success is True
        assert result.error is None

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_stop_success_rm_fails(self, mock_run):
        """docker stop 成功 + docker rm 失敗(returncode=1) → success=True（rm失敗は無視）"""
        stop_result = MagicMock(returncode=0)
        rm_result = MagicMock(returncode=1, stderr=b"No such container")
        mock_run.side_effect = [stop_result, rm_result]

        orch = ContainerOrchestrator()
        result = orch.stop_container("abc123")

        assert result.success is True
        assert result.error is None

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_stop_failure_exception(self, mock_run):
        """docker stop が例外を投げた場合 → success=False"""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["docker", "stop"], timeout=30
        )
        orch = ContainerOrchestrator()
        result = orch.stop_container("abc123")

        assert result.success is False
        assert result.error is not None
        # docker rm は呼ばれない（stop で例外発生のため）
        assert mock_run.call_count == 1

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_stop_removes_from_containers_dict(self, mock_run):
        """stop_container() 後に _containers から pack_id が除去されること"""
        orch = ContainerOrchestrator()
        orch._containers["abc123"] = "container_id_xyz"

        result = orch.stop_container("abc123")

        assert result.success is True
        assert "abc123" not in orch._containers

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_remove_container_regression(self, mock_run):
        """remove_container() が従来通り docker rm -f を呼ぶこと（回帰テスト）"""
        orch = ContainerOrchestrator()
        orch._containers["abc123"] = "container_id_xyz"

        result = orch.remove_container("abc123")

        assert result.success is True
        mock_run.assert_called_once_with(
            ["docker", "rm", "-f", "rumi-pack-abc123"],
            capture_output=True,
            timeout=30,
        )
        assert "abc123" not in orch._containers

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_container_name_format(self, mock_run):
        """container_name が rumi-pack-{pack_id} フォーマットであること"""
        orch = ContainerOrchestrator()
        orch.stop_container("test-pack-42")

        first_call = mock_run.call_args_list[0]
        cmd = first_call[0][0]
        container_name = cmd[2]
        assert container_name == "rumi-pack-test-pack-42"

    @patch("core_runtime.container_orchestrator.subprocess.run")
    def test_timeout_values(self, mock_run):
        """docker stop は 30s、docker rm は 10s のタイムアウトであること"""
        orch = ContainerOrchestrator()
        orch.stop_container("abc123")

        calls = mock_run.call_args_list
        assert len(calls) == 2
        # docker stop: timeout=30
        assert calls[0][1]["timeout"] == 30
        # docker rm: timeout=10
        assert calls[1][1]["timeout"] == 10
