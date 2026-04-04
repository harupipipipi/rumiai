"""Tests for desktop_app_manager.py — launch_app() argument construction.

Agent L — Wave 2: Verify that launch_app() constructs the correct
Popen arguments after the --command / RUMI_API_TOKEN fix.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest

from core_runtime.desktop_app_manager import DesktopAppManager


@pytest.fixture
def manager(tmp_path):
    """Create a DesktopAppManager with a temporary repo dir."""
    repo_dir = str(tmp_path / "rumi_ai_1_10")
    os.makedirs(os.path.join(repo_dir, "user_data", "apps"), exist_ok=True)
    return DesktopAppManager(repo_dir=repo_dir)


@pytest.fixture
def sample_meta():
    """Sample app metadata as saved by register_app()."""
    return {
        "pack_id": "test-pack-001",
        "command": "python app.py --verbose",
        "pack_dir": "/tmp/packs/test-pack-001",
        "pack_shell": "/usr/local/bin/pack-shell",
        "requires_api_token": True,
        "window": {"title": "Test App"},
        "env": {"CUSTOM_VAR": "hello"},
        "working_dir": "/tmp/packs/test-pack-001",
        "platforms": [],
    }


class TestLaunchAppArguments:
    """Verify that launch_app() constructs the correct Popen arguments."""

    @mock.patch("subprocess.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_launch_app_passes_run_subcommand_and_command_flag(
        self, mock_isfile, mock_popen, manager, sample_meta
    ):
        """Popen should be called with:
        [pack_shell, 'run', pack_id, '--command', command]
        """
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        manager._load_meta = mock.MagicMock(return_value=sample_meta)

        with mock.patch.dict(os.environ, {"RUMI_API_TOKEN": "secret-token-xyz"}):
            result = manager.launch_app("test-pack-001")

        assert result["success"] is True
        assert result["status"] == "launched"

        call_args = mock_popen.call_args
        cmd_list = call_args[0][0]  # first positional arg to Popen
        assert cmd_list == [
            "/usr/local/bin/pack-shell",
            "run",
            "test-pack-001",
            "--command",
            "python app.py --verbose",
            "--working-dir",
            "/tmp/packs/test-pack-001",
        ]

    @mock.patch("subprocess.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_launch_app_passes_rumi_api_token_in_env(
        self, mock_isfile, mock_popen, manager, sample_meta
    ):
        """RUMI_API_TOKEN should appear in the env dict passed to Popen."""
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        manager._load_meta = mock.MagicMock(return_value=sample_meta)

        with mock.patch.dict(os.environ, {"RUMI_API_TOKEN": "secret-token-xyz"}):
            result = manager.launch_app("test-pack-001")

        assert result["success"] is True
        call_kwargs = mock_popen.call_args[1]
        env = call_kwargs.get("env")
        assert env is not None
        assert env.get("RUMI_API_TOKEN") == "secret-token-xyz"

    @mock.patch("os.path.isfile", return_value=True)
    def test_launch_app_errors_when_command_is_empty(
        self, mock_isfile, manager, sample_meta
    ):
        """launch_app() should return an error if command is empty."""
        meta_no_cmd = dict(sample_meta)
        meta_no_cmd["command"] = ""

        manager._load_meta = mock.MagicMock(return_value=meta_no_cmd)

        result = manager.launch_app("test-pack-001")

        assert result["success"] is False
        assert "No command" in result["error"]

    @mock.patch("os.path.isfile", return_value=True)
    def test_launch_app_errors_when_command_is_none(
        self, mock_isfile, manager, sample_meta
    ):
        """launch_app() should return an error if command key is missing."""
        meta_no_cmd = dict(sample_meta)
        del meta_no_cmd["command"]

        manager._load_meta = mock.MagicMock(return_value=meta_no_cmd)

        result = manager.launch_app("test-pack-001")

        assert result["success"] is False
        assert "No command" in result["error"]

    def test_launch_app_errors_when_not_registered(self, manager):
        """launch_app() should return an error for unregistered pack_id."""
        result = manager.launch_app("nonexistent-pack")

        assert result["success"] is False
        assert "not registered" in result["error"].lower()

    @mock.patch("subprocess.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_launch_app_includes_custom_env_vars(
        self, mock_isfile, mock_popen, manager, sample_meta
    ):
        """Custom env vars from meta should be present in Popen env."""
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        manager._load_meta = mock.MagicMock(return_value=sample_meta)

        with mock.patch.dict(os.environ, {"RUMI_API_TOKEN": "secret-token-xyz"}):
            result = manager.launch_app("test-pack-001")

        assert result["success"] is True
        call_kwargs = mock_popen.call_args[1]
        env = call_kwargs.get("env")
        assert env.get("CUSTOM_VAR") == "hello"
        assert env.get("RUMI_PACK_ID") == "test-pack-001"

    @mock.patch("subprocess.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_launch_app_errors_without_rumi_api_token_env(
        self, mock_isfile, mock_popen, manager, sample_meta
    ):
        """Desktop app launch should fail fast when RUMI_API_TOKEN is missing."""
        manager._load_meta = mock.MagicMock(return_value=sample_meta)

        env_clean = {k: v for k, v in os.environ.items() if k != "RUMI_API_TOKEN"}
        with mock.patch.dict(os.environ, env_clean, clear=True):
            result = manager.launch_app("test-pack-001")

        assert result["success"] is False
        assert "RUMI_API_TOKEN" in result["error"]
        mock_popen.assert_not_called()
