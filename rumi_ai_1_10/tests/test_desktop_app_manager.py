"""Tests for desktop_app_manager.py — launch_app() argument construction.

Agent L — Wave 2: Verify that launch_app() constructs the correct
Popen arguments after the --command / RUMI_API_TOKEN fix.
"""
from __future__ import annotations

import os
import json
import shlex
import sys
from pathlib import Path
from unittest import mock

import pytest

from core_runtime.desktop_app_manager import DesktopAppManager
import core_runtime.desktop_app_manager as desktop_app_manager


@pytest.fixture
def manager(tmp_path):
    """Create a DesktopAppManager with a temporary repo dir."""
    repo_dir = str(tmp_path / "rumi_ai_1_10")
    os.makedirs(os.path.join(repo_dir, "user_data", "apps"), exist_ok=True)
    return DesktopAppManager(repo_dir=repo_dir)


@pytest.fixture
def sample_meta(tmp_path):
    """Sample app metadata as saved by register_app()."""
    pack_dir = tmp_path / "packs" / "test-pack-001"
    pack_dir.mkdir(parents=True)
    return {
        "pack_id": "test-pack-001",
        "command": "python app.py --verbose",
        "pack_dir": str(pack_dir),
        "pack_shell": "/usr/local/bin/pack-shell",
        "requires_api_token": True,
        "window": {"title": "Test App"},
        "env": {"CUSTOM_VAR": "hello"},
        "working_dir": str(pack_dir),
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
            "--port",
            "8765",
            "--kernel-cmd",
            f"{shlex.quote(desktop_app_manager._runtime_python_for_app())} -m app",
            "--timeout",
            "120",
            "--working-dir",
            sample_meta["working_dir"],
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

    @mock.patch("subprocess.Popen")
    @mock.patch("os.path.isfile", return_value=True)
    def test_launch_app_with_env_overrides_pack_env(
        self, mock_isfile, mock_popen, manager, sample_meta
    ):
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        manager._load_meta = mock.MagicMock(return_value=sample_meta)

        result = manager.launch_app_with_env(
            "test-pack-001",
            api_token="issued-token",
            env_overrides={"CUSTOM_VAR": "override", "RUMI_DEFAULTSPACK_SURFACE": "browser"},
        )

        assert result["success"] is True
        env = mock_popen.call_args.kwargs["env"]
        assert env["CUSTOM_VAR"] == "override"
        assert env["RUMI_DEFAULTSPACK_SURFACE"] == "browser"

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

    def test_resolve_pack_shell_prefers_bundled_runtime_copy(self, tmp_path):
        """Bundled Tauri runtime should resolve app/bundled/pack-shell."""
        repo_dir = tmp_path / "rumi_ai_1_10"
        bundled_shell = repo_dir / "bundled" / desktop_app_manager._pack_shell_binary_name()
        bundled_shell.parent.mkdir(parents=True)
        bundled_shell.write_text("#!/bin/sh\n", encoding="utf-8")
        bundled_shell.chmod(0o755)

        env_clean = {
            k: v
            for k, v in os.environ.items()
            if k not in {"RUMI_PACK_SHELL_PATH", "PATH"}
        }
        with mock.patch.object(desktop_app_manager, "_default_repo_dir", return_value=str(repo_dir)):
            with mock.patch.dict(os.environ, env_clean, clear=True):
                assert desktop_app_manager._resolve_pack_shell_path() == str(bundled_shell)

    @mock.patch("subprocess.Popen")
    def test_launch_app_lazily_registers_repo_local_pack(
        self, mock_popen, tmp_path
    ):
        """Viewer launch can start a repo-local desktop_app before metadata exists."""
        repo_dir = tmp_path / "rumi_ai_1_10"
        pack_dir = repo_dir / "ecosystem" / "autopack"
        pack_dir.mkdir(parents=True)
        (pack_dir / "ecosystem.json").write_text(
            json.dumps(
                {
                    "pack_id": "autopack",
                    "desktop_app": {
                        "command": "python app.py",
                        "env": {"AUTOPACK_PORT": "9999"},
                    },
                }
            ),
            encoding="utf-8",
        )

        pack_shell = tmp_path / "pack-shell"
        pack_shell.write_text("#!/bin/sh\n", encoding="utf-8")
        pack_shell.chmod(0o755)

        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        manager = DesktopAppManager(repo_dir=str(repo_dir))
        with mock.patch.dict(os.environ, {"RUMI_PACK_SHELL_PATH": str(pack_shell)}):
            with mock.patch.object(manager, "_create_shortcut", return_value=str(tmp_path / "Autopack.app")):
                result = manager.launch_app("autopack", api_token="issued-token")

        assert result["success"] is True
        assert result["launch_mode"] == "direct"
        meta_path = repo_dir / "user_data" / "apps" / "autopack.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["pack_dir"] == str(pack_dir)

        cmd_list = mock_popen.call_args[0][0]
        assert cmd_list == [desktop_app_manager._runtime_python_for_app(), "app.py"]
        env = mock_popen.call_args.kwargs["env"]
        assert env["RUMI_API_TOKEN"] == "issued-token"
        assert env["RUMI_TOKEN"] == "issued-token"
        assert env["AUTOPACK_PORT"] == "9999"
        assert str(Path(sys.executable).resolve().parent) in env["PATH"]

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

    def test_default_manager_uses_rumi_user_data_apps_dir(self, tmp_path, monkeypatch):
        user_data = tmp_path / "user-data"
        monkeypatch.setenv("RUMI_USER_DATA", str(user_data))

        manager = DesktopAppManager()

        assert Path(manager._apps_dir) == user_data / "apps"

    @mock.patch("subprocess.Popen")
    def test_launch_refreshes_stale_meta_from_managed_pack(
        self, mock_popen, tmp_path, monkeypatch
    ):
        user_data = tmp_path / "user-data"
        pack_dir = user_data / "packs" / "defaultspack" / "versions" / "2.0.0"
        pack_dir.mkdir(parents=True)
        (pack_dir / "ecosystem.json").write_text(
            json.dumps(
                {
                    "pack_id": "defaultspack",
                    "desktop_app": {
                        "command": "python defaultspack/desktop_app.py",
                        "env": {"RUMI_DEFAULTSPACK_SURFACE": "browser"},
                    },
                }
            ),
            encoding="utf-8",
        )
        current = user_data / "packs" / "defaultspack" / "current.json"
        current.write_text(
            json.dumps(
                {
                    "schema": "rumi.pack_current.v1",
                    "pack_id": "defaultspack",
                    "version": "2.0.0",
                    "path": "versions/2.0.0",
                }
            ),
            encoding="utf-8",
        )
        apps_dir = user_data / "apps"
        apps_dir.mkdir()
        (apps_dir / "defaultspack.json").write_text(
            json.dumps(
                {
                    "pack_id": "defaultspack",
                    "command": "python old.py",
                    "pack_dir": str(tmp_path / "missing-old-bundle"),
                    "pack_shell": str(tmp_path / "missing-pack-shell"),
                    "requires_api_token": True,
                    "env": {"RUMI_DEFAULTSPACK_SURFACE": "browser"},
                    "working_dir": "",
                }
            ),
            encoding="utf-8",
        )
        pack_shell = tmp_path / "pack-shell"
        pack_shell.write_text("#!/bin/sh\n", encoding="utf-8")
        pack_shell.chmod(0o755)
        monkeypatch.setenv("RUMI_USER_DATA", str(user_data))
        monkeypatch.setenv("RUMI_PACK_SHELL_PATH", str(pack_shell))

        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        manager = DesktopAppManager()
        with mock.patch.object(manager, "_create_shortcut", return_value=str(tmp_path / "Rumi.app")):
            result = manager.launch_app("defaultspack", api_token="issued-token")

        assert result["success"] is True
        meta = json.loads((apps_dir / "defaultspack.json").read_text(encoding="utf-8"))
        assert meta["pack_dir"] == str(pack_dir)
        assert mock_popen.call_args.kwargs["cwd"] == str(pack_dir)

    def test_macos_shortcut_exports_rumi_user_data(self, tmp_path, monkeypatch):
        user_data = tmp_path / "user-data"
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        pack_shell = tmp_path / "pack-shell"
        pack_shell.write_text("#!/bin/sh\n", encoding="utf-8")
        pack_shell.chmod(0o755)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("RUMI_USER_DATA", str(user_data))

        manager = DesktopAppManager(repo_dir=str(tmp_path / "repo"))
        shortcut = manager._create_macos_app(
            "defaultspack",
            str(pack_shell),
            str(pack_dir),
            {
                "command": "python defaultspack/desktop_app.py",
                "window": {"title": "Rumi Defaultspack"},
                "env": {"RUMI_DEFAULTSPACK_PORT": "8766"},
            },
        )

        launch_script = Path(shortcut, "Contents", "MacOS", "launch").read_text(encoding="utf-8")
        assert f"export RUMI_USER_DATA={user_data}" in launch_script
        assert 'export PYTHONPATH="$APP_ROOT:${PYTHONPATH:-}"' in launch_script
