from __future__ import annotations

import subprocess
from pathlib import Path


def test_x11_virtual_missing_commands_are_gracefully_unavailable(monkeypatch) -> None:
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.linux import x11_virtual

    popen_calls: list[list[str]] = []

    monkeypatch.setattr(x11_virtual.sys, "platform", "linux")
    monkeypatch.setattr(x11_virtual.shutil, "which", lambda name: None)
    monkeypatch.setattr(x11_virtual.subprocess, "Popen", lambda args, **kwargs: popen_calls.append(args))

    session = x11_virtual.X11VirtualSession()
    status = session.start()

    assert session.is_available() is False
    assert status["available"] is False
    assert status["running"] is False
    assert status["missing_commands"] == ["Xvfb", "openbox", "xdotool", "import"]
    assert popen_calls == []


def test_x11_virtual_start_passes_owned_display_env_and_cleanup(monkeypatch, tmp_path: Path) -> None:
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.linux import x11_virtual

    popen_calls: list[dict[str, object]] = []
    run_calls: list[dict[str, object]] = []
    processes: list[FakeProcess] = []
    session_path = tmp_path / "session"

    def fake_popen(args, **kwargs):
        proc = FakeProcess()
        processes.append(proc)
        popen_calls.append({"args": list(args), "env": dict(kwargs["env"])})
        return proc

    def fake_run(args, **kwargs):
        run_calls.append({"args": list(args), "env": dict(kwargs["env"])})
        return subprocess.CompletedProcess(args, 0, stdout="1280 800\n", stderr="")

    def fake_mkdtemp(prefix: str):
        session_path.mkdir()
        return str(session_path)

    monkeypatch.setattr(x11_virtual.sys, "platform", "linux")
    monkeypatch.setattr(x11_virtual.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(x11_virtual.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(x11_virtual.subprocess, "run", fake_run)
    monkeypatch.setattr(x11_virtual.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(x11_virtual.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(x11_virtual.X11VirtualSession, "_display_socket_exists", staticmethod(lambda number: False))
    monkeypatch.setattr(x11_virtual.time, "sleep", lambda seconds: None)

    config = x11_virtual.X11VirtualSessionConfig(display_min=88, display_max=88)
    session = x11_virtual.X11VirtualSession(
        config,
        env={"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0", "XAUTHORITY": "/tmp/user-auth", "KEEP": "1"},
    )
    status = session.start()

    assert status["running"] is True
    assert session.display == ":88"
    assert [call["args"] for call in popen_calls] == [
        ["Xvfb", ":88", "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
        ["openbox"],
    ]
    assert run_calls[0]["args"] == ["xdotool", "getdisplaygeometry"]
    for call in [*popen_calls, *run_calls]:
        env = call["env"]
        assert env["DISPLAY"] == ":88"
        assert env["RUMI_X11_VIRTUAL"] == "1"
        assert env["KEEP"] == "1"
        assert "WAYLAND_DISPLAY" not in env
        assert "XAUTHORITY" not in env

    stop_status = session.stop()

    assert stop_status["running"] is False
    assert all(proc.terminated for proc in processes)
    assert not session_path.exists()
    assert not (tmp_path / "rumi-x11-virtual-displays" / "display-88.lock").exists()


def test_x11_virtual_actions_and_screenshot_use_virtual_display(monkeypatch, tmp_path: Path) -> None:
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.linux import x11_virtual

    run_calls: list[dict[str, object]] = []

    def fake_run(args, **kwargs):
        args = list(args)
        run_calls.append({"args": args, "env": dict(kwargs["env"])})
        if args[0] == "import":
            Path(args[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(x11_virtual.sys, "platform", "linux")
    monkeypatch.setattr(x11_virtual.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(x11_virtual.subprocess, "Popen", lambda args, **kwargs: FakeProcess())
    monkeypatch.setattr(x11_virtual.subprocess, "run", fake_run)
    monkeypatch.setattr(x11_virtual.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(x11_virtual.tempfile, "mkdtemp", lambda prefix: str(_mkdir(tmp_path / "session")))
    monkeypatch.setattr(x11_virtual.X11VirtualSession, "_display_socket_exists", staticmethod(lambda number: False))
    monkeypatch.setattr(x11_virtual.time, "sleep", lambda seconds: None)

    session = x11_virtual.X11VirtualSession(x11_virtual.X11VirtualSessionConfig(display_min=91, display_max=91))

    assert session.click(10, 20, button="right")["executed"] is True
    assert session.double_click(30, 40)["executed"] is True
    assert session.move(50, 60)["executed"] is True
    assert session.drag(1, 2, 3, 4)["executed"] is True
    assert session.scroll(7, 8, direction="up", clicks=2)["executed"] is True
    assert session.type("hello")["executed"] is True
    assert session.keypress("cmd+s")["executed"] is True

    screenshot_path = tmp_path / "shot.png"
    screenshot = session.screenshot(screenshot_path)

    commands = [call["args"] for call in run_calls]
    assert ["xdotool", "mousemove", "10", "20", "click", "3"] in commands
    assert ["xdotool", "mousemove", "30", "40", "click", "--repeat", "2", "--delay", "80", "1"] in commands
    assert ["xdotool", "mousemove", "50", "60"] in commands
    assert ["xdotool", "mousemove", "1", "2", "mousedown", "1", "mousemove", "--sync", "3", "4", "mouseup", "1"] in commands
    assert ["xdotool", "mousemove", "7", "8", "click", "--repeat", "2", "--delay", "10", "4"] in commands
    assert ["xdotool", "type", "--delay", "1", "hello"] in commands
    assert ["xdotool", "key", "ctrl+s"] in commands
    assert ["import", "-window", "root", str(screenshot_path)] in commands
    assert screenshot["method"] == "imagemagick_import_root"
    assert screenshot["data_url"].startswith("data:image/png;base64,")
    assert all(call["env"]["DISPLAY"] == ":91" for call in run_calls)


def test_linux_x11_virtual_driver_delegates_to_session(monkeypatch) -> None:
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers import linux_x11_virtual
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.linux_x11_virtual import (
        LinuxX11VirtualDriver,
    )
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget

    session = FakeSession()
    monkeypatch.setattr(linux_x11_virtual.sys, "platform", "linux")

    driver = LinuxX11VirtualDriver(session=session)
    target = ComputerTarget(kind="desktop", app="xterm")

    assert driver.is_available() is True
    assert driver.observe(target).screenshot["display"] == ":77"
    assert driver.click(target, x=1, y=2, button="right").executed is True
    assert driver.type_text(target, "abc").data["text_length"] == 3
    assert driver.key(target, "ctrl+l").data["key_combo"] == "ctrl+l"
    assert driver.scroll(target, x=3, y=4, direction="down", clicks=5).executed is True
    assert driver.move(target, x=6, y=7).uses_physical_input is False
    assert driver.drag(target, x1=1, y1=2, x2=3, y2=4).can_parallel_user_work is True
    assert driver.semantic_action(target, "press ok").executed is False
    assert session.calls == [
        ("screenshot",),
        ("click", 1, 2, "right"),
        ("type", "abc"),
        ("keypress", "ctrl+l"),
        ("scroll", 3, 4, "down", 5),
        ("move", 6, 7),
        ("drag", 1, 2, 3, 4),
    ]


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if not self.terminated and not self.killed else 0

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        return 0


class FakeSession:
    display = ":77"

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def is_available(self) -> bool:
        return True

    def screenshot(self):
        self.calls.append(("screenshot",))
        return {"display": self.display, "path": "/tmp/shot.png"}

    def click(self, x, y, button="left"):
        self.calls.append(("click", x, y, button))
        return {"executed": True, "display": self.display}

    def type(self, text):
        self.calls.append(("type", text))
        return {"executed": True, "display": self.display}

    def keypress(self, key_combo):
        self.calls.append(("keypress", key_combo))
        return {"executed": True, "display": self.display}

    def scroll(self, x=0, y=0, direction="down", clicks=3):
        self.calls.append(("scroll", x, y, direction, clicks))
        return {"executed": True, "display": self.display}

    def move(self, x, y):
        self.calls.append(("move", x, y))
        return {"executed": True, "display": self.display}

    def drag(self, x1, y1, x2, y2):
        self.calls.append(("drag", x1, y1, x2, y2))
        return {"executed": True, "display": self.display}


def _mkdir(path: Path) -> Path:
    path.mkdir()
    return path
