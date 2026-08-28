#!/usr/bin/env python3
"""Launch the final macOS DMG application through LaunchServices.

The verifier attaches the final DMG read-only, copies its sole application
bundle out of the mounted volume, and starts that copied bundle with the
system ``open`` command.  It then asks System Events for a visible application
window before reporting success.  The mounted volume and temporary copy are
both bound to paths created by this process and are cleaned up fail-closed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_active_release_targets() -> tuple[str, ...]:
    """Load the root release authority without a shadowable package import.

    Packaging tests intentionally run with ``tobkiri_runtime`` on
    ``PYTHONPATH``.  That tree also has a ``scripts`` package, so importing
    ``scripts.release_inventory`` by module name can resolve the wrong package.
    The release inventory is a fixed repository file; load that exact file.
    """

    inventory_path = REPOSITORY_ROOT / "scripts" / "release_inventory.py"
    spec = importlib.util.spec_from_file_location(
        "tobkiri_release_inventory", inventory_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load release inventory: {inventory_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    targets = getattr(module, "ACTIVE_RELEASE_TARGETS", None)
    if not isinstance(targets, tuple) or not all(
        isinstance(target, str) for target in targets
    ):
        raise ImportError("release inventory has invalid active target authority")
    return targets


ACTIVE_RELEASE_TARGETS = _load_active_release_targets()
from tobkiri_launcher.scripts.verify_packaged_python_dmg import (  # noqa: E402
    DmgVerificationError,
    Executable,
    MountedDmg,
    _bind_executable,
    _verify_executable,
)


APP_NAME = "Tobkiri Launcher.app"
BUNDLE_IDENTIFIER = "dev.tobkiri.launcher"
COPY_PREFIX = ".tobkiri-dmg-launch-"
DEFAULT_TIMEOUT_SECONDS = 90.0
POLL_INTERVAL_SECONDS = 0.5
TOOL_TIMEOUT_SECONDS = 15.0

VISIBLE_UI_APPLESCRIPT = '''
tell application "System Events"
    if exists process "Tobkiri Launcher" then
        tell process "Tobkiri Launcher"
            if bundle identifier is "dev.tobkiri.launcher" and visible is true and (count of windows) > 0 then
                return "visible"
            end if
        end tell
    end if
end tell
return "not-visible"
'''

QUIT_APPLESCRIPT = 'tell application id "dev.tobkiri.launcher" to quit'


class DmgLaunchVerificationError(DmgVerificationError):
    """Raised when the final DMG cannot prove a visible LaunchServices boot."""


def _canonical_regular_file(path: Path, label: str) -> Path:
    """Return an absolute regular file whose path contains no symlink."""
    if not path.is_absolute():
        path = path.absolute()
    try:
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError as error:
        raise DmgLaunchVerificationError(f"{label} is unavailable") from error
    if path != resolved or path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise DmgLaunchVerificationError(
            f"{label} must be a canonical regular file"
        )
    return path


def _canonical_directory(path: Path, label: str) -> Path:
    """Return an absolute directory whose path contains no symlink."""
    if not path.is_absolute():
        path = path.absolute()
    try:
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError as error:
        raise DmgLaunchVerificationError(f"{label} is unavailable") from error
    if path != resolved or path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise DmgLaunchVerificationError(
            f"{label} must be a canonical real directory"
        )
    return path


def _system_executable(name: str) -> Executable:
    """Bind one fixed macOS system tool before it is executed."""
    if not name or "/" in name or "\\" in name:
        raise DmgLaunchVerificationError("invalid system executable name")
    return _bind_executable(Path("/usr/bin") / name, f"/usr/bin/{name}")


def _run_tool(
    executable: Executable,
    arguments: Sequence[str],
    *,
    timeout_seconds: float = TOOL_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    """Run a bound system tool with bounded output and execution time."""
    _verify_executable(executable)
    try:
        return subprocess.run(
            [os.fspath(executable.path), *arguments],
            check=False,
            close_fds=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise DmgLaunchVerificationError(
            f"{executable.path.name} timed out"
        ) from error


def _tool_failure(result: subprocess.CompletedProcess[bytes], label: str) -> str:
    """Format a bounded tool failure without exposing unrelated environment."""
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    if len(detail) > 2000:
        detail = detail[-2000:]
    suffix = f": {detail}" if detail else ""
    return f"{label} failed with status {result.returncode}{suffix}"


def _bundle_executable_name(metadata: dict[str, Any]) -> str:
    """Validate and return the bundle-relative executable filename."""
    executable_name = metadata.get("CFBundleExecutable")
    if not isinstance(executable_name, str) or not executable_name:
        raise DmgLaunchVerificationError(
            "application CFBundleExecutable must be a non-empty filename"
        )
    if (
        executable_name in {".", ".."}
        or Path(executable_name).is_absolute()
        or "/" in executable_name
        or "\\" in executable_name
        or "\x00" in executable_name
    ):
        raise DmgLaunchVerificationError(
            "application CFBundleExecutable must be bundle-relative"
        )
    return executable_name


def _validate_application_bundle(app_bundle: Path) -> dict[str, str]:
    """Validate the production bundle identity and its executable."""
    app_bundle = _canonical_directory(app_bundle, "application bundle")
    if app_bundle.name != APP_NAME:
        raise DmgLaunchVerificationError(
            "final DMG must contain the production Tobkiri Launcher app"
        )
    info_plist = _canonical_regular_file(
        app_bundle / "Contents" / "Info.plist", "application Info.plist"
    )
    try:
        with info_plist.open("rb") as source:
            metadata = plistlib.load(source)
    except (OSError, plistlib.InvalidFileException, ValueError) as error:
        raise DmgLaunchVerificationError("application Info.plist is unreadable") from error
    if not isinstance(metadata, dict):
        raise DmgLaunchVerificationError("application Info.plist is not a dictionary")
    if metadata.get("CFBundleIdentifier") != BUNDLE_IDENTIFIER:
        raise DmgLaunchVerificationError("application bundle identifier is invalid")
    executable_name = _bundle_executable_name(metadata)
    executable = _canonical_regular_file(
        app_bundle / "Contents" / "MacOS" / executable_name,
        "application executable",
    )
    if not os.access(executable, os.X_OK):
        raise DmgLaunchVerificationError("application executable is not executable")
    return {
        "bundle_identifier": BUNDLE_IDENTIFIER,
        "executable": executable_name,
    }


def _copy_application(
    source: Path, destination_root: Path, ditto: Executable
) -> Path:
    """Copy a mounted application bundle into the process-owned temp root."""
    destination_root = _canonical_directory(destination_root, "application copy root")
    destination = destination_root / source.name
    if destination.exists() or destination.is_symlink():
        raise DmgLaunchVerificationError("application copy destination already exists")
    result = _run_tool(
        ditto,
        ["--rsrc", "--extattr", "--acl", os.fspath(source), os.fspath(destination)],
    )
    if result.returncode != 0:
        raise DmgLaunchVerificationError(_tool_failure(result, "ditto application copy"))
    return _canonical_directory(destination, "copied application bundle")


def _visible_ui(osascript: Executable) -> bool:
    """Return whether System Events currently sees a visible app window."""
    result = _run_tool(osascript, ["-e", VISIBLE_UI_APPLESCRIPT])
    if result.returncode != 0:
        return False
    return result.stdout.decode("utf-8", errors="replace").strip() == "visible"


def _wait_for_visible_ui(osascript: Executable, timeout_seconds: float) -> None:
    """Wait until the launched production process exposes a visible window."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _visible_ui(osascript):
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    raise DmgLaunchVerificationError(
        "LaunchServices-launched application did not expose a visible window"
    )


