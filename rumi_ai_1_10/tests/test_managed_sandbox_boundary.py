from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _executor():
    from core_runtime.capability_executor import CapabilityExecutor

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._trust_store = MagicMock()
    executor._grant_manager = MagicMock()
    return executor


def _entry(tmp_path):
    function_dir = tmp_path / "third_party"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    return SimpleNamespace(
        pack_id="third_party_pack",
        function_id="run",
        qualified_name="third_party_pack:run",
        function_dir=str(function_dir),
        main_py_path=str(main_py),
        entrypoint="main.py:run",
        runtime="python",
        calling_convention="python_docker",
        host_execution=False,
        manifest={},
    )


def test_non_core_user_function_fails_closed_when_managed_sandbox_unavailable(tmp_path, monkeypatch):
    from core_runtime.execution_boundary import SANDBOX_RUNTIME_UNAVAILABLE

    monkeypatch.setenv("RUMI_ALLOW_HOST_FALLBACK", "true")
    executor = _executor()
    entry = _entry(tmp_path)

    with patch.object(executor, "_execute_user_function_host") as host_exec:
        response = executor._execute_user_function(
            principal_id="third_party_pack",
            entry=entry,
            args={},
            request_id="req-sandbox",
            start_time=time.time(),
            force_docker=True,
        )

    assert response.success is False
    assert response.error_type == SANDBOX_RUNTIME_UNAVAILABLE
    assert response.output["execution_boundary"] == "managed_sandbox"
    host_exec.assert_not_called()


def test_development_host_flag_is_ignored_for_profile_principal(tmp_path, monkeypatch):
    from core_runtime.execution_boundary import SANDBOX_RUNTIME_UNAVAILABLE

    monkeypatch.setenv("RUMI_ENVIRONMENT", "development")
    monkeypatch.setenv("RUMI_ALLOW_DEVELOPMENT_HOST_EXECUTION", "true")
    executor = _executor()
    entry = _entry(tmp_path)

    response = executor._execute_user_function(
        principal_id="profile:work__surface:mobile",
        entry=entry,
        args={},
        request_id="req-profile",
        start_time=time.time(),
        force_docker=True,
    )

    assert response.success is False
    assert response.error_type == SANDBOX_RUNTIME_UNAVAILABLE


def test_untrusted_manifest_and_context_cannot_bypass_managed_sandbox(tmp_path):
    executor = _executor()
    entry = _entry(tmp_path)
    entry.is_builtin = True

    assert executor._entry_requires_managed_sandbox(
        entry,
        "third_party_pack",
        {"execution_boundary": "host_broker", "boundary": "host_broker"},
    ) is True


def test_untrusted_legacy_handler_builtin_flag_cannot_bypass_managed_sandbox(tmp_path):
    executor = _executor()
    handler_dir = tmp_path / "legacy"
    handler_dir.mkdir()
    handler_py = handler_dir / "main.py"
    handler_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    handler_def = SimpleNamespace(
        pack_id="third_party_pack",
        handler_id="third_party_pack:run",
        handler_dir=str(handler_dir),
        handler_py_path=str(handler_py),
        is_builtin=True,
    )

    assert executor._handler_def_requires_managed_sandbox(handler_def, "third_party_pack") is True


def test_bubblewrap_builder_uses_policy_not_raw_command(tmp_path):
    from ecosystem.defaultspack.backend.sandbox.isolation import (
        BubblewrapSandboxSpec,
        WorkspaceMount,
        build_bubblewrap_argv,
    )

    root = tmp_path / "root"
    workspace = tmp_path / "workspace"
    root.mkdir()
    workspace.mkdir()
    spec = BubblewrapSandboxSpec(
        sandbox_id="sbx_test",
        profile_id="work",
        immutable_root=root,
        workspace=WorkspaceMount(source=workspace),
        argv=("python3", "/workspace/main.py"),
        env={"RUMI_SANDBOX_ID": "sbx_test"},
        network_enabled=False,
        seccomp_fd=7,
    )

    argv = build_bubblewrap_argv(spec)

    assert "--clearenv" in argv
    assert "--unshare-net" in argv
    assert "--ro-bind" in argv
    assert str(root.resolve()) in argv
    assert str(workspace.resolve()) in argv
    assert "/workspace" in argv
    assert argv[argv.index("--seccomp") + 1] == "7"
    assert argv[argv.index("--setenv") + 1] == "HOME"


def test_managed_sandbox_supervisor_runs_payload_under_bwrap_and_cgroup(tmp_path, monkeypatch):
    from ecosystem.defaultspack.backend.sandbox.isolation import ManagedSandboxSupervisor

    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'echo': args.get('value')}\n", encoding="utf-8")
    runner_path = ROOT / "core_runtime" / "function_runner.py"
    captured: dict[str, object] = {}

    def fake_which(name):
        return f"/usr/bin/{name}" if name in {"bwrap", "systemd-run"} else None

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = dict(kwargs)
        workspace = Path(command[command.index("/workspace") - 1])
        captured["workspace"] = workspace
        assert (workspace / "function" / "main.py").is_file()
        assert (workspace / "function_runner.py").is_file()
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"echo":"hello"}',
            stderr="",
        )

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = ManagedSandboxSupervisor().execute_capability(
        {
            "profile_runtime": "rumi-profile-test",
            "principal_id": "profile:work",
            "pack_id": "third_party_pack",
            "function_id": "run",
            "qualified_name": "third_party_pack:run",
            "calling_convention": "subprocess",
            "function_dir": str(function_dir),
            "main_py_path": str(main_py),
            "entrypoint": "main.py:run",
            "runner_path": str(runner_path),
            "timeout_seconds": 10,
            "args": {"value": "hello"},
            "context": {"request_id": "req-1"},
        }
    )

    command = captured["command"]
    assert result == {
        "success": True,
        "ok": True,
        "output": {"echo": "hello"},
        "execution_boundary": "managed_sandbox",
    }
    assert command[0] == "systemd-run"
    assert any(str(item).startswith("--property=MemoryMax=") for item in command)
    assert "bwrap" in command
    assert "--clearenv" in command
    assert "--unshare-net" in command
    assert captured["kwargs"]["timeout"] == 12
    assert not Path(captured["workspace"]).exists()
