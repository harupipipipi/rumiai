from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "package_macos_dmg.sh"
FINAL_NAME = "Tobkiri Launcher_1.2.3_x64.dmg"


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def _create_fake_tools(root: Path, mode: str) -> tuple[Path, Path]:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    state_path = root / "hdiutil-state.json"
    state_path.write_text(
        json.dumps(
            {
                "mode": mode,
                "create_count": 0,
                "info_count": 0,
                "attached": {},
                "detach": [],
                "commands": [],
                "events": [],
                "requested_size": None,
            }
        ),
        encoding="utf-8",
    )

    _write_executable(
        bin_dir / "codesign",
        """#!/bin/sh
if [ "${1:-}" = "--display" ]; then
  printf '%s\\n' 'Authority=Developer ID Application: Test'
fi
exit 0
""",
    )
    _write_executable(
        bin_dir / "ditto",
        """#!/bin/sh
set -eu
cp -R "$1" "$2"
""",
    )
    _write_executable(
        bin_dir / "plutil",
        """#!/bin/sh
printf '%s\\n' '1.2.3'
""",
    )
    _write_executable(
        bin_dir / "hdiutil",
        r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


state_path = Path(os.environ["FAKE_HDIUTIL_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8"))
command = sys.argv[1]


def save() -> None:
    state_path.write_text(json.dumps(state), encoding="utf-8")


def fail(message: str, code: int) -> None:
    save()
    print(message, file=sys.stderr)
    raise SystemExit(code)


if command == "create":
    output = Path(sys.argv[-1])
    state["create_count"] += 1
    state["commands"].append(sys.argv[1:])
    state["events"].append("create")
    try:
        size_arg = sys.argv[sys.argv.index("-size") + 1]
    except (ValueError, IndexError):
        fail("hdiutil: create missing -size", 8)
    state["requested_size"] = size_arg
    mode = state["mode"]
    if mode == "primary_error":
        workspace = output.parents[1]
        (workspace / "staging" / "external-victim").symlink_to(
            Path(os.environ["FAKE_EXTERNAL_VICTIM"]), target_is_directory=True
        )
        fail("hdiutil: create failed - permission denied", 7)
    if mode == "permanent":
        fail("hdiutil: create failed - permission denied", 7)
    if mode == "symlink":
        output.symlink_to(Path(os.environ["FAKE_EXTERNAL_VICTIM"]) / "keep.txt")
    elif mode == "directory":
        output.mkdir()
    elif mode == "fifo":
        os.mkfifo(output)
    else:
        output.write_bytes(("DMG-%d" % state["create_count"]).encode("ascii"))
        if mode == "under_floor":
            with output.open("r+b") as stream:
                stream.truncate(10240000000 - 1024)
        else:
            with output.open("r+b") as stream:
                stream.truncate(10240000000)
    state["attached"][str(output)] = "/dev/disk42"
    if mode == "resource_busy":
        fail("hdiutil: create failed - Resource busy", 1)
    if mode == "success_cleanup_failure":
        workspace = output.parents[1]
        (workspace / "staging" / "external-victim").symlink_to(
            Path(os.environ["FAKE_EXTERNAL_VICTIM"]), target_is_directory=True
        )
    save()
    print("created: %s" % output)
    raise SystemExit(0)

if command == "info":
    state["events"].append("info")
    state["info_count"] += 1
    print("framework : test")
    print("image-path      : /foreign/foreign.dmg")
    print("/dev/disk99 GUID_partition_scheme")
    print("================================================")
    for image_path, device in state["attached"].items():
        current_device = device
        if state["mode"] == "rebound_device" and state["info_count"] > 1:
            current_device = "/dev/disk99"
        if state["mode"] == "mount_rebinding" and state["info_count"] > 1:
            current_device = "/dev/disk43"
        print("image-path      : %s" % image_path)
        print("%s GUID_partition_scheme" % current_device)
        print("%ss1 APFS" % current_device)
        print("================================================")
    save()
    raise SystemExit(0)

if command == "detach":
    state["events"].append("detach")
    state["detach"].append(sys.argv[2])
    state["attached"] = {}
    save()
    raise SystemExit(0)

if command == "verify":
    state["events"].append("verify")
    verification_path = Path(sys.argv[-1])
    if not verification_path.is_file():
        fail("missing image", 2)
    attached_paths = list(state["attached"])
    if len(attached_paths) != 1:
        fail("missing named image", 2)
    image_path = Path(attached_paths[0])
    if state["mode"] == "replaced_path":
        replacement = Path(os.environ["FAKE_EXTERNAL_VICTIM"]) / "replacement.bin"
        replacement.write_bytes(b"replacement-bytes")
        image_path.unlink()
        image_path.symlink_to(replacement)
    save()
    raise SystemExit(0)

fail("unexpected hdiutil command: %s" % command, 2)
''',
    )
    return bin_dir, state_path


def _fixture_app(root: Path) -> Path:
    app = root / "Tobkiri Launcher.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources" / "app" / "python-runtime").mkdir(parents=True)
    (contents / "Info.plist").write_text("fixture", encoding="utf-8")
    (contents / "MacOS" / "launcher").write_text("fixture", encoding="utf-8")
    return app


def _formal_binding() -> tuple[str, str]:
    interpreter = Path(os.path.realpath(sys.executable))
    return str(interpreter), hashlib.sha256(interpreter.read_bytes()).hexdigest()


def _prepare(root: Path, mode: str) -> tuple[Path, Path, Path, dict[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    app = _fixture_app(root)
    output_dir = root / "output"
    output_dir.mkdir()
    formal_python_snapshot = root / "formal-python-snapshot"
    formal_python_snapshot.mkdir()
    bin_dir, state_path = _create_fake_tools(root, mode)
    victim = root / "external-victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    interpreter, digest = _formal_binding()
    environment = os.environ.copy()
    if mode == "fifo_substitution":
        fifo_wrapper = root / "formal-python-fifo-substitution"
        _write_executable(
            fifo_wrapper,
            """#!/usr/bin/env python3
import os
import subprocess
import sys


source = sys.stdin.read()
needle = "    named_metadata = os.lstat(sys.argv[1])\\n"
if os.environ.get("FAKE_FIFO_SUBSTITUTION") == "1":
    source = source.replace(
        needle,
        needle + "    os.unlink(sys.argv[1])\\n    os.mkfifo(sys.argv[1])\\n",
        1,
    )
result = subprocess.run(
    [os.environ["FORMAL_PYTHON_DELEGATE"], *sys.argv[1:]],
    input=source,
    text=True,
    check=False,
)
raise SystemExit(result.returncode)
""",
        )
        interpreter = str(fifo_wrapper)
        digest = hashlib.sha256(fifo_wrapper.read_bytes()).hexdigest()
    environment.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
            "FAKE_HDIUTIL_STATE": str(state_path),
            "FAKE_EXTERNAL_VICTIM": str(victim),
            "TOBKIRI_PACKAGING_PYTHON": interpreter,
            "TOBKIRI_PACKAGING_PYTHON_SHA256": digest,
            "TOBKIRI_PACKAGING_PYTHON_SNAPSHOT": str(formal_python_snapshot),
        }
    )
    if mode == "fifo_substitution":
        environment.update(
            {
                "FAKE_FIFO_SUBSTITUTION": "1",
                "FORMAL_PYTHON_DELEGATE": str(Path(os.path.realpath(sys.executable))),
            }
        )
    return app, output_dir, state_path, environment


def _command(app: Path, output_dir: Path) -> list[str]:
    return [
        "/bin/bash",
        str(SCRIPT),
        "--app-bundle",
        str(app),
        "--target",
        "x86_64-apple-darwin",
        "--allow-ad-hoc-local",
        "--output-dir",
        str(output_dir),
    ]


def _run_packager(
    root: Path, mode: str, *, timeout: float | None = None
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    app, output_dir, state_path, environment = _prepare(root, mode)
    process = subprocess.Popen(
        _command(app, output_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as timeout_error:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        raise AssertionError(
            "packager timed out while opening a FIFO substitution\n"
            f"stdout={stdout}\n"
            f"stderr={stderr}"
        ) from timeout_error
    result = subprocess.CompletedProcess(
        process.args, process.returncode, stdout, stderr
    )
    return result, output_dir, state_path


def _state(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _temporary_workspaces(output_dir: Path) -> list[Path]:
    return list(output_dir.glob(".tobkiri-dmg.*"))


def test_resource_busy_is_one_shot_and_preserves_stderr(tmp_path: Path) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "resource_busy")
    assert isinstance(result, subprocess.CompletedProcess)
    state = _state(state_path)
    argv = state["commands"]
    assert result.returncode == 1, result.stderr
    assert state["create_count"] == 1
    assert len(argv) == 1
    assert argv[0][0] == "create", "foreign hdiutil command"
    assert "Resource busy" in result.stderr
    assert state["detach"] == ["/dev/disk42"]
    assert "/dev/disk99" not in state["detach"]
    assert not (output_dir / FINAL_NAME).exists()
    assert _temporary_workspaces(output_dir) == []


def test_permanent_hdiutil_error_is_not_retried_and_stderr_is_preserved(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "permanent")
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 7, result.stderr
    assert _state(state_path)["create_count"] == 1
    assert "permission denied" in result.stderr
    assert "Resource busy" not in result.stderr
    assert not (output_dir / FINAL_NAME).exists()
    assert _temporary_workspaces(output_dir) == []


def test_formal_python_helpers_use_verified_interpreter_and_digest(tmp_path: Path) -> None:
    app, output_dir, state_path, environment = _prepare(tmp_path, "permanent")
    argv = _command(app, output_dir)
    missing_environment = environment.copy()
    missing_environment.pop("TOBKIRI_PACKAGING_PYTHON")
    missing = subprocess.run(
        argv, capture_output=True, check=False, env=missing_environment, text=True
    )
    assert isinstance(missing, subprocess.CompletedProcess)
    assert missing.returncode != 0
    assert "missing" in missing.stderr.lower()
    assert "path" in missing.stderr.lower()
    relative_environment = environment.copy()
    relative_environment["TOBKIRI_PACKAGING_PYTHON"] = "python3"
    relative = subprocess.run(
        argv, capture_output=True, check=False, env=relative_environment, text=True
    )
    assert isinstance(relative, subprocess.CompletedProcess)
    assert relative.returncode != 0
    assert "absolute" in relative.stderr.lower()
    assert "python3" in relative_environment["TOBKIRI_PACKAGING_PYTHON"]
    mismatch_environment = environment.copy()
    mismatch_environment["TOBKIRI_PACKAGING_PYTHON_SHA256"] = "0" * 64
    mismatch = subprocess.run(
        argv, capture_output=True, check=False, env=mismatch_environment, text=True
    )
    assert isinstance(mismatch, subprocess.CompletedProcess)
    assert mismatch.returncode != 0
    assert "sha256" in mismatch.stderr.lower()
    assert "mismatch" in mismatch.stderr.lower()
    assert "wrapper" in mismatch.stderr.lower()
    assert _state(state_path)["create_count"] == 0

    missing_snapshot_environment = environment.copy()
    missing_snapshot_environment.pop("TOBKIRI_PACKAGING_PYTHON_SNAPSHOT")
    missing_snapshot = subprocess.run(
        argv,
        capture_output=True,
        check=False,
        env=missing_snapshot_environment,
        text=True,
    )
    assert isinstance(missing_snapshot, subprocess.CompletedProcess)
    assert missing_snapshot.returncode != 0
    assert "snapshot" in missing_snapshot.stderr.lower()
    assert _state(state_path)["create_count"] == 0


def test_formal_python_runs_from_the_sealed_snapshot_root(tmp_path: Path) -> None:
    app, output_dir, state_path, environment = _prepare(tmp_path, "permanent")
    snapshot = tmp_path / "formal-python-snapshot"
    delegate = Path(os.path.realpath(sys.executable))
    wrapper = tmp_path / "formal-python"
    _write_executable(
        wrapper,
        """#!/bin/sh
set -eu
if [ "$PWD" != "$EXPECTED_FORMAL_PYTHON_CWD" ]; then
  printf 'unexpected formal Python cwd: %s\\n' "$PWD" >&2
  exit 88
fi
exec "$FORMAL_PYTHON_DELEGATE" "$@"
""",
    )
    environment.update(
        {
            "EXPECTED_FORMAL_PYTHON_CWD": str(snapshot),
            "FORMAL_PYTHON_DELEGATE": str(delegate),
            "TOBKIRI_PACKAGING_PYTHON": str(wrapper),
            "TOBKIRI_PACKAGING_PYTHON_SHA256": hashlib.sha256(
                wrapper.read_bytes()
            ).hexdigest(),
        }
    )
    caller = tmp_path / "caller"
    caller.mkdir()
    result = subprocess.run(
        _command(app, output_dir),
        capture_output=True,
        check=False,
        cwd=caller,
        env=environment,
        text=True,
    )
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 7, result.stderr
    assert "permission denied" in result.stderr
    assert _state(state_path)["create_count"] == 1


def test_failure_cleanup_only_detaches_owned_images(tmp_path: Path) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "resource_busy")
    assert isinstance(result, subprocess.CompletedProcess)
    state = _state(state_path)
    assert result.returncode == 1
    assert state["detach"] == ["/dev/disk42"]
    assert "/dev/disk99" not in state["detach"]
    assert "Resource busy" in result.stderr
    assert _temporary_workspaces(output_dir) == []


def test_output_publication_never_clobbers_existing_trusted_file(tmp_path: Path) -> None:
    app, output_dir, state_path, environment = _prepare(tmp_path, "success")
    final_path = output_dir / FINAL_NAME
    final_path.write_bytes(b"trusted-existing-output")
    result = subprocess.run(
        _command(app, output_dir),
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 1
    assert _state(state_path)["create_count"] == 0
    assert final_path.read_bytes() == b"trusted-existing-output"
    assert "Refusing to overwrite" in result.stderr
    assert _temporary_workspaces(output_dir) == []


def test_primary_package_error_wins_when_cleanup_rejects_external_link(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "primary_error")
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 7, result.stderr
    assert "permission denied" in result.stderr
    assert "descriptor-bound POSIX tree contains a symlink" in result.stderr
    assert "Could not remove temporary DMG workspace" in result.stderr
    assert (tmp_path / "external-victim" / "keep.txt").read_text(
        encoding="utf-8"
    ) == "keep"
    assert _state(state_path)["create_count"] == 1
    assert len(_temporary_workspaces(output_dir)) == 1


def test_cleanup_failure_after_success_fails_without_deleting_published_dmg(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(
        tmp_path, "success_cleanup_failure"
    )
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 1
    assert "Could not remove temporary DMG workspace" in result.stderr
    published_path = output_dir / FINAL_NAME
    with published_path.open("rb") as stream:
        assert stream.read(len(b"DMG-1")) == b"DMG-1"
    assert published_path.stat().st_size == 10240000000
    assert (tmp_path / "external-victim" / "keep.txt").read_text(
        encoding="utf-8"
    ) == "keep"
    assert _state(state_path)["detach"] == ["/dev/disk42"]
    assert len(_temporary_workspaces(output_dir)) == 1


def test_rebound_device_is_rejected_without_detaching_foreign_device(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "rebound_device")
    assert isinstance(result, subprocess.CompletedProcess)
    state = _state(state_path)
    assert result.returncode == 1
    assert state["detach"] == []
    assert "foreign detach refused" in result.stderr
    assert "/dev/disk99" not in state["detach"]
    assert not (output_dir / FINAL_NAME).exists()
    assert len(_temporary_workspaces(output_dir)) == 1


def test_mount_rebinding_is_rejected_without_detaching_owned_device(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "mount_rebinding")
    assert isinstance(result, subprocess.CompletedProcess)
    state = _state(state_path)
    assert result.returncode == 1
    assert state["detach"] == []
    assert "mapping changed" in result.stderr
    assert "/dev/disk42" not in state["detach"]
    assert not (output_dir / FINAL_NAME).exists()
    assert len(_temporary_workspaces(output_dir)) == 1


def test_replaced_image_path_is_not_unlinked_or_detached(tmp_path: Path) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "replaced_path")
    assert isinstance(result, subprocess.CompletedProcess)
    state = _state(state_path)
    assert result.returncode == 1
    assert state["detach"] == []
    assert "identity changed" in result.stderr
    assert not (output_dir / FINAL_NAME).exists()
    workspace = _temporary_workspaces(output_dir)[0]
    replaced_path = next((workspace / "images").glob("*.dmg"))
    assert replaced_path.is_symlink()
    assert replaced_path.read_bytes() == b"replacement-bytes"
    assert (tmp_path / "external-victim" / "replacement.bin").read_bytes() == (
        b"replacement-bytes"
    )


def test_detached_create_result_is_identity_bound_regular_file_until_retention_verification(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "success")
    state = _state(state_path)
    assert result.returncode == 0, result.stderr
    assert state["requested_size"] == "10000000k"
    events = state["events"]
    assert "attach" not in events
    assert events.index("create") < events.index("verify")
    assert events.index("verify") < events.index("detach")
    assert (output_dir / FINAL_NAME).stat().st_size >= 10240000000


def test_detached_create_result_replacement_fails_before_attach(tmp_path: Path) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "replaced_path")
    state = _state(state_path)
    assert result.returncode == 1
    assert "identity changed during retained verification" in result.stderr
    assert "attach" not in state["events"]
    assert state["detach"] == []
    assert not (output_dir / FINAL_NAME).exists()


def test_detached_create_result_non_regular_fails_before_attach(tmp_path: Path) -> None:
    for mode in ("symlink", "directory", "fifo", "fifo_substitution"):
        result, output_dir, state_path = _run_packager(
            tmp_path / mode, mode, timeout=5
        )
        state = _state(state_path)
        assert result.returncode == 1
        assert "detached regular file" in result.stderr
        assert "attach" not in state["events"]
        assert "verify" not in state["events"]
        assert state["detach"] == []
        assert not (output_dir / FINAL_NAME).exists()


def test_precreate_floor_is_at_least_10000000_kib_before_attach(tmp_path: Path) -> None:
    below, below_output, below_state_path = _run_packager(
        tmp_path / "below", "under_floor"
    )
    below_state = _state(below_state_path)
    assert below.returncode == 1
    assert below_state["requested_size"] == "10000000k"
    assert "logical size is below 10000000 KiB" in below.stderr
    assert "verify" not in below_state["events"]
    assert "attach" not in below_state["events"]
    assert not (below_output / FINAL_NAME).exists()

    boundary, boundary_output, boundary_state_path = _run_packager(
        tmp_path / "boundary", "success"
    )
    boundary_state = _state(boundary_state_path)
    assert boundary.returncode == 0, boundary.stderr
    assert boundary_state["requested_size"] == "10000000k"
    assert (boundary_output / FINAL_NAME).stat().st_size == 10240000000
    assert "attach" not in boundary_state["events"]
