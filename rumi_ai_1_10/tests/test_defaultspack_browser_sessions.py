from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


class FakeCdpClient:
    def __init__(self):
        self.calls = []
        self.tabs = [{"id": "tab-1", "type": "page", "url": "about:blank", "title": "Blank"}]

    def version(self):
        self.calls.append(("version",))
        return {"Browser": "MockChrome/1.0"}

    def list_tabs(self):
        self.calls.append(("list_tabs",))
        return list(self.tabs)

    def new_tab(self, url):
        self.calls.append(("new_tab", url))
        tab = {"id": "tab-2", "type": "page", "url": url, "title": "Example"}
        self.tabs.append(tab)
        return {"ok": True, "tab": tab}

    def activate_tab(self, tab_id):
        self.calls.append(("activate_tab", tab_id))
        return {"ok": True}

    def close_tab(self, tab_id):
        self.calls.append(("close_tab", tab_id))
        return {"ok": True}

    def navigate(self, tab_id, url):
        self.calls.append(("navigate", tab_id, url))
        return {"ok": True, "frame_id": "frame-1"}

    def snapshot(self, tab_id):
        self.calls.append(("snapshot", tab_id))
        return {
            "ok": True,
            "snapshot": {
                "url": "https://example.test",
                "title": "Example",
                "elements": [
                    {
                        "role": "button",
                        "name": "Continue",
                        "text": "Continue",
                        "selector": "#continue",
                        "interactive": True,
                        "bounds": {"x": 10, "y": 20, "width": 100, "height": 30},
                    }
                ],
            },
        }

    def screenshot(self, tab_id, format="png", quality=None):
        self.calls.append(("screenshot", tab_id, format, quality))
        return {"ok": True, "data": PNG_1X1, "mime_type": "image/png"}


class FakeProcess:
    def __init__(self):
        self.pid = 4321
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_browser_session_manager_supports_mock_cdp_tabs_snapshots_and_artifacts(tmp_path):
    from domain.browser.sessions import BrowserSessionManager

    fake = FakeCdpClient()
    manager = BrowserSessionManager(tmp_path, cdp_client_factory=lambda record: fake)
    session = manager.start_session(session_id="qa", profile_id="QA", launch=False)

    assert session["id"] == "qa"
    assert session["state"] == "running"
    assert session["managed"] is False

    health = manager.health("qa")
    assert health["ok"] is True
    assert health["version"]["Browser"] == "MockChrome/1.0"
    assert health["tabs"][0]["id"] == "tab-1"

    opened = manager.open_tab(session_id="qa", url="https://example.test")
    assert opened["ok"] is True
    assert opened["tab"]["url"] == "https://example.test"

    navigated = manager.navigate_tab(session_id="qa", tab_id="tab-2", url="https://example.test/next")
    assert navigated["ok"] is True
    assert ("navigate", "tab-2", "https://example.test/next") in fake.calls

    snapshot = manager.snapshot_tab(session_id="qa", tab_id="tab-2")
    assert snapshot["ok"] is True
    assert snapshot["snapshot"]["ref_count"] == 1
    assert snapshot["snapshot"]["refs"][0]["role"] == "button"

    screenshot = manager.screenshot_tab(session_id="qa", tab_id="tab-2")
    assert screenshot["ok"] is True
    assert Path(screenshot["artifact"]["path"]).is_file()


def test_browser_session_manager_start_stop_restart_with_fake_process(tmp_path):
    from domain.browser.sessions import BrowserSessionManager

    fake_browser = tmp_path / "chrome"
    fake_browser.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_browser.chmod(0o755)
    processes = []

    def process_factory(command, **kwargs):
        process = FakeProcess()
        process.command = command
        processes.append(process)
        return process

    manager = BrowserSessionManager(
        tmp_path,
        cdp_client_factory=lambda record: FakeCdpClient(),
        process_factory=process_factory,
        browser_executable=fake_browser,
    )
    started = manager.start_session(session_id="managed", profile_id="Managed", launch=True)
    stopped = manager.stop_session("managed")
    restarted = manager.restart_session("managed")

    assert started["pid"] == 4321
    assert "--remote-debugging-port=" in " ".join(started["command"])
    assert stopped["state"] == "stopped"
    assert processes[0].terminated is True
    assert restarted["state"] == "running"
    assert len(processes) == 2
