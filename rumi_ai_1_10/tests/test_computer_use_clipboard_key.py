from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_computer_key_normalizes_retrun_typo_on_macos():
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController()

    assert controller._apple_script("computer.key", {"key": "retrun"}) == 'tell application "System Events" to key code 36'


def test_computer_backspace_repeat_generates_repeated_key_code_on_macos():
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController()
    script = controller._apple_script("computer.key", {"key": "backspace", "count": 3})

    assert "repeat 3 times" in script
    assert 'key code 51' in script


def test_computer_clipboard_read_write_and_clear(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    writes: list[str] = []
    monkeypatch.setattr(BrowserComputerController, "_system_clipboard_read", staticmethod(lambda: "clip text"))
    monkeypatch.setattr(BrowserComputerController, "_system_clipboard_write", staticmethod(lambda content: writes.append(content)))

    controller = BrowserComputerController(artifact_root=tmp_path)

    read = controller.run("clipboard", {}, yolo_mode=True)
    full_read = controller.run("clipboard", {"include_content": True}, yolo_mode=True)
    write = controller.run("clipboard_write", {"content": "new text"}, yolo_mode=True)
    clear = controller.run("clipboard_clear", {}, yolo_mode=True)

    assert read["content_preview"] == "clip text"
    assert read["content_included"] is False
    assert "content" not in read
    assert full_read["content"] == "clip text"
    assert full_read["content_included"] is True
    assert write["written"] is True
    assert clear["cleared"] is True
    assert writes == ["new text", ""]


def test_computer_clipboard_read_requires_explicit_full_content_approval(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    monkeypatch.setattr(BrowserComputerController, "_system_clipboard_read", staticmethod(lambda: "secret-token-value"))

    controller = BrowserComputerController(artifact_root=tmp_path)

    preview_approval = controller.run("clipboard", {}, yolo_mode=False)
    full_approval = controller.run("clipboard", {"include_content": True}, yolo_mode=False)

    assert preview_approval["requires_approval"] is True
    assert preview_approval["payload"]["clipboard_access"] == "preview_only"
    assert "short preview" in preview_approval["approval_warning"]
    assert full_approval["payload"]["clipboard_access"] == "full_content"
    assert "full system clipboard text" in full_approval["approval_warning"]
