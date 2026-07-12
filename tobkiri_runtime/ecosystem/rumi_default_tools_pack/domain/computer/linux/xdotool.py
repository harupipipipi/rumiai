"""Linux visible-desktop helpers for Computer Use.

These helpers intentionally stay foreground/visible-screen oriented. Linux
desktop automation varies by display server and compositor, so every function
returns best-effort structured data instead of raising for missing tools.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def desktop_session_available() -> bool:
    return is_linux() and bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def _run(args: list[str], *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _proc_name(pid: int | None) -> str:
    if not pid:
        return ""
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _safe_int(value: Any) -> int:
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return 0


def _window_id_matches(left: Any, right: Any) -> bool:
    left_text = str(left or "").strip().lower()
    right_text = str(right or "").strip().lower()
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    left_int = _safe_int(left_text)
    right_int = _safe_int(right_text)
    return bool(left_int and right_int and left_int == right_int)


def active_window_id() -> str:
    if not command_available("xdotool"):
        return ""
    completed = _run(["xdotool", "getactivewindow"])
    return completed.stdout.strip() if completed.returncode == 0 else ""


def list_windows() -> list[dict[str, Any]]:
    if not (desktop_session_available() and command_available("wmctrl")):
        return []
    completed = _run(["wmctrl", "-lG", "-p"])
    if completed.returncode != 0:
        return []
    active = active_window_id()
    windows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        window_id, desktop, pid, x, y, width, height, _host, title = parts
        pid_int = _safe_int(pid)
        app = _proc_name(pid_int)
        windows.append(
            {
                "window_id": window_id,
                "id": window_id,
                "desktop": _safe_int(desktop),
                "pid": pid_int or None,
                "app": app,
                "title": title,
                "x": _safe_int(x),
                "y": _safe_int(y),
                "width": _safe_int(width),
                "height": _safe_int(height),
                "active": _window_id_matches(window_id, active),
                "platform": "Linux",
            }
        )
    return windows


def running_apps() -> list[dict[str, Any]]:
    apps: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for window in list_windows():
        app = str(window.get("app") or "").strip()
        pid = _safe_int(window.get("pid"))
        if not app:
            continue
        key = (app.lower(), pid)
        if key in seen:
            continue
        seen.add(key)
        apps.append(
            {
                "name": app,
                "app": app,
                "pid": pid or None,
                "active": bool(window.get("active")),
                "running": True,
            }
        )
    return apps


def installed_apps(*, limit: int = 300) -> list[dict[str, Any]]:
    roots = [
        Path.home() / ".local" / "share" / "applications",
        Path("/usr/local/share/applications"),
        Path("/usr/share/applications"),
    ]
    apps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.desktop")):
            if len(apps) >= limit:
                return apps
            parsed = _parse_desktop_file(path)
            name = str(parsed.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            apps.append(
                {
                    "name": name,
                    "app": name,
                    "path": str(path),
                    "exec": parsed.get("exec", ""),
                    "running": False,
                }
            )
    return apps


def _parse_desktop_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("Name=") and "name" not in result:
                result["name"] = line.split("=", 1)[1].strip()
            elif line.startswith("Exec=") and "exec" not in result:
                result["exec"] = line.split("=", 1)[1].strip()
    except OSError:
        return {}
    return result


def find_window(*, window_id: Any = None, app: str = "", title: str = "") -> dict[str, Any] | None:
    requested_id = str(window_id or "").strip().lower()
    app_needle = str(app or "").strip().casefold()
    title_needle = str(title or "").strip().casefold()
    for window in list_windows():
        if requested_id and _window_id_matches(window.get("window_id"), requested_id):
            return window
    for window in list_windows():
        if app_needle and app_needle not in str(window.get("app") or "").casefold():
            continue
        if title_needle and title_needle not in str(window.get("title") or "").casefold():
            continue
        if app_needle or title_needle:
            return window
    return None


def activate_window(window: dict[str, Any] | None) -> bool:
    if not window or not command_available("xdotool"):
        return False
    window_id = str(window.get("window_id") or "").strip()
    if not window_id:
        return False
    completed = _run(["xdotool", "windowactivate", "--sync", window_id])
    return completed.returncode == 0


def screenshot(path: Path, target: dict[str, Any] | None = None) -> dict[str, Any]:
    if not desktop_session_available():
        return _unavailable("No Linux desktop session is available.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if target and command_available("import"):
        window_id = str(target.get("window_id") or "").strip()
        if window_id:
            completed = _run(["import", "-window", window_id, str(path)], timeout=10)
            if completed.returncode == 0 and path.exists():
                return _screenshot_result(path, "imagemagick_import_window", target)
    commands = [
        ["gnome-screenshot", "-f", str(path)],
        ["scrot", str(path)],
        ["import", "-window", "root", str(path)],
        ["spectacle", "-bn", "-o", str(path)],
    ]
    for command in commands:
        if not command_available(command[0]):
            continue
        completed = _run(command, timeout=10)
        if completed.returncode == 0 and path.exists():
            return _screenshot_result(path, command[0], target)
    return _unavailable("No supported Linux screenshot tool was found.")


def _screenshot_result(path: Path, method: str, target: dict[str, Any] | None) -> dict[str, Any]:
    data_url = ""
    try:
        data_url = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        pass
    return {
        "path": str(path),
        "data_url": data_url,
        "coordinate_system": "screen_pixels",
        "method": method,
        "target_window": target,
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "path": "",
        "data_url": "",
        "coordinate_system": "screen_pixels",
        "method": "unavailable",
        "error": reason,
    }


def move(x: int, y: int) -> bool:
    if not command_available("xdotool"):
        return False
    return _run(["xdotool", "mousemove", str(int(x)), str(int(y))]).returncode == 0


def click(x: int, y: int, *, button: str = "left") -> bool:
    if not command_available("xdotool"):
        return False
    button_id = {"left": "1", "middle": "2", "center": "2", "right": "3"}.get(button.lower(), "1")
    return _run(["xdotool", "mousemove", str(int(x)), str(int(y)), "click", button_id]).returncode == 0


def drag(x1: int, y1: int, x2: int, y2: int) -> bool:
    if not command_available("xdotool"):
        return False
    completed = _run(
        [
            "xdotool",
            "mousemove",
            str(int(x1)),
            str(int(y1)),
            "mousedown",
            "1",
            "mousemove",
            "--sync",
            str(int(x2)),
            str(int(y2)),
            "mouseup",
            "1",
        ],
        timeout=10,
    )
    return completed.returncode == 0


def type_text(text: str) -> bool:
    if not command_available("xdotool"):
        return False
    completed = _run(["xdotool", "type", "--delay", "1", str(text)], timeout=max(5, len(text) / 20))
    return completed.returncode == 0


def key(key_combo: str) -> bool:
    if not command_available("xdotool"):
        return False
    normalized = str(key_combo or "").replace("command", "ctrl").replace("cmd", "ctrl")
    normalized = "+".join(part.strip() for part in normalized.split("+") if part.strip())
    if not normalized:
        return False
    return _run(["xdotool", "key", normalized]).returncode == 0


def scroll(direction: str, clicks: int) -> bool:
    if not command_available("xdotool"):
        return False
    button = {
        "up": "4",
        "down": "5",
        "left": "6",
        "right": "7",
    }.get(str(direction or "down").lower(), "5")
    ok = True
    for _ in range(max(1, min(100, int(clicks or 1)))):
        ok = _run(["xdotool", "click", button]).returncode == 0 and ok
        time.sleep(0.01)
    return ok


def temp_screenshot_path() -> Path:
    return Path(tempfile.gettempdir()) / f"rumi-linux-computer-{int(time.time() * 1000)}.png"
