from __future__ import annotations

import os
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


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
    assert "--disable-userns" in argv
    assert "--unshare-net" in argv
    assert "--ro-bind" in argv
    assert str(root.resolve()) in argv
    assert str(workspace.resolve()) in argv
    assert "/workspace" in argv
    assert argv[argv.index("--seccomp") + 1] == "7"
    assert argv[argv.index("--setenv") + 1] == "HOME"


def test_sandbox_stage_rejects_symlink_escape(tmp_path):
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import ManagedSandboxSupervisor

    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    os.symlink("/etc/passwd", function_dir / "host-passwd")

    with pytest.raises(ValueError, match="symlinks"):
        ManagedSandboxSupervisor()._stage_function(
            request={
                "function_dir": str(function_dir),
                "main_py_path": str(main_py),
                "entrypoint": "main.py:run",
            },
            function_target=tmp_path / "stage",
        )


def test_sandbox_stage_rejects_relative_symlink_escape(tmp_path):
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import ManagedSandboxSupervisor

    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    os.symlink("../secret.txt", function_dir / "secret-link")

    with pytest.raises(ValueError, match="symlinks"):
        ManagedSandboxSupervisor()._stage_function(
            request={
                "function_dir": str(function_dir),
                "main_py_path": str(main_py),
                "entrypoint": "main.py:run",
            },
            function_target=tmp_path / "stage",
        )


def test_sandbox_stage_rejects_large_or_special_files(tmp_path, monkeypatch):
    from ecosystem.defaultspack.backend.sandbox.isolation import supervisor as supervisor_module
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import ManagedSandboxSupervisor

    monkeypatch.setattr(supervisor_module, "MAX_STAGE_FILE_BYTES", 64)
    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    (function_dir / "big.txt").write_text("x" * 65, encoding="utf-8")

    with pytest.raises(ValueError, match="too large"):
        ManagedSandboxSupervisor()._stage_function(
            request={
                "function_dir": str(function_dir),
                "main_py_path": str(main_py),
                "entrypoint": "main.py:run",
            },
            function_target=tmp_path / "stage-big",
        )

    if hasattr(os, "mkfifo"):
        (function_dir / "big.txt").unlink()
        os.mkfifo(function_dir / "pipe")
        with pytest.raises(ValueError, match="special files"):
            ManagedSandboxSupervisor()._stage_function(
                request={
                    "function_dir": str(function_dir),
                    "main_py_path": str(main_py),
                    "entrypoint": "main.py:run",
                },
                function_target=tmp_path / "stage-special",
            )


def test_sandbox_stage_rejects_hardlinks_and_ignored_name_symlinks(tmp_path):
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import ManagedSandboxSupervisor

    if not hasattr(os, "link"):
        pytest.skip("hardlinks are not supported on this platform")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    os.link(outside, function_dir / "hardlinked.txt")

    with pytest.raises(ValueError, match="hardlinked"):
        ManagedSandboxSupervisor()._stage_function(
            request={
                "function_dir": str(function_dir),
                "main_py_path": str(main_py),
                "entrypoint": "main.py:run",
            },
            function_target=tmp_path / "stage-hardlink",
        )

    (function_dir / "hardlinked.txt").unlink()
    os.symlink("/etc/passwd", function_dir / "ignored.pyc")
    with pytest.raises(ValueError, match="symlinks"):
        ManagedSandboxSupervisor()._stage_function(
            request={
                "function_dir": str(function_dir),
                "main_py_path": str(main_py),
                "entrypoint": "main.py:run",
            },
            function_target=tmp_path / "stage-pyc-link",
        )

    (function_dir / "ignored.pyc").unlink()
    os.symlink("/etc", function_dir / "__pycache__")
    with pytest.raises(ValueError, match="symlinks"):
        ManagedSandboxSupervisor()._stage_function(
            request={
                "function_dir": str(function_dir),
                "main_py_path": str(main_py),
                "entrypoint": "main.py:run",
            },
            function_target=tmp_path / "stage-cache-link",
        )


