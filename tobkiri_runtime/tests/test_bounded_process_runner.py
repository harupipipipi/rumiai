from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from core_runtime.bounded_process_runner import (
    HostBoundedProcessRunner,
    ProcessExecutionPolicy,
)


def _policy(
    argv: tuple[str, ...],
    cwd: Path,
    **overrides: object,
) -> ProcessExecutionPolicy:
    values = {
        "allowed_executables": frozenset({argv[0]}),
        "allowed_argv": (argv,),
        "allowed_cwds": (cwd,),
        "allowed_environment": frozenset(),
        "max_timeout_seconds": 2.0,
    }
    values.update(overrides)
    return ProcessExecutionPolicy(**values)


def test_runner_caps_redacts_and_preserves_exit_code(tmp_path: Path) -> None:
    argv = (
        sys.executable,
        "-c",
        (
            "import sys; "
            "print('token=top-secret-' + 'x' * 200); "
            "print('password=hunter2', file=sys.stderr); "
            "raise SystemExit(7)"
        ),
    )

    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=1,
        environment={},
        policy=_policy(
            argv,
            tmp_path,
            max_stdout_bytes=64,
            max_stderr_bytes=64,
            redact_values=("top-secret", "hunter2"),
        ),
    )

    assert result.exit_code == 7
    assert result.stdout_truncated is True
    assert "top-secret" not in result.stdout
    assert "hunter2" not in result.stderr
    assert "[REDACTED]" in result.stdout
    assert "[REDACTED]" in result.stderr
    assert result.attestation.authority == "core_runtime.bounded_process_runner"
    assert result.attestation.sandboxed is False


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("executable", "executable"),
        ("arguments", "arguments"),
        ("cwd", "cwd"),
        ("environment", "environment"),
    ],
)
def test_runner_allowlists_fail_closed(
    tmp_path: Path,
    change: str,
    expected: str,
) -> None:
    argv = (sys.executable, "-c", "print('ok')")
    policy = _policy(argv, tmp_path)
    actual_argv = argv
    actual_cwd = tmp_path
    environment = {}
    if change == "executable":
        actual_argv = ("/not/allowlisted", *argv[1:])
    elif change == "arguments":
        actual_argv = (*argv, "extra")
    elif change == "cwd":
        actual_cwd = tmp_path.parent
    else:
        environment = {"SECRET": "must-not-pass"}

    with pytest.raises((PermissionError, ValueError), match=expected):
        HostBoundedProcessRunner().run_local(
            argv=actual_argv,
            cwd=actual_cwd,
            stdin=None,
            timeout_seconds=1,
            environment=environment,
            policy=policy,
        )


def test_runner_timeout_kills_descendant_process_tree(tmp_path: Path) -> None:
    sentinel = tmp_path / "descendant-survived"
    child = (
        "import pathlib,time; "
        "time.sleep(0.7); "
        f"pathlib.Path({str(sentinel)!r}).write_text('alive')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "time.sleep(10)"
    )
    argv = (sys.executable, "-c", parent)

    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=0.15,
        environment={},
        policy=_policy(argv, tmp_path),
    )
    time.sleep(0.8)

    assert result.timed_out is True
    assert result.exit_code is not None
    assert not sentinel.exists()


def test_attested_backend_output_schema_requires_exit_code(tmp_path: Path) -> None:
    argv = ("python3", "-c", "print('ok')")

    with pytest.raises(ValueError, match="missing required fields"):
        HostBoundedProcessRunner().run_attested_backend(
            argv=argv,
            cwd=tmp_path,
            stdin=None,
            timeout_seconds=1,
            environment={},
            policy=_policy(argv, tmp_path, allow_path_search=True),
            backend=lambda: {"stdout": "ok", "stderr": ""},
            boundary="managed_sandbox",
            sandboxed=True,
            process_tree_kill="pid_namespace",
        )
