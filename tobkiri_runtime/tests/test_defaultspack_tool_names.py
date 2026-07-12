from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_tool_names_block_returns_only_names(monkeypatch):
    from blocks.tool import names
    from domain.tool import introspection

    fake_tools = [
        {"tool_id": "web_search", "summary": "Search web"},
        {"tool_id": "calculator", "summary": "Calculate"},
    ]

    class FakeRegistry:
        def list_tools(self, filter_dict=None):
            assert filter_dict is None
            return list(fake_tools)

    class FakeChecker:
        def __init__(self, registry=None):
            del registry

        def decide(self, tool_name, context=None, tool_def=None):
            del tool_name, context, tool_def
            return {"action": "ask"}

    monkeypatch.setattr(introspection, "ToolRegistry", lambda: FakeRegistry())
    monkeypatch.setattr(introspection, "PermissionChecker", FakeChecker)

    result = names.run({}, {})

    assert result["status"] == "ok"
    assert result["data"] == {
        "names": ["calculator", "web_search"],
        "tool_names": ["calculator", "web_search"],
        "count": 2,
    }


def test_tool_names_block_honors_runtime_profile_scope(monkeypatch):
    from blocks.tool import names
    from domain.tool import introspection

    fake_tools = [
        {"tool_id": "web_search", "summary": "Search web"},
        {"tool_id": "calculator", "summary": "Calculate"},
        {"tool_id": "coding_file_read", "summary": "Read files"},
    ]

    class FakeRegistry:
        def list_tools(self, filter_dict=None):
            assert filter_dict is None
            return list(fake_tools)

    class FakeChecker:
        def __init__(self, registry=None):
            del registry

        def decide(self, tool_name, context=None, tool_def=None):
            del tool_name, context, tool_def
            return {"action": "ask"}

    monkeypatch.setattr(introspection, "ToolRegistry", lambda: FakeRegistry())
    monkeypatch.setattr(introspection, "PermissionChecker", FakeChecker)

    result = names.run(
        {},
        {
            "runtime_profile": {
                "defaultspack": {
                    "agents": {
                        "only_search": {
                            "tools": ["web_search"],
                        }
                    }
                }
            },
            "agent_id": "only_search",
        },
    )

    assert result["status"] == "ok"
    assert result["data"] == {
        "names": ["web_search"],
        "tool_names": ["web_search"],
        "count": 1,
    }


def test_tool_names_block_hides_permission_denied_tools(monkeypatch):
    from blocks.tool import names
    from domain.tool import introspection

    fake_tools = [
        {"tool_id": "web_search", "summary": "Search web"},
        {"tool_id": "calculator", "summary": "Calculate"},
    ]

    class FakeRegistry:
        def list_tools(self, filter_dict=None):
            assert filter_dict is None
            return list(fake_tools)

    class FakeChecker:
        def __init__(self, registry=None):
            del registry

        def decide(self, tool_name, context=None, tool_def=None):
            del context, tool_def
            action = "deny" if tool_name == "calculator" else "ask"
            return {"action": action}

    monkeypatch.setattr(introspection, "ToolRegistry", lambda: FakeRegistry())
    monkeypatch.setattr(introspection, "PermissionChecker", FakeChecker)

    result = names.run({}, {})

    assert result["status"] == "ok"
    assert result["data"] == {
        "names": ["web_search"],
        "tool_names": ["web_search"],
        "count": 1,
    }


def test_tool_names_manifest_declares_always_loading():
    import json

    manifest = json.loads((DEFAULTSPACK_ROOT / "tools" / "tool_names" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["loading"] == "always"
    assert manifest["config"]["loading"] == "always"
    assert manifest["config"]["execution"]["handler"] == "domain.tool.introspection:tool_names"