def test_sandbox_stage_rejects_socket_and_tree_limits(tmp_path, monkeypatch):
    from ecosystem.defaultspack.backend.sandbox.isolation import supervisor as supervisor_module
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import ManagedSandboxSupervisor

    with tempfile.TemporaryDirectory(prefix="rs-", dir="/tmp") as short_root_raw:
        function_dir = Path(short_root_raw) / "function"
        function_dir.mkdir()
        main_py = function_dir / "main.py"
        main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(function_dir / "sock"))
            with pytest.raises(ValueError, match="special files"):
                ManagedSandboxSupervisor()._stage_function(
                    request={
                        "function_dir": str(function_dir),
                        "main_py_path": str(main_py),
                        "entrypoint": "main.py:run",
                    },
                    function_target=tmp_path / "stage-socket",
                )
        finally:
            sock.close()
            try:
                (function_dir / "sock").unlink()
            except OSError:
                pass

        monkeypatch.setattr(supervisor_module, "MAX_STAGE_FILES", 1)
        (function_dir / "extra.txt").write_text("extra", encoding="utf-8")
        with pytest.raises(ValueError, match="too many files"):
            ManagedSandboxSupervisor()._stage_function(
                request={
                    "function_dir": str(function_dir),
                    "main_py_path": str(main_py),
                    "entrypoint": "main.py:run",
                },
                function_target=tmp_path / "stage-count",
            )

        monkeypatch.setattr(supervisor_module, "MAX_STAGE_FILES", 10)
        monkeypatch.setattr(supervisor_module, "MAX_STAGE_FILE_BYTES", 1024)
        monkeypatch.setattr(supervisor_module, "MAX_STAGE_TOTAL_BYTES", 48)
        with pytest.raises(ValueError, match="tree is too large"):
            ManagedSandboxSupervisor()._stage_function(
                request={
                    "function_dir": str(function_dir),
                    "main_py_path": str(main_py),
                    "entrypoint": "main.py:run",
                },
                function_target=tmp_path / "stage-total",
            )


def test_sandbox_stage_regular_files_only(tmp_path):
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import ManagedSandboxSupervisor

    function_dir = tmp_path / "function"
    nested = function_dir / "nested"
    cache = function_dir / "__pycache__"
    nested.mkdir(parents=True)
    cache.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")
    (nested / "data.txt").write_text("data", encoding="utf-8")
    (cache / "main.pyc").write_bytes(b"pyc")
    target = tmp_path / "stage"

    module_rel, callable_name, audit = ManagedSandboxSupervisor()._stage_function(
        request={
            "function_dir": str(function_dir),
            "main_py_path": str(main_py),
            "entrypoint": "main.py:run",
        },
        function_target=target,
    )

    assert module_rel == Path("main.py")
    assert callable_name == "run"
    assert audit["files"] == 2
    assert (target / "main.py").is_file()
    assert (target / "nested" / "data.txt").is_file()
    assert not (target / "__pycache__").exists()


