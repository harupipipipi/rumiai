from __future__ import annotations

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
    )

    argv = build_bubblewrap_argv(spec)

    assert "--unshare-net" in argv
    assert "--ro-bind" in argv
    assert str(root.resolve()) in argv
    assert str(workspace.resolve()) in argv
    assert "/workspace" in argv
