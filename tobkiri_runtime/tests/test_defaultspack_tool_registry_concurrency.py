from __future__ import annotations

import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_concurrent_registry_reader_waits_for_initial_tool_load(monkeypatch):
    from domain.tool.registry import ToolRegistry

    load_started = threading.Event()
    release_load = threading.Event()
    second_returned = threading.Event()
    registries = []
    second_tools = []

    def blocking_pack_load(registry):
        load_started.set()
        assert release_load.wait(timeout=5)
        registry.register(
            {
                "tool_id": "sheet_read",
                "name": "sheet_read",
                "summary": "Read a generated sheet",
                "schema": {"type": "object", "properties": {}},
                "execution": {"type": "local"},
            }
        )
        return 1

    monkeypatch.setattr(ToolRegistry, "_load_pack_tools", blocking_pack_load)
    monkeypatch.setattr(ToolRegistry, "_load_dynamic_tools", lambda _registry: 0)
    ToolRegistry._instance = None

    first = threading.Thread(target=lambda: registries.append(ToolRegistry()))

    def read_from_second_thread():
        registry = ToolRegistry()
        registries.append(registry)
        second_tools.extend(tool["tool_id"] for tool in registry.list_tools())
        second_returned.set()

    second = threading.Thread(target=read_from_second_thread)
    first.start()
    assert load_started.wait(timeout=5)
    second.start()

    try:
        assert not second_returned.wait(timeout=0.2)
    finally:
        release_load.set()
        first.join(timeout=5)
        second.join(timeout=5)
        ToolRegistry._instance = None

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(registries) == 2
    assert registries[0] is registries[1]
    assert second_tools == ["sheet_read"]
