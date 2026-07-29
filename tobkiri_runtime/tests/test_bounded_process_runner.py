from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from core_runtime.bounded_process_runner import (
    BoundedProcessResult,
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


def test_runner_accepts_bounded_binary_stdin(tmp_path: Path) -> None:
    argv = (
        sys.executable,
        "-c",
        "import sys; data=sys.stdin.buffer.read(); print(data.hex())",
    )
    payload = b"\x00\xffbinary\n"

    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=payload,
        timeout_seconds=1,
        environment={},
        policy=_policy(argv, tmp_path, max_stdin_bytes=len(payload)),
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == payload.hex()


def test_runner_allows_exactly_allowlisted_empty_argument(tmp_path: Path) -> None:
    argv = (
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1] == '')",
        "",
    )

    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=1,
        environment={},
        policy=_policy(argv, tmp_path),
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "True"


def test_runner_preserves_json_boolean_for_secret_named_field(
    tmp_path: Path,
) -> None:
    argv = (
        sys.executable,
        "-c",
        "print('{\"sibling_pack_secret\": false}')",
    )

    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=1,
        environment={},
        policy=_policy(argv, tmp_path),
    )

    assert json.loads(result.stdout) == {"sibling_pack_secret": False}


def test_runner_streams_stdout_to_bounded_new_file(tmp_path: Path) -> None:
    argv = (sys.executable, "-c", "print('x' * 4096, end='')")
    output = tmp_path / "stream.bin"

    result = HostBoundedProcessRunner().run_local_to_file(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=1,
        environment={},
        policy=_policy(argv, tmp_path, max_stdout_bytes=128),
        stdout_path=output,
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stdout_truncated is True
    assert output.read_bytes() == b"x" * 128


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
        "import pathlib,signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(0.7); "
        f"pathlib.Path({str(sentinel)!r}).write_text('alive')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "time.sleep(10)"
    )
    argv = (sys.executable, "-c", parent)

    started = time.monotonic()
    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=0.15,
        environment={},
        policy=_policy(argv, tmp_path),
    )
    elapsed = time.monotonic() - started
    time.sleep(0.8)

    assert result.timed_out is True
    assert result.exit_code is not None
    assert elapsed < 1.5
    assert not sentinel.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX pipe inheritance test")
def test_runner_does_not_wait_unbounded_for_descendant_pipe_holders(
    tmp_path: Path,
) -> None:
    child = "import time; time.sleep(2)"
    parent = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}])"
    )
    argv = (sys.executable, "-c", parent)

    started = time.monotonic()
    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=1,
        environment={},
        policy=_policy(argv, tmp_path),
    )
    elapsed = time.monotonic() - started

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True
    assert elapsed < 1.5


def test_runner_redacts_secret_crossing_output_cap(tmp_path: Path) -> None:
    secret = "cross-boundary-secret"
    argv = (sys.executable, "-c", f"print('12345678901234{secret}')")

    result = HostBoundedProcessRunner().run_local(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=1,
        environment={},
        policy=_policy(
            argv,
            tmp_path,
            max_stdout_bytes=20,
            redact_values=(secret,),
        ),
    )

    assert result.stdout_truncated is True
    assert "cross-" not in result.stdout
    assert "[REDA" in result.stdout


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


def _run_backend(
    tmp_path: Path,
    payload: dict[str, object],
    **policy_overrides: object,
) -> BoundedProcessResult:
    argv = ("python3", "-c", "print('ok')")
    return HostBoundedProcessRunner().run_attested_backend(
        argv=argv,
        cwd=tmp_path,
        stdin=None,
        timeout_seconds=1,
        environment={},
        policy=_policy(
            argv,
            tmp_path,
            allow_path_search=True,
            **policy_overrides,
        ),
        backend=lambda: payload,
        boundary="managed_sandbox",
        sandboxed=True,
        process_tree_kill="pid_namespace",
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
            },
            "null exit_code",
        ),
        (
            {
                "exit_code": 0,
                "returncode": 3,
                "stdout": "",
                "stderr": "",
            },
            "returncode conflicts",
        ),
        (
            {
                "exit_code": 2,
                "stdout": "",
                "stderr": "",
                "success": True,
            },
            "success conflicts",
        ),
        (
            {
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "unexpected": "raw material",
            },
            "unknown fields",
        ),
        (
            {
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": "yes",
            },
            "stdout_truncated must be boolean",
        ),
    ],
)
def test_attested_backend_output_schema_rejects_inconsistent_results(
    tmp_path: Path,
    payload: dict[str, object],
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        _run_backend(tmp_path, payload)


def test_attested_backend_propagates_truncation_and_redacts_transport_error(
    tmp_path: Path,
) -> None:
    secret = "backend-secret-value"
    result = _run_backend(
        tmp_path,
        {
            "exit_code": None,
            "returncode": None,
            "stdout": "already clipped",
            "stderr": f"token={secret}",
            "timed_out": True,
            "stdout_truncated": True,
            "stderr_truncated": True,
            "error_type": f"provider-{secret}",
            "success": False,
            "ok": False,
        },
        max_stderr_bytes=32,
        redact_values=(secret,),
    )

    assert result.exit_code is None
    assert result.timed_out is True
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True
    assert secret not in result.stderr
    assert secret not in str(result.transport_error)
    assert result.transport_error == "provider-[REDACTED]"
