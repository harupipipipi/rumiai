"""Owned X11 virtual desktop helper for Linux Computer Use.

This module intentionally targets a rumiai-owned Xvfb display instead of the
user's visible Linux/Wayland session. Every subprocess call receives an
explicit DISPLAY environment for the virtual session.
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
from dataclasses import dataclass
from typing import Any


REQUIRED_COMMANDS = ("Xvfb", "openbox", "xdotool", "import")


@dataclass(frozen=True)
class X11VirtualSessionConfig:
    width: int = 1280
    height: int = 800
    depth: int = 24
    display_min: int = 90
    display_max: int = 199
    startup_timeout: float = 5.0


class X11VirtualSession:
    """Manage a private Xvfb/Openbox desktop for AI computer actions."""

    def __init__(
        self,
        config: X11VirtualSessionConfig | None = None,
        *,
        env: dict[str, str] | None = None,
    ) -> None:
        self.config = config or X11VirtualSessionConfig()
        self._base_env = dict(os.environ if env is None else env)
        self._display_number: int | None = None
        self._display: str | None = None
        self._display_lock_dir: Path | None = None
        self._session_dir: Path | None = None
        self._processes: dict[str, subprocess.Popen[Any]] = {}

    @property
    def display(self) -> str | None:
        return self._display

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def is_available(self) -> bool:
        return sys.platform.startswith("linux") and not self.missing_commands()

    def missing_commands(self) -> list[str]:
        return [name for name in REQUIRED_COMMANDS if shutil.which(name) is None]

    def start(self) -> dict[str, Any]:
        """Start Xvfb and Openbox if needed."""

        if self._is_running():
            return self._status(available=True, running=True)
        if not sys.platform.startswith("linux"):
            return self._status(available=False, running=False, reason="Linux is required for X11 virtual sessions.")

        missing = self.missing_commands()
        if missing:
            return self._status(
                available=False,
                running=False,
                reason="Missing required X11 virtual desktop commands: " + ", ".join(missing),
                missing_commands=missing,
            )

        display_number = self._allocate_display_number()
        if display_number is None:
            return self._status(available=False, running=False, reason="No free X11 DISPLAY number was available.")

        self._display_number = display_number
        self._display = f":{display_number}"
        self._session_dir = Path(tempfile.mkdtemp(prefix=f"rumi-x11-virtual-{display_number}-"))

        try:
            env = self._session_env()
            geometry = f"{self.config.width}x{self.config.height}x{self.config.depth}"
            self._processes["xvfb"] = subprocess.Popen(
                ["Xvfb", self._display, "-screen", "0", geometry, "-nolisten", "tcp"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not self._wait_for_display():
                reason = "Xvfb did not become ready before the startup timeout."
                self.stop()
                return self._status(available=True, running=False, reason=reason)

            self._processes["openbox"] = subprocess.Popen(
                ["openbox"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.05)
            return self._status(available=True, running=self._is_running())
        except OSError as exc:
            reason = f"Failed to start X11 virtual desktop: {exc}"
            self.stop()
            return self._status(available=True, running=False, reason=reason)

    def stop(self) -> dict[str, Any]:
        """Stop managed processes and remove session artifacts."""

        for name in ("openbox", "xvfb"):
            proc = self._processes.pop(name, None)
            if proc is not None:
                self._terminate_process(proc)

        if self._session_dir is not None:
            shutil.rmtree(self._session_dir, ignore_errors=True)
        if self._display_lock_dir is not None:
            try:
                self._display_lock_dir.rmdir()
            except OSError:
                pass

        self._session_dir = None
        self._display_lock_dir = None
        self._display_number = None
        self._display = None
        return self._status(available=self.is_available(), running=False)

    def screenshot(self, path: Path | None = None) -> dict[str, Any]:
        reason = self._ensure_started()
        if reason:
            return self._unavailable_screenshot(reason)

        output_path = path or self._next_screenshot_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self._run(["import", "-window", "root", str(output_path)], timeout=10.0)
        if result.get("executed") and output_path.exists():
            data_url = ""
            try:
                data_url = "data:image/png;base64," + base64.b64encode(output_path.read_bytes()).decode("ascii")
            except OSError:
                pass
            return {
                "path": str(output_path),
                "data_url": data_url,
                "coordinate_system": "screen_pixels",
                "method": "imagemagick_import_root",
                "display": self._display,
                "session_dir": str(self._session_dir or ""),
            }
        return self._unavailable_screenshot(str(result.get("reason") or result.get("stderr") or "Screenshot failed."))

    def click(self, x: int, y: int, *, button: str = "left") -> dict[str, Any]:
        button_id = self._button_id(button)
        return self._run_xdotool(["mousemove", str(int(x)), str(int(y)), "click", button_id])

    def double_click(self, x: int, y: int, *, button: str = "left", delay_ms: int = 80) -> dict[str, Any]:
        button_id = self._button_id(button)
        return self._run_xdotool(
            [
                "mousemove",
                str(int(x)),
                str(int(y)),
                "click",
                "--repeat",
                "2",
                "--delay",
                str(max(0, int(delay_ms))),
                button_id,
            ]
        )

    def move(self, x: int, y: int) -> dict[str, Any]:
        return self._run_xdotool(["mousemove", str(int(x)), str(int(y))])

    def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left") -> dict[str, Any]:
        button_id = self._button_id(button)
        return self._run_xdotool(
            [
                "mousemove",
                str(int(x1)),
                str(int(y1)),
                "mousedown",
                button_id,
                "mousemove",
                "--sync",
                str(int(x2)),
                str(int(y2)),
                "mouseup",
                button_id,
            ],
            timeout=10.0,
        )

    def scroll(
        self,
        x: int = 0,
        y: int = 0,
        *,
        direction: str = "down",
        clicks: int = 3,
    ) -> dict[str, Any]:
        button_id = {
            "up": "4",
            "down": "5",
            "left": "6",
            "right": "7",
        }.get(str(direction or "down").lower(), "5")
        repeat = str(max(1, min(100, int(clicks or 1))))
        return self._run_xdotool(
            [
                "mousemove",
                str(int(x)),
                str(int(y)),
                "click",
                "--repeat",
                repeat,
                "--delay",
                "10",
                button_id,
            ]
        )

    def type(self, text: str, *, delay_ms: int = 1) -> dict[str, Any]:
        return self._run_xdotool(["type", "--delay", str(max(0, int(delay_ms))), str(text)], timeout=max(5.0, len(text) / 20))

    def keypress(self, key_combo: str) -> dict[str, Any]:
        normalized = self._normalize_key_combo(key_combo)
        if not normalized:
            return self._command_result(False, ["xdotool", "key"], reason="No key combination was provided.")
        return self._run_xdotool(["key", normalized])

    def wait(self, seconds: float = 0.2) -> dict[str, Any]:
        duration = max(0.0, float(seconds or 0))
        time.sleep(duration)
        return self._command_result(True, ["wait", str(duration)], data={"seconds": duration})

    def _run_xdotool(self, args: list[str], *, timeout: float = 5.0) -> dict[str, Any]:
        reason = self._ensure_started()
        if reason:
            return self._command_result(False, ["xdotool", *args], reason=reason)
        return self._run(["xdotool", *args], timeout=timeout)

    def _run(self, args: list[str], *, timeout: float = 5.0) -> dict[str, Any]:
        if not self._display:
            return self._command_result(False, args, reason="X11 virtual DISPLAY is not running.")
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=self._session_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._command_result(False, args, reason=str(exc))
        return self._command_result(
            completed.returncode == 0,
            args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _ensure_started(self) -> str:
        if self._is_running():
            return ""
        status = self.start()
        if status.get("running"):
            return ""
        return str(status.get("reason") or "X11 virtual session is unavailable.")

    def _is_running(self) -> bool:
        xvfb = self._processes.get("xvfb")
        return bool(self._display and xvfb is not None and xvfb.poll() is None)

    def _wait_for_display(self) -> bool:
        deadline = time.monotonic() + max(0.1, float(self.config.startup_timeout))
        while time.monotonic() < deadline:
            xvfb = self._processes.get("xvfb")
            if xvfb is None or xvfb.poll() is not None:
                return False
            probe = self._run(["xdotool", "getdisplaygeometry"], timeout=1.0)
            if probe.get("executed"):
                return True
            time.sleep(0.05)
        return False

    def _allocate_display_number(self) -> int | None:
        lock_root = Path(tempfile.gettempdir()) / "rumi-x11-virtual-displays"
        lock_root.mkdir(parents=True, exist_ok=True)
        for number in range(int(self.config.display_min), int(self.config.display_max) + 1):
            if self._display_socket_exists(number):
                continue
            lock_dir = lock_root / f"display-{number}.lock"
            try:
                lock_dir.mkdir()
            except FileExistsError:
                continue
            self._display_lock_dir = lock_dir
            return number
        return None

    @staticmethod
    def _display_socket_exists(number: int) -> bool:
        return (Path("/tmp/.X11-unix") / f"X{number}").exists()

    def _session_env(self) -> dict[str, str]:
        if not self._display:
            raise RuntimeError("Cannot build X11 virtual env before DISPLAY allocation.")
        env = dict(self._base_env)
        env["DISPLAY"] = self._display
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("MIR_SOCKET", None)
        env.pop("XAUTHORITY", None)
        env["RUMI_X11_VIRTUAL"] = "1"
        return env

    def _next_screenshot_path(self) -> Path:
        session_dir = self._session_dir or Path(tempfile.gettempdir())
        return session_dir / f"screenshot-{int(time.time() * 1000)}.png"

    def _status(
        self,
        *,
        available: bool,
        running: bool,
        reason: str = "",
        missing_commands: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "available": available,
            "running": running,
            "display": self._display or "",
            "display_number": self._display_number,
            "session_dir": str(self._session_dir or ""),
            "missing_commands": missing_commands if missing_commands is not None else self.missing_commands(),
            "reason": reason,
        }

    def _command_result(
        self,
        executed: bool,
        command: list[str],
        *,
        reason: str = "",
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "executed": executed,
            "display": self._display or "",
            "session_dir": str(self._session_dir or ""),
            "command": command,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        if reason:
            result["reason"] = reason
        if data:
            result.update(data)
        return result

    def _unavailable_screenshot(self, reason: str) -> dict[str, Any]:
        return {
            "path": "",
            "data_url": "",
            "coordinate_system": "screen_pixels",
            "method": "unavailable",
            "display": self._display or "",
            "session_dir": str(self._session_dir or ""),
            "error": reason,
        }

    @staticmethod
    def _button_id(button: str) -> str:
        return {"left": "1", "middle": "2", "center": "2", "right": "3"}.get(str(button or "left").lower(), "1")

    @staticmethod
    def _normalize_key_combo(key_combo: str) -> str:
        normalized = str(key_combo or "").replace("command", "ctrl").replace("cmd", "ctrl")
        return "+".join(part.strip() for part in normalized.split("+") if part.strip())

    @staticmethod
    def _terminate_process(proc: subprocess.Popen[Any]) -> None:
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2.0)
            except Exception:
                pass
