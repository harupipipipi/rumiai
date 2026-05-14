from __future__ import annotations

import builtins
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_virtual_pointer_moves_without_physical_cursor():
    from ecosystem.rumi_default_tools_pack.domain.computer.virtual_pointer import VirtualPointer

    pointer = VirtualPointer({"x": 3, "y": 4})
    move = pointer.move(10.2, 20.8, source="test")
    click = pointer.click()
    drag = pointer.drag(1, 2, 30, 40)

    assert move["virtual_cursor"] is True
    assert move["target"] == {"x": 10, "y": 21}
    assert click["target"] == {"x": 10, "y": 21}
    assert drag["target"] == {"from": {"x": 1, "y": 2}, "to": {"x": 30, "y": 40}}
    assert pointer.position()["metadata"]["source"] == "test"


def test_render_overlay_is_import_safe_without_pillow(tmp_path, monkeypatch):
    from ecosystem.rumi_default_tools_pack.domain.computer import render_overlay

    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    source.write_bytes(b"not a real png")
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("Pillow intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = render_overlay.render_cursor_overlay(source, output, {"x": 1, "y": 2})

    assert result["rendered"] is False
    assert result["reason"] == "pillow_unavailable"
    assert output.exists()
