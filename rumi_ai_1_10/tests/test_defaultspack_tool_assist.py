from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_tool_recommender_prefers_related_tools():
    from domain.chat.tool_recommender import recommend_tool_ids

    tools = [
        {
            "tool_id": "web_search",
            "name": "Web Search",
            "summary": "Search the web for current weather and news.",
            "tags": ["search", "web"],
        },
        {
            "tool_id": "coding_file_write",
            "name": "Write File",
            "summary": "Write files in the workspace.",
            "tags": ["coding", "write"],
        },
    ]

    assert recommend_tool_ids("webで今日のweatherを検索して", tools, limit=2) == ["web_search"]


def test_tool_recommender_uses_mcp_metadata_and_input_schema():
    from domain.chat.tool_recommender import recommend_tool_ids

    tools = [
        {
            "tool_id": "mcp__filesystem__read_file",
            "name": "mcp_fs_read_file",
            "summary": "",
            "tags": ["mcp"],
            "schema": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"description": "workspace file path to read"},
                    },
                }
            },
            "metadata": {
                "source": "mcp",
                "server_id": "filesystem",
                "server_name": "filesystem",
                "mcp_tool_name": "read_file",
                "description": "Read files from the workspace through MCP.",
            },
        },
        {"tool_id": "calculator", "summary": "Compute arithmetic.", "tags": ["math"]},
    ]

    assert recommend_tool_ids("MCP filesystemでworkspaceのfileをreadして", tools, limit=2) == [
        "mcp__filesystem__read_file"
    ]


def test_tool_recommender_uses_skill_metadata():
    from domain.chat.tool_recommender import recommend_tool_ids

    tools = [
        {
            "tool_id": "hatch_pet_tool",
            "name": "Pet Builder",
            "summary": "Create animated pets.",
            "skills": ["hatch-pet"],
            "metadata": {"skills": ["spritesheet", "pet animation"]},
            "ui": {"keywords": "hatch pet sprite atlas"},
        },
        {"tool_id": "web_search", "summary": "Search web pages.", "tags": ["web"]},
    ]

    assert recommend_tool_ids("hatch-pet skillでsprite atlasを作って", tools, limit=2) == [
        "hatch_pet_tool"
    ]


def test_run_request_auto_tool_assist_recommends_when_tools_are_not_selected(monkeypatch):
    from domain.chat import run_request

    fake_tools = [
        {
            "tool_id": "web_search",
            "name": "Web Search",
            "summary": "Search web pages and recent weather.",
            "tags": ["web", "search"],
        },
        {
            "tool_id": "calculator",
            "name": "Calculator",
            "summary": "Compute arithmetic.",
            "tags": ["math"],
        },
    ]

    class FakeRegistry:
        def list_tools(self):
            return list(fake_tools)

        def get(self, tool_id):
            return next((tool for tool in fake_tools if tool["tool_id"] == tool_id), None)

    monkeypatch.setattr(run_request, "ToolRegistry", lambda: FakeRegistry())
    monkeypatch.setattr(run_request, "effective_tool_assist_mode", lambda **_kwargs: "auto")
    monkeypatch.setattr(run_request, "tool_assist_limit", lambda **_kwargs: 4)

    resolved, unknown = run_request._resolve_selected_tools(
        None,
        user_text="今日のweatherをwebで検索して",
        context={},
    )

    assert unknown == []
    assert [tool["tool_id"] for tool in resolved] == ["web_search"]


def test_run_request_tool_assist_off_keeps_unselected_tools_empty(monkeypatch):
    from domain.chat import run_request

    class FakeRegistry:
        def list_tools(self):
            return [{"tool_id": "web_search", "summary": "Search the web"}]

    monkeypatch.setattr(run_request, "ToolRegistry", lambda: FakeRegistry())
    monkeypatch.setattr(run_request, "effective_tool_assist_mode", lambda **_kwargs: "off")

    resolved, unknown = run_request._resolve_selected_tools(None, user_text="search", context={})

    assert resolved == []
    assert unknown == []
