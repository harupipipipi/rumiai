from __future__ import annotations

import contextlib
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
RUMI_DEFAULT_TOOLS_ROOT = ROOT / "ecosystem" / "rumi_default_tools_pack"
RUMI_DEFAULT_TOOLS_FUNCTIONS = ROOT / "ecosystem" / "rumi_default_tools_pack" / "functions"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))


@contextmanager
def _default_tools_function_imports():
    sys.path.insert(0, str(RUMI_DEFAULT_TOOLS_FUNCTIONS))
    try:
        yield
    finally:
        for path in (str(RUMI_DEFAULT_TOOLS_FUNCTIONS), str(RUMI_DEFAULT_TOOLS_ROOT)):
            while path in sys.path:
                sys.path.remove(path)


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
        settings=EdgeHazeSettings(enabled=True),
    )

    assert manager.start(action="computer.click", payload={"x": 1, "y": 2}) is True
    manager.stop()

    assert events == ["compile", "start", "terminate", "wait:1"]


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
    lease = json.loads(Path(popen_envs[0]["RUMI_EDGE_HAZE_LEASE_PATH"]).read_text(encoding="utf-8"))
    assert 0 < lease["deadline_epoch"] - time.time() <= 6

    second.end_sequence("other_run")
    assert "terminate_pid:2468" not in events

    second.end_sequence("run_123")
    assert "terminate_pid:2468" in events


def test_edge_haze_standalone_active_lease_has_floor(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer.mac import edge_haze
    from ecosystem.rumi_default_tools_pack.domain.computer.mac.edge_haze import (
        ComputerUseEdgeHazeManager,
        EdgeHazeSettings,
    )

    source = tmp_path / "EdgeHaze.swift"
    source.write_text("print(\"haze\")\n", encoding="utf-8")
    binary = tmp_path / "helpers" / "edge_haze"

    class FakeProcess:
        pid = 9753

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

        def kill(self):
            pass

    def fake_run(args, capture_output=False, timeout=None, check=False):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("binary", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(edge_haze.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(edge_haze.shutil, "which", lambda name: "/usr/bin/swiftc" if name == "swiftc" else None)
    monkeypatch.setattr(edge_haze.subprocess, "run", fake_run)
    monkeypatch.setattr(edge_haze.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(ComputerUseEdgeHazeManager, "_pid_alive", staticmethod(lambda pid: pid == 9753))
    monkeypatch.setenv("RUMI_COMPUTER_USE_HAZE", "1")

    manager = ComputerUseEdgeHazeManager(
        pack_root=tmp_path,
        source_path=source,
        binary_path=binary,
        settings=EdgeHazeSettings(enabled=True, linger_seconds=1),
    )

    assert manager.start(action="computer.click", payload={}) is True

    lease = json.loads(manager._lease_path.read_text(encoding="utf-8"))
    remaining = lease["deadline_epoch"] - time.time()
    assert lease["sequence_id"] == "standalone"
    assert 25 <= remaining <= 31


def test_browser_computer_injects_haze_sequence_from_context_without_overwriting_payload():
    with _default_tools_function_imports():
        from browser_computer import main as browser_computer_main

        injected = browser_computer_main._payload_with_sequence_defaults({}, {"run_id": "run_abc"}, {})
        explicit = browser_computer_main._payload_with_sequence_defaults(
            {"computer_use_haze_sequence_id": "explicit"},
            {"run_id": "run_abc"},
            {},
        )

    assert injected["computer_use_haze_sequence_id"] == "run_abc"
    assert explicit["computer_use_haze_sequence_id"] == "explicit"


def test_browser_computer_run_passes_context_sequence_to_controller(monkeypatch):
    with _default_tools_function_imports():
        from browser_computer import main as browser_computer_main
        from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

        captured: dict[str, object] = {}

        def fake_controller_run(self, action, payload, *, yolo_mode=False):
            captured["action"] = action
            captured["payload"] = payload
            return {"action": action}

        monkeypatch.setattr(BrowserComputerController, "run", fake_controller_run)
        monkeypatch.setenv("RUMI_COMPUTER_HOST_INTERNAL", "1")

        browser_computer_main.run({"request_id": "req_ctx"}, {"action": "computer.type", "payload": {"text": "hi"}})

    assert captured["action"] == "computer.type"
    assert captured["payload"]["computer_use_haze_sequence_id"] == "req_ctx"


def test_browser_use_and_computer_use_preserve_sequence_payload(monkeypatch):
    with _default_tools_function_imports():
        from browser_use import main as browser_use_main
        from computer_use import main as computer_use_main

        captured: list[dict[str, object]] = []

        def fake_run_browser_computer(context, args):
            captured.append(args)
            return {"status": "ok"}

        monkeypatch.setattr(browser_use_main, "_run_browser_computer", fake_run_browser_computer)
        monkeypatch.setattr(computer_use_main, "_run_browser_computer", fake_run_browser_computer)

        browser_use_main.run(
            {"request_id": "ctx_request"},
            {"action": "click", "run_id": "run_from_browser", "x": 1, "y": 2},
        )
        computer_use_main.run(
            {"request_id": "ctx_request"},
            {"action": "type", "request_id": "req_from_computer", "text": "hi"},
        )

    assert captured[0]["payload"]["run_id"] == "run_from_browser"
    assert captured[1]["payload"]["request_id"] == "req_from_computer"


def test_edge_haze_swift_helper_watches_lease():
    source = ROOT / "ecosystem" / "rumi_default_tools_pack" / "domain" / "computer" / "mac" / "EdgeHaze.swift"
    text = source.read_text(encoding="utf-8")
    assert "RUMI_EDGE_HAZE_LEASE_PATH" in text
    assert "deadline_epoch" in text
    assert "app.terminate(nil)" in text


def test_browser_computer_wraps_visible_desktop_actions_with_haze(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool import browser_computer
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    events: list[str] = []

    @contextlib.contextmanager
    def fake_haze(self, action, payload):
        events.append(f"enter:{action}")
        try:
            yield {"attempted": True, "started": True, "action": action, "sequence_id": "seq-test"}
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
    assert result["edge_haze"] == {
        "attempted": True,
        "started": True,
        "action": "computer.type",
        "sequence_id": "seq-test",
    }
    assert events == ["enter:computer.type", "exit:computer.type", "enter:computer.type", "exit:computer.type"]


def test_browser_computer_wraps_foreground_open_url_with_haze(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    events: list[str] = []

    @contextlib.contextmanager
    def fake_haze(self, action, payload):
        events.append(f"enter:{action}")
        try:
            yield {"attempted": True, "started": True, "action": action, "sequence_id": "seq-test"}
        finally:
            events.append(f"exit:{action}")

    monkeypatch.setattr(BrowserComputerController, "_edge_haze", fake_haze)
    monkeypatch.setattr(BrowserComputerController, "_open_url_foreground", staticmethod(lambda url, app_name="": True))

    result = BrowserComputerController(artifact_root=tmp_path).run(
        "browser.open_url",
        {"url": "https://example.test", "app": "Google Chrome"},
        yolo_mode=True,
    )

    assert result["opened"] is True
    assert result["edge_haze"] == {
        "attempted": True,
        "started": True,
        "action": "browser.open_url",
        "sequence_id": "seq-test",
    }
    assert events == ["enter:browser.open_url", "exit:browser.open_url"]


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