def test_sandbox_rejects_host_root_as_default_immutable_root(tmp_path, monkeypatch):
    from ecosystem.defaultspack.backend.sandbox.isolation import supervisor as supervisor_module

    monkeypatch.delenv("RUMI_SANDBOX_IMMUTABLE_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        supervisor_module._immutable_root({})
    with pytest.raises(RuntimeError, match="host root"):
        supervisor_module._immutable_root({"immutable_root": "/"})

    unmarked = tmp_path / "root"
    unmarked.mkdir()
    with pytest.raises(RuntimeError, match="marker"):
        supervisor_module._immutable_root({"immutable_root": str(unmarked)})

    marked_writable = tmp_path / "writable-root"
    marked_writable.mkdir()
    (marked_writable / ".rumi-sandbox-root").write_text("ok\n", encoding="utf-8")
    marked_writable.chmod(0o777)
    try:
        with pytest.raises(RuntimeError, match="root is writable"):
            supervisor_module._immutable_root({"immutable_root": str(marked_writable)})
    finally:
        marked_writable.chmod(0o700)


def test_sandbox_wrapper_opens_seccomp_fd_inside_cgroup_command(tmp_path):
    from ecosystem.defaultspack.backend.sandbox.isolation import supervisor as supervisor_module

    fake_bwrap = tmp_path / "fake_bwrap.py"
    fake_bwrap.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import os",
                "import sys",
                "argv = sys.argv[1:]",
                "index = argv.index('--seccomp')",
                "os.fstat(int(argv[index + 1]))",
                "print(json.dumps({'argv': argv}))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    seccomp_profile = tmp_path / "profile.bpf"
    seccomp_profile.write_bytes(b"fake-bpf")

    command, stdout_path, stderr_path, returncode_path = supervisor_module._sandbox_wrapper_command(
        temp_root=tmp_path,
        bwrap_argv=[sys.executable, str(fake_bwrap), "--clearenv", "--", "python3"],
        seccomp_profile=seccomp_profile,
    )
    proc = subprocess.run(command, capture_output=True, text=True, timeout=5)

    assert proc.returncode == 0
    assert returncode_path.read_text(encoding="utf-8") == "0"
    assert stderr_path.read_text(encoding="utf-8") == ""
    payload = json.loads(stdout_path.read_text(encoding="utf-8"))
    assert payload["argv"].index("--seccomp") < payload["argv"].index("--")


def test_managed_sandbox_supervisor_runs_payload_under_bwrap_and_cgroup(tmp_path, monkeypatch):
    from ecosystem.defaultspack.backend.sandbox.isolation import ManagedSandboxSupervisor

    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'echo': args.get('value')}\n", encoding="utf-8")
    runner_path = ROOT / "core_runtime" / "function_runner.py"
    sandbox_root = tmp_path / "rootfs"
    sandbox_root.mkdir()
    (sandbox_root / ".rumi-sandbox-root").write_text("ok\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_which(name):
        return f"/usr/bin/{name}" if name in {"bwrap", "systemd-run"} else None

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = dict(kwargs)
        wrapper_payload = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        bwrap_argv = list(wrapper_payload["argv"])
        captured["bwrap_argv"] = bwrap_argv
        workspace = Path(bwrap_argv[bwrap_argv.index("/workspace") - 1])
        captured["workspace"] = workspace
        assert (workspace / "function" / "main.py").is_file()
        assert (workspace / "function_runner.py").is_file()
        Path(wrapper_payload["stdout_path"]).write_text('{"echo":"hello"}', encoding="utf-8")
        Path(wrapper_payload["stderr_path"]).write_text("", encoding="utf-8")
        Path(wrapper_payload["returncode_path"]).write_text("0", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="",
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
            "immutable_root": str(sandbox_root),
            "timeout_seconds": 10,
            "args": {"value": "hello"},
            "context": {"request_id": "req-1"},
        }
    )

    command = captured["command"]
    assert result["success"] is True
    assert result["ok"] is True
    assert result["output"] == {"echo": "hello"}
    assert result["execution_boundary"] == "managed_sandbox"
    assert result["sandbox_stage"]["files"] == 1
    assert command[0] == "systemd-run"
    assert any(str(item).startswith("--property=MemoryMax=") for item in command)
    assert captured["bwrap_argv"][0] == "bwrap"
    assert "--clearenv" in captured["bwrap_argv"]
    assert "--unshare-net" in captured["bwrap_argv"]
    assert captured["kwargs"]["timeout"] == 12
    assert not Path(captured["workspace"]).exists()


def test_actual_bwrap_systemd_run_exec_when_available(tmp_path, monkeypatch):
    from ecosystem.defaultspack.backend.sandbox.isolation import ManagedSandboxSupervisor

    if shutil.which("bwrap") is None or shutil.which("systemd-run") is None:
        pytest.skip("Bubblewrap/systemd-run are not installed")
    sandbox_root_env = os.environ.get("RUMI_SANDBOX_IMMUTABLE_ROOT", "")
    if not sandbox_root_env:
        pytest.skip("RUMI_SANDBOX_IMMUTABLE_ROOT is not configured")
    sandbox_root = Path(sandbox_root_env)
    if not (sandbox_root / ".rumi-sandbox-root").is_file():
        pytest.skip("configured sandbox root marker is missing")

    function_dir = tmp_path / "function"
    function_dir.mkdir()
    main_py = function_dir / "main.py"
    main_py.write_text("def run(context, args): return {'ok': True}\n", encoding="utf-8")

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
            "runner_path": str(ROOT / "core_runtime" / "function_runner.py"),
            "timeout_seconds": 5,
            "args": {},
            "context": {},
        }
    )

    assert result["success"] is True
    assert result["output"] == {"ok": True}