def _quit_launched_application(osascript: Executable) -> None:
    """Ask the exact production bundle to quit after the UI smoke test."""
    result = _run_tool(osascript, ["-e", QUIT_APPLESCRIPT])
    if result.returncode != 0:
        raise DmgLaunchVerificationError(
            _tool_failure(result, "quit production application")
        )


def _remove_application_copy(copy_root: Path, parent: Path) -> None:
    """Remove only the canonical temporary directory created for this run."""
    if copy_root.parent != parent or not copy_root.name.startswith(COPY_PREFIX):
        raise DmgLaunchVerificationError("application copy root is not process-owned")
    _canonical_directory(copy_root, "application copy root")
    shutil.rmtree(copy_root)


def _validate_target(target: str) -> str:
    """Require the final DMG target to be an active production target."""
    if target not in ACTIVE_RELEASE_TARGETS:
        raise DmgLaunchVerificationError(f"release target is not active: {target}")
    return target


def verify_dmg(
    dmg: Path, target: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> dict[str, object]:
    """Mount, copy, launch, and visibly smoke-test one final production DMG."""
    if sys.platform != "darwin":
        raise DmgLaunchVerificationError(
            "final macOS DMG launch verification requires macOS"
        )
    if timeout_seconds <= 0:
        raise DmgLaunchVerificationError("UI timeout must be positive")
    target = _validate_target(target)
    dmg = _canonical_regular_file(dmg, "final DMG")
    ditto = _system_executable("ditto")
    open_tool = _system_executable("open")
    osascript = _system_executable("osascript")
    codesign = _system_executable("codesign")
    mount = MountedDmg(dmg)
    copy_root: Path | None = None
    launched = False
    primary_error: BaseException | None = None
    try:
        mount.attach()
        mounted_app = mount.application_bundle()
        mounted_identity = _validate_application_bundle(mounted_app)

        created_copy_root = Path(tempfile.mkdtemp(prefix=COPY_PREFIX, dir=mount.parent))
        copy_root = created_copy_root
        copy_root = _canonical_directory(copy_root, "application copy root")
        copied_app = _copy_application(mounted_app, copy_root, ditto)
        copied_identity = _validate_application_bundle(copied_app)
        if copied_identity != mounted_identity:
            raise DmgLaunchVerificationError(
                "copied application identity differs from the mounted application"
            )
        mount.verify_mounted()

        codesign_result = _run_tool(
            codesign,
            ["--verify", "--deep", "--strict", "--verbose=2", os.fspath(copied_app)],
        )
        if codesign_result.returncode != 0:
            raise DmgLaunchVerificationError(
                _tool_failure(codesign_result, "copied application codesign verification")
            )
        mount.verify_mounted()

        launch_result = _run_tool(open_tool, ["-n", os.fspath(copied_app)])
        if launch_result.returncode != 0:
            raise DmgLaunchVerificationError(
                _tool_failure(launch_result, "LaunchServices open")
            )
        launched = True
        _wait_for_visible_ui(osascript, timeout_seconds)
        return {
            "target": target,
            "bundle_identifier": copied_identity["bundle_identifier"],
            "copied_application": os.fspath(copied_app),
            "visible_ui": True,
        }
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_errors: list[BaseException] = []
        if launched:
            try:
                _quit_launched_application(osascript)
            except BaseException as error:
                cleanup_errors.append(error)
        if copy_root is not None:
            try:
                _remove_application_copy(copy_root, mount.parent)
            except BaseException as error:
                cleanup_errors.append(error)
        try:
            mount.cleanup()
        except BaseException as error:
            cleanup_errors.append(error)
        try:
            mount.close()
        except BaseException as error:
            cleanup_errors.append(error)
        if cleanup_errors:
            if primary_error is None:
                details = "; ".join(str(error) for error in cleanup_errors)
                raise DmgLaunchVerificationError(
                    f"final DMG launch cleanup failed: {details}"
                )
            for error in cleanup_errors:
                print(f"final DMG launch cleanup also failed: {error}", file=sys.stderr)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for final DMG launch verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run final DMG launch verification and emit non-sensitive evidence."""
    args = parse_args(argv)
    try:
        result = verify_dmg(args.dmg, args.target, args.timeout_seconds)
    except (DmgLaunchVerificationError, OSError, ValueError) as error:
        print(f"final macOS DMG launch verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
