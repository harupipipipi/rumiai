from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "package_macos_dmg.sh"
FINAL_NAME = "Tobkiri Launcher_1.2.3_x64.dmg"


def _write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def _create_fake_tools(root: Path, mode: str) -> tuple[Path, Path, Path]:
    """Create deterministic macOS command fakes for the shell harness."""
    bin_dir = root / "bin"
    bin_dir.mkdir()
    state_path = root / "hdiutil-state.json"
    state_path.write_text(
        json.dumps(
            {
                "mode": mode,
                "create_count": 0,
                "attached": [],
                "detach": [],
                "commands": [],
            }
        ),
        encoding="utf-8",
    )
    sleep_log = root / "sleep.log"
    sleep_log.touch()

    _write_executable(
        bin_dir / "codesign",
        """#!/bin/sh
if [ "${1:-}" = "--verify" ]; then
  exit 0
fi
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
sealed="$2/Contents/Resources/app/python-runtime"
if [ -d "$sealed" ]; then
  find "$sealed" -type f -exec chmod 0444 {} +
  find "$sealed" -type d -exec chmod 0555 {} +
fi
""",
    )
    _write_executable(
        bin_dir / "plutil",
        """#!/bin/sh
printf '%s\\n' '1.2.3'
""",
    )
    _write_executable(
        bin_dir / "sleep",
        """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_SLEEP_LOG"
""",
    )
    _write_executable(
        bin_dir / "hdiutil",
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


state_path = Path(os.environ["FAKE_HDIUTIL_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8"))
command = sys.argv[1]


def save():
    state_path.write_text(json.dumps(state), encoding="utf-8")


if command == "create":
    output = Path(sys.argv[-1])
    state["create_count"] += 1
    state["commands"].append(sys.argv[1:])
    attempt = state["create_count"]
    mode = state["mode"]
    if mode == "primary_and_cleanup_failure":
        workspace = output.parents[1]
        (workspace / "staging" / "external-victim").symlink_to(
            Path(os.environ["FAKE_EXTERNAL_VICTIM"]),
            target_is_directory=True,
        )
        save()
        print("hdiutil: create failed - permission denied", file=sys.stderr)
        raise SystemExit(7)
    if mode == "busy_then_success" and attempt == 1:
        state["attached"].append(str(output))
        save()
        print("hdiutil: create failed - Resource busy", file=sys.stderr)
        raise SystemExit(1)
    if mode == "always_busy" or (mode == "busy_then_error" and attempt == 1):
        state["attached"].append(str(output))
        save()
        print("hdiutil: create failed - Resource busy", file=sys.stderr)
        raise SystemExit(1)
    if mode in {"permanent", "busy_then_error"}:
        save()
        print("hdiutil: create failed - permission denied", file=sys.stderr)
        raise SystemExit(7)
    output.write_bytes(("DMG-%d" % attempt).encode("ascii"))
    if mode == "success_cleanup_failure":
        workspace = output.parents[1]
        (workspace / "staging" / "external-victim").symlink_to(
            Path(os.environ["FAKE_EXTERNAL_VICTIM"]),
            target_is_directory=True,
        )
    save()
    print("created: %s" % output)
    raise SystemExit(0)

if command == "info":
    print("framework : test")
    print("image-path      : /foreign/foreign.dmg")
    print("/dev/disk99 GUID_partition_scheme")
    print("================================================")
    for path in state["attached"]:
        print("image-path      : %s" % path)
        print("/dev/disk42 GUID_partition_scheme")
        print("/dev/disk42s1 APFS")
        print("================================================")
    raise SystemExit(0)

if command == "detach":
    device = sys.argv[2]
    state["detach"].append(device)
    if device == "/dev/disk99":
        print("refusing foreign detach", file=sys.stderr)
        save()
        raise SystemExit(9)
    state["attached"] = []
    save()
    raise SystemExit(0)

if command == "verify":
    if Path(sys.argv[-1]).is_file():
        raise SystemExit(0)
    print("missing image", file=sys.stderr)
    raise SystemExit(2)

print("unexpected hdiutil command: %s" % command, file=sys.stderr)
raise SystemExit(2)
""",
    )
    return bin_dir, state_path, sleep_log


def _fixture_app(root: Path) -> Path:
    app = root / "Tobkiri Launcher.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    sealed = contents / "Resources" / "app" / "python-runtime" / "nested"
    sealed.mkdir(parents=True)
    (contents / "Info.plist").write_text("fixture", encoding="utf-8")
    (contents / "MacOS" / "launcher").write_text("fixture", encoding="utf-8")
    (sealed / "sealed.py").write_text("fixture", encoding="utf-8")
    return app


def _run_packager(
    root: Path, mode: str
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    app = _fixture_app(root)
    output_dir = root / "output"
    output_dir.mkdir()
    bin_dir, state_path, sleep_log = _create_fake_tools(root, mode)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
    environment["FAKE_HDIUTIL_STATE"] = str(state_path)
    environment["FAKE_SLEEP_LOG"] = str(sleep_log)
    victim = root / "external-victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    environment["FAKE_EXTERNAL_VICTIM"] = str(victim)
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--app-bundle",
            str(app),
            "--target",
            "x86_64-apple-darwin",
            "--allow-ad-hoc-local",
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    return result, output_dir, state_path


def _state(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _temporary_workspaces(output_dir: Path) -> list[Path]:
    return list(output_dir.glob(".tobkiri-dmg.*"))


def test_busy_then_success_retries_once_and_publishes_verified_output(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "busy_then_success")

    assert result.returncode == 0, result.stderr
    state = _state(state_path)
    assert state["create_count"] == 2
    assert state["commands"][0][-1] != state["commands"][1][-1]
    assert state["detach"] == ["/dev/disk42"]
    assert "Resource busy" in result.stderr
    assert (output_dir / FINAL_NAME).read_bytes() == b"DMG-2"
    assert _temporary_workspaces(output_dir) == []


def test_permanent_hdiutil_error_is_not_retried_and_stderr_is_preserved(
    tmp_path: Path,
) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "permanent")

    assert result.returncode == 7, result.stderr
    assert _state(state_path)["create_count"] == 1
    assert "permission denied" in result.stderr
    assert "Retrying hdiutil create" not in result.stderr
    assert not (output_dir / FINAL_NAME).exists()
    assert _temporary_workspaces(output_dir) == []


def test_busy_retry_exhaustion_is_bounded(tmp_path: Path) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "always_busy")

    assert result.returncode == 1
    state = _state(state_path)
    assert state["create_count"] == 3
    assert state["detach"] == ["/dev/disk42", "/dev/disk42", "/dev/disk42"]
    assert len(result.stderr.split("Resource busy")) == 4
    assert "exhausted 3 attempts" in result.stderr
    assert (tmp_path / "sleep.log").read_text(encoding="utf-8").splitlines() == [
        "1",
        "2",
    ]
    assert not (output_dir / FINAL_NAME).exists()
    assert _temporary_workspaces(output_dir) == []


def test_failure_cleanup_only_detaches_owned_images(tmp_path: Path) -> None:
    result, output_dir, state_path = _run_packager(tmp_path, "busy_then_error")

    assert result.returncode == 7
    state = _state(state_path)
    assert state["create_count"] == 2
    assert state["detach"] == ["/dev/disk42"]
    assert "/dev/disk99" not in state["detach"]
    assert "permission denied" in result.stderr
    assert _temporary_workspaces(output_dir) == []


def test_output_publication_never_clobbers_existing_trusted_file(
    tmp_path: Path,
) -> None:
    app = _fixture_app(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    final_path = output_dir / FINAL_NAME
    final_path.write_bytes(b"trusted-existing-output")
    bin_dir, state_path, sleep_log = _create_fake_tools(tmp_path, "success")
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
    environment["FAKE_HDIUTIL_STATE"] = str(state_path)
    environment["FAKE_SLEEP_LOG"] = str(sleep_log)

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--app-bundle",
            str(app),
            "--target",
            "x86_64-apple-darwin",
            "--allow-ad-hoc-local",
            "--output-dir",
            str(output_dir),
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert result.returncode == 1
    assert _state(state_path)["create_count"] == 0
    assert final_path.read_bytes() == b"trusted-existing-output"
    assert "Refusing to overwrite" in result.stderr
    assert _temporary_workspaces(output_dir) == []


def test_primary_package_error_wins_when_cleanup_rejects_external_link(
    tmp_path: Path,
) -> None:
    result, output_dir, _state_path = _run_packager(
        tmp_path, "primary_and_cleanup_failure"
    )

    assert result.returncode == 7, result.stderr
    assert "permission denied" in result.stderr
    assert "descriptor-bound POSIX tree contains a symlink" in result.stderr
    assert "Could not remove temporary DMG workspace" in result.stderr
    assert (tmp_path / "external-victim" / "keep.txt").read_text(
        encoding="utf-8"
    ) == "keep"

    workspace = _temporary_workspaces(output_dir)[0]
    (workspace / "staging" / "external-victim").unlink()
    for path in sorted(workspace.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o700)
    workspace.chmod(0o700)
    shutil.rmtree(workspace)


def test_cleanup_failure_after_success_fails_without_deleting_published_dmg(
    tmp_path: Path,
) -> None:
    source_file = (
        tmp_path
        / "Tobkiri Launcher.app/Contents/Resources/app/python-runtime/nested/sealed.py"
    )
    result, output_dir, _state_path = _run_packager(
        tmp_path, "success_cleanup_failure"
    )

    assert result.returncode == 1
    assert "Could not remove temporary DMG workspace" in result.stderr
    assert (output_dir / FINAL_NAME).read_bytes() == b"DMG-1"
    assert source_file.read_text(encoding="utf-8") == "fixture"
    assert source_file.stat().st_mode & 0o777 == 0o644
    assert (tmp_path / "external-victim" / "keep.txt").read_text(
        encoding="utf-8"
    ) == "keep"

    workspace = _temporary_workspaces(output_dir)[0]
    (workspace / "staging" / "external-victim").unlink()
    for path in sorted(workspace.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o700)
    workspace.chmod(0o700)
    shutil.rmtree(workspace)
