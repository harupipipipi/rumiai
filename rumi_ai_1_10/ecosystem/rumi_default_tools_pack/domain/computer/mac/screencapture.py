"""ScreenCaptureKit + screencapture CLI fallback for macOS.

Captures window screenshots using ScreenCaptureKit when available,
falling back to the screencapture CLI tool.
"""

from __future__ import annotations

import base64
import subprocess
import sys
import tempfile
from pathlib import Path

_SCK_AVAILABLE = False

if sys.platform == "darwin":
    try:
        import ScreenCaptureKit  # type: ignore[import]  # noqa: F401

        _SCK_AVAILABLE = True
    except ImportError:
        pass


def screen_capture_kit_available() -> bool:
    """Check if ScreenCaptureKit is available."""
    return sys.platform == "darwin" and _SCK_AVAILABLE


def list_windows() -> list[dict]:
    """List visible windows via CGWindowListCopyWindowInfo."""
    if sys.platform != "darwin":
        return []
    try:
        from Quartz import (  # type: ignore[import]
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )

        info_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )
        results = []
        for info in info_list or []:
            bounds = info.get("kCGWindowBounds", {})
            results.append({
                "window_id": int(info.get("kCGWindowNumber", 0)),
                "pid": int(info.get("kCGWindowOwnerPID", 0)),
                "app": str(info.get("kCGWindowOwnerName", "")),
                "title": str(info.get("kCGWindowName", "")),
                "bounds": dict(bounds) if bounds else {},
            })
        return results
    except Exception:
        return []


def capture_window(
    window_id: int | None = None,
    pid: int | None = None,
    app: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Capture a window screenshot.

    Returns dict with path, data_url, coordinate_system, method, error.
    """
    if sys.platform != "darwin":
        return {
            "path": "",
            "data_url": "",
            "coordinate_system": "window_pixels",
            "method": "unavailable",
            "error": "Not macOS",
        }

    # Resolve window_id from pid/app if needed
    if window_id is None and (pid or app):
        window_id = _resolve_window_id(pid, app)

    if window_id is None:
        return {
            "path": "",
            "data_url": "",
            "coordinate_system": "window_pixels",
            "method": "unavailable",
            "error": "No window_id resolved",
        }

    # Try screencapture CLI (always available on macOS)
    out = output_path or tempfile.mktemp(suffix=".png")
    try:
        result = subprocess.run(
            ["screencapture", "-l", str(window_id), "-x", out],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0 and Path(out).exists():
            data_url = ""
            try:
                raw = Path(out).read_bytes()
                b64 = base64.b64encode(raw).decode("ascii")
                data_url = f"data:image/png;base64,{b64}"
            except Exception:
                pass
            return {
                "path": out,
                "data_url": data_url,
                "coordinate_system": "window_pixels",
                "method": "screencapture_cli",
                "error": None,
            }
        return {
            "path": "",
            "data_url": "",
            "coordinate_system": "window_pixels",
            "method": "unavailable",
            "error": f"screencapture failed: rc={result.returncode}",
        }
    except Exception as e:
        return {
            "path": "",
            "data_url": "",
            "coordinate_system": "window_pixels",
            "method": "unavailable",
            "error": str(e),
        }


def _resolve_window_id(pid: int | None, app: str | None) -> int | None:
    """Resolve a window_id from pid or app name."""
    windows = list_windows()
    for w in windows:
        if pid and w.get("pid") == pid:
            return w.get("window_id")
        if app and app.lower() in w.get("app", "").lower():
            return w.get("window_id")
    return None
