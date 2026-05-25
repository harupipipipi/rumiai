from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_edge_haze_manager_noops_off_macos(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac import edge_haze
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    monkeypatch.setattr(edge_haze.platform, "system", lambda: "Linux")
    manager = ComputerUseEdgeHazeManager(
        pack_root=tmp_path,
        source_path=tmp_path / "EdgeHaze.swift",
        binary_path=tmp_path / "edge_haze",
        settings=EdgeHazeSettings(enabled=True),
    )

    assert manager.start(action="computer.click", payload={"x": 1, "y": 2}) is False


def test_edge_haze_manager_compiles_starts_and_stops_on_macos(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac import edge_haze
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    source = tmp_path / "EdgeHaze.swift"
    source.write_text("print(\"haze\")\n", encoding="utf-8")
    binary = tmp_path / "helpers" / "edge_haze"
    events: list[str] = []

    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

        def terminate(self):
            events.append("terminate")

        def wait(self, timeout=None):
            events.append(f"wait:{timeout}")

        def kill(self):
            events.append("kill")

    def fake_run(args, capture_output=False, timeout=None, check=False):
        events.append("compile")
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("binary", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    def fake_popen(args, **kwargs):
        events.append("start")
        return FakeProcess()

    monkeypatch.setattr(edge_haze.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(edge_haze.shutil, "which", lambda name: "/usr/bin/swiftc" if name == "swiftc" else None)
    monkeypatch.setattr(edge_haze.subprocess, "run", fake_run)
    monkeypatch.setattr(edge_haze.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("RUMI_COMPUTER_USE_HAZE", "1")

    manager = ComputerUseEdgeHazeManager(
        pack_root=tmp_path,
        source_path=source,
        binary_path=binary,
        settings=EdgeHazeSettings(enabled=True, linger_seconds=0),
    )

    assert manager.start(action="computer.click", payload={"x": 1, "y": 2}) is True
    manager.stop()

    assert events == ["compile", "start", "terminate", "wait:1"]


def test_edge_haze_manager_uses_existing_binary_without_swiftc(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac import edge_haze
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    source = tmp_path / "EdgeHaze.swift"
    source.write_text("print(\"haze\")\n", encoding="utf-8")
    binary = tmp_path / "helpers" / "edge_haze"
    binary.parent.mkdir(parents=True)
    binary.write_text("binary", encoding="utf-8")
    binary.chmod(0o755)
    events: list[str] = []

    class FakeProcess:
        pid = 1357

        def poll(self):
            return None

    def fake_popen(args, **kwargs):
        events.append(f"start:{args[0]}")
        return FakeProcess()

    monkeypatch.setattr(edge_haze.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(edge_haze.shutil, "which", lambda name: None)
    monkeypatch.setattr(edge_haze.subprocess, "run", lambda *args, **kwargs: events.append("compile"))
    monkeypatch.setattr(edge_haze.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("RUMI_COMPUTER_USE_HAZE", "1")

    manager = ComputerUseEdgeHazeManager(
        pack_root=tmp_path,
        source_path=source,
        binary_path=binary,
        settings=EdgeHazeSettings(enabled=True),
    )

    assert manager.start(action="computer.click", payload={"x": 1, "y": 2}) is True
    assert events == [f"start:{binary}"]


def test_edge_haze_manager_uses_bundled_binary_with_writable_lease(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac import edge_haze
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    app_root = tmp_path / "app"
    pack_root = app_root / "ecosystem" / "rumi_default_tools_pack"
    bundled = app_root / "bundled" / "helpers" / "edge_haze" / "edge_haze"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("binary", encoding="utf-8")
    bundled.chmod(0o755)
    user_data = tmp_path / "user_data"
    popen_args: list[list[str]] = []
    popen_envs: list[dict[str, str]] = []

    class FakeProcess:
        pid = 9753

        def poll(self):
            return None

    def fake_popen(args, **kwargs):
        popen_args.append(list(args))
        popen_envs.append(dict(kwargs.get("env") or {}))
        return FakeProcess()

    monkeypatch.setattr(edge_haze.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(edge_haze.shutil, "which", lambda name: None)
    monkeypatch.setattr(edge_haze.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("RUMI_COMPUTER_USE_HAZE", "1")
    monkeypatch.setenv("RUMI_USER_DATA", str(user_data))

    manager = ComputerUseEdgeHazeManager(
        pack_root=pack_root,
        source_path=tmp_path / "missing.swift",
        settings=EdgeHazeSettings(enabled=True),
    )

    assert manager.start(action="computer.click", payload={"x": 1, "y": 2}) is True
    assert popen_args == [[str(bundled)]]
    lease_path = Path(popen_envs[0]["RUMI_EDGE_HAZE_LEASE_PATH"])
    assert lease_path == user_data / "shared" / "helpers" / "edge_haze" / "edge_haze.lease.json"
    assert lease_path.exists()


def test_edge_haze_manager_prefers_env_binary(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac import edge_haze
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    override = tmp_path / "override_edge_haze"
    override.write_text("binary", encoding="utf-8")
    override.chmod(0o755)
    popen_args: list[list[str]] = []

    class FakeProcess:
        pid = 24601

        def poll(self):
            return None

    def fake_popen(args, **kwargs):
        popen_args.append(list(args))
        return FakeProcess()

    monkeypatch.setattr(edge_haze.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(edge_haze.shutil, "which", lambda name: None)
    monkeypatch.setattr(edge_haze.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("RUMI_COMPUTER_USE_HAZE", "1")
    monkeypatch.setenv("RUMI_EDGE_HAZE_BINARY", str(override))

    manager = ComputerUseEdgeHazeManager(
        pack_root=tmp_path / "pack",
        source_path=tmp_path / "missing.swift",
        settings=EdgeHazeSettings(enabled=True),
    )

    assert manager.start(action="computer.click", payload={"x": 1, "y": 2}) is True
    assert popen_args == [[str(override)]]


def test_edge_haze_reuses_process_for_same_sequence_until_sequence_ends(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac import edge_haze
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    source = tmp_path / "EdgeHaze.swift"
    source.write_text("print(\"haze\")\n", encoding="utf-8")
    binary = tmp_path / "helpers" / "edge_haze"
    events: list[str] = []
    popen_envs: list[dict[str, str]] = []

    class FakeProcess:
        pid = 2468

        def poll(self):
            return None

        def terminate(self):
            events.append("terminate")

        def wait(self, timeout=None):
            events.append(f"wait:{timeout}")

        def kill(self):
            events.append("kill")

    def fake_run(args, capture_output=False, timeout=None, check=False):
        events.append("compile")
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("binary", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    def fake_popen(args, **kwargs):
        events.append("start")
        popen_envs.append(dict(kwargs.get("env") or {}))
        return FakeProcess()

    monkeypatch.setattr(edge_haze.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(edge_haze.shutil, "which", lambda name: "/usr/bin/swiftc" if name == "swiftc" else None)
    monkeypatch.setattr(edge_haze.subprocess, "run", fake_run)
    monkeypatch.setattr(edge_haze.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ComputerUseEdgeHazeManager, "_pid_alive", staticmethod(lambda pid: pid == 2468))
    monkeypatch.setattr(
        ComputerUseEdgeHazeManager,
        "_terminate_pid",
        classmethod(lambda cls, pid: events.append(f"terminate_pid:{pid}")),
    )
    monkeypatch.setenv("RUMI_COMPUTER_USE_HAZE", "1")

    first = ComputerUseEdgeHazeManager(
        pack_root=tmp_path,
        source_path=source,
        binary_path=binary,
        settings=EdgeHazeSettings(enabled=True, linger_seconds=5),
    )
    second = ComputerUseEdgeHazeManager(
        pack_root=tmp_path,
        source_path=source,
        binary_path=binary,
        settings=EdgeHazeSettings(enabled=True, linger_seconds=5),
    )

    payload = {"computer_use_haze_sequence_id": "run_123"}
    assert first.start(action="computer.type", payload=payload) is True
    first.stop()
    assert second.start(action="computer.key", payload=payload) is True
    second.stop()
    assert events.count("start") == 1
    assert "terminate_pid:2468" not in events
    assert popen_envs[0]["RUMI_EDGE_HAZE_SEQUENCE_ID"] == "run_123"
    assert popen_envs[0]["RUMI_EDGE_HAZE_LEASE_PATH"].endswith("edge_haze.lease.json")
    lease = json.loads(Path(popen_envs[0]["RUMI_EDGE_HAZE_LEASE_PATH"]).read_text(encoding="utf-8"))
    assert lease["deadline_epoch"] - time.time() > 60

    second.end_sequence("other_run")
    assert "terminate_pid:2468" not in events

    second.end_sequence("run_123")
    assert "terminate_pid:2468" in events


def test_edge_haze_sequence_inactive_deadline_uses_linger(tmp_path):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    manager = ComputerUseEdgeHazeManager(
        pack_root=tmp_path,
        source_path=tmp_path / "EdgeHaze.swift",
        binary_path=tmp_path / "edge_haze",
        settings=EdgeHazeSettings(enabled=True, linger_seconds=4),
    )
    manager._sequence_id = "run_123"

    assert manager._deadline_seconds(active=True) > 60
    assert manager._deadline_seconds(active=False) == 4


def test_browser_computer_wraps_visible_desktop_actions_with_haze(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    events: list[str] = []

    @contextlib.contextmanager
    def fake_haze(self, action, payload):
        events.append(f"enter:{action}")
        try:
            yield
        finally:
            events.append(f"exit:{action}")

    monkeypatch.setattr(browser_computer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "_edge_haze", fake_haze)
    monkeypatch.setattr(BrowserComputerController, "_try_computer_seat_action", lambda self, action, payload: None)
    monkeypatch.setattr(BrowserComputerController, "_darwin_type", lambda self, payload: None)

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "computer.type",
        {"text": "hi", "include_screenshot": False},
        yolo_mode=True,
    )

    assert result["executed"] is True
    assert events == ["enter:computer.type", "exit:computer.type", "enter:computer.type", "exit:computer.type"]


def test_browser_computer_does_not_wrap_screenshot_with_haze(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    def fail_haze(self, action, payload):
        raise AssertionError("screenshot should not start haze")

    monkeypatch.setattr(BrowserComputerController, "_edge_haze", fail_haze)

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "computer.screenshot",
        {"dry_run": True},
        yolo_mode=True,
    )

    assert result["action"] == "computer.screenshot"


def test_edge_haze_swift_helper_watches_lease_file():
    source = (
        ROOT
        / "ecosystem"
        / "rumi_default_tools_pack"
        / "domain"
        / "computer"
        / "mac"
        / "EdgeHaze.swift"
    ).read_text(encoding="utf-8")

    assert "RUMI_EDGE_HAZE_LEASE_PATH" in source
    assert "RUMI_EDGE_HAZE_SEQUENCE_ID" in source
    assert "deadline_epoch" in source
    assert "leaseIsCurrent()" in source


def test_stream_engine_ends_haze_sequence_by_run_id(monkeypatch):
    from domain.chat import stream_engine
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import ComputerUseEdgeHazeManager

    calls: list[tuple[str, str]] = []

    class FakeManager:
        def __init__(self, root):
            self.root = root

        def end_sequence(self, sequence_id):
            calls.append((str(self.root), sequence_id))

    monkeypatch.setattr(ComputerUseEdgeHazeManager, "from_pack_root", classmethod(lambda cls, root: FakeManager(root)))

    stream_engine._end_computer_use_haze_sequence("run_haze_1")

    assert calls
    assert calls[0][0].endswith("ecosystem/rumi_default_tools_pack")
    assert calls[0][1] == "run_haze_1"
