"""Mac helper utilities – platform detection, TCC checks, app management.

Provides utility functions for macOS-specific operations used by
the Mac drivers.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def is_macos() -> bool:
    """Check if the current platform is macOS.

    Returns:
        True if running on macOS.
    """
    return sys.platform == "darwin"


def macos_version() -> tuple[int, ...]:
    """Get the macOS version as a tuple.

    Returns:
        Version tuple, e.g. (14, 2, 1). Returns (0,) on failure.
    """
    if not is_macos():
        return (0,)
    try:
        result = subprocess.run(
            ["sw_vers", "-productVersion"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        parts = result.stdout.strip().split(".")
        return tuple(int(p) for p in parts)
    except (subprocess.SubprocessError, ValueError):
        return (0,)


def tcc_accessibility_granted() -> bool:
    """Check if Accessibility (TCC) permission is granted.

    Uses AXIsProcessTrusted via a small Swift/osascript check.

    Returns:
        True if accessibility permission is granted.
    """
    if not is_macos():
        return False
    try:
        script = (
            'tell application "System Events" to return '
            "(UI elements enabled)"
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "true" in result.stdout.lower()
    except subprocess.SubprocessError:
        return False


def tcc_screen_recording_granted() -> bool:
    """Check if Screen Recording (TCC) permission is likely granted.

    There's no direct API to check this; we attempt a screencapture
    and check if it succeeds.

    Returns:
        True if screen recording appears to be permitted.
    """
    if not is_macos():
        return False
    try:
        result = subprocess.run(
            ["screencapture", "-x", "-t", "png", "/dev/null"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False


def get_frontmost_app() -> dict[str, Any] | None:
    """Get the currently frontmost (active) application.

    Returns:
        Dict with 'name' and 'bundle_id', or None on failure.
    """
    if not is_macos():
        return None
    try:
        script = """
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    return {name of frontApp, bundle identifier of frontApp}
end tell
"""
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 2:
                return {"name": parts[0], "bundle_id": parts[1]}
            return {"name": parts[0], "bundle_id": ""}
        return None
    except subprocess.SubprocessError:
        return None


def activate_app(app: str, pid: int | None = None) -> bool:
    """Bring an application to the foreground.

    Args:
        app: Application name or bundle identifier.
        pid: Optional process ID.

    Returns:
        True if activation succeeded.
    """
    if not is_macos():
        return False
    try:
        if pid:
            script = f"""
tell application "System Events"
    set targetProcess to first application process whose unix id is {pid}
    set frontmost of targetProcess to true
end tell
"""
        else:
            script = f'tell application "{app}" to activate'

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False


def restore_app(previous_app: dict[str, Any]) -> bool:
    """Restore the previously frontmost application.

    Args:
        previous_app: Dict with 'name' key from get_frontmost_app().

    Returns:
        True if restoration succeeded.
    """
    if not previous_app:
        return False
    name = previous_app.get("name", "")
    if not name:
        return False
    return activate_app(name)
