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


def test_tool_recommender_expands_japanese_coding_file_terms():
    from domain.chat.tool_recommender import recommend_tool_ids

    tools = [
        {
            "tool_id": "coding_file_patch",
            "name": "Patch File",
            "summary": "Patch and edit a workspace source file.",
            "tags": ["coding", "file", "patch"],
        },
        {"tool_id": "web_search", "summary": "Search web pages.", "tags": ["web"]},
    ]

    assert recommend_tool_ids("コードを編集してファイルを修正", tools, limit=2)[0] == "coding_file_patch"


def test_tool_search_returns_overview_and_schema_from_docs(tmp_path):
    from domain.chat.tool_recommender import search_tools

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("Use this tool for parquet schema extraction and dataset docs.", encoding="utf-8")
    tools = [
        {
            "tool_id": "dataset_schema",
            "name": "Dataset Schema",
            "summary": "",
            "tags": [],
            "schema": {"parameters": {"type": "object", "properties": {"path": {"description": "dataset path"}}}},
            "metadata": {"manifest_path": str(manifest)},
        }
    ]

    overview = search_tools("parquet docs", tools, include_schema=False)
    schema = search_tools("parquet docs", tools, include_schema=True)

    assert overview[0]["tool_id"] == "dataset_schema"
    assert overview[0]["usage"]["phase"] == "overview"
    assert "schema" not in overview[0]
    assert schema[0]["schema"]["parameters"]["properties"]["path"]["description"] == "dataset path"


def test_effective_tool_assist_defaults_to_all_and_maps_legacy_auto_to_vector():
    from domain.chat.tool_recommender import effective_tool_assist_mode

    assert effective_tool_assist_mode({}) == "all"
    assert effective_tool_assist_mode({"tools": {"tool_assist_mode": "auto"}}) == "vector"
    assert effective_tool_assist_mode({"tools": {"tool_assist_mode": "vector"}}) == "vector"


def test_run_request_all_tool_assist_exposes_every_tool_when_tools_are_not_selected(monkeypatch):
    from domain.chat import run_request

    fake_tools = [
        {"tool_id": "web_search", "summary": "Search web pages."},
        {"tool_id": "calculator", "summary": "Compute arithmetic."},
    ]

    class FakeRegistry:
        def list_tools(self):
            return list(fake_tools)

        def get(self, tool_id):
            return next((tool for tool in fake_tools if tool["tool_id"] == tool_id), None)

    monkeypatch.setattr(run_request, "ToolRegistry", lambda: FakeRegistry())
    monkeypatch.setattr(run_request, "effective_tool_assist_mode", lambda **_kwargs: "all")

    resolved, unknown = run_request._resolve_selected_tools(None, user_text="anything", context={})

    assert unknown == []
    assert [tool["tool_id"] for tool in resolved] == ["web_search", "calculator"]


def test_run_request_vector_tool_assist_recommends_when_tools_are_not_selected(monkeypatch):
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
    monkeypatch.setattr(run_request, "effective_tool_assist_mode", lambda **_kwargs: "vector")
    monkeypatch.setattr(run_request, "tool_assist_limit", lambda **_kwargs: 4)

    context = {}
    resolved, unknown = run_request._resolve_selected_tools(
        None,
        user_text="今日のweatherをwebで検索して",
        context=context,
    )

    assert unknown == []
    assert [tool["tool_id"] for tool in resolved] == ["web_search"]
    assert context["tool_assist"]["mode"] == "vector"


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


def test_run_request_explicit_empty_selected_tools_blocks_inferred_computer_tools():
    from domain.chat import run_request

    updated = run_request._with_inferred_tools(
        {
            "tools": [],
            "params": {"tool_policy": {"selected_tools": []}},
            "message": {"metadata": {"selected_tools": []}},
        },
        ["computer_use", "browser_computer"],
    )

    assert updated["tools"] == []


def test_run_request_metadata_selected_tools_disables_auto_recommendation(monkeypatch):
    from domain.chat import run_request

    captured = {}

    def fake_resolve(raw_tools, **_kwargs):
        captured["raw_tools"] = raw_tools
        return [], []

    monkeypatch.setattr(run_request, "_resolve_selected_tools", fake_resolve)
    monkeypatch.setattr(run_request, "resolve_runtime_profile_context", lambda context: context or {})
    monkeypatch.setattr(run_request, "filter_tool_definitions_for_runtime_profile", lambda tools, *_args, **_kwargs: tools)
    monkeypatch.setattr(run_request, "adapt_tool_definitions", lambda tools: tools)

    run_request._available_tools(
        {},
        {"message": {"metadata": {"selected_tools": []}}},
        user_text="search the web",
    )

    assert captured["raw_tools"] == []


def test_run_request_selected_shell_tool_respects_profile_policy_yolo():
    from domain.chat import run_request

    raw_tools, provider_tools, _tool_context = run_request._available_tools(
        {
            "profile_policy": {
                "yolo_mode": True,
                "allow_shell": True,
                "allow_file_write": True,
                "write_actions_require_approval": False,
            }
        },
        {
            "tools": ["coding_terminal_exec"],
            "params": {
                "tool_policy": {
                    "selected_tools": ["coding_terminal_exec"],
                    "yolo_mode": True,
                    "allow_shell": True,
                    "allow_file_write": True,
                    "write_actions_require_approval": False,
                }
            },
        },
        user_text="run coding_terminal_exec",
    )

    assert [tool["tool_id"] for tool in raw_tools] == ["coding_terminal_exec"]
    assert provider_tools[0]["function"]["name"] == "coding_terminal_exec"


def test_prepare_chat_run_promotes_tool_policy_tool_choice(tmp_path, monkeypatch):
    from domain.chat.run_request import prepare_chat_run
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")

    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "use the calculator"},
            "tools": [],
            "params": {"tool_policy": {"selected_tools": [], "tool_choice": "required"}},
        },
        {},
    )

    assert prepared.params["tool_choice"] == "required"
    ChatStore._instance = None


def test_assistant_tool_history_preserves_reasoning_content():
    from blocks.chat.send import _append_assistant_tool_use_message

    messages = []

    _append_assistant_tool_use_message(
        messages,
        [
            {
                "type": "tool_use",
                "id": "call_exec",
                "name": "coding_terminal_exec",
                "input": {"command": "echo ok"},
            }
        ],
        reasoning_content="I need the terminal result.",
    )

    assert messages == [
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "I need the terminal result.",
            "tool_calls": [
                {
                    "id": "call_exec",
                    "type": "function",
                    "function": {
                        "name": "coding_terminal_exec",
                        "arguments": "{\"command\": \"echo ok\"}",
                    },
                }
            ],
        }
    ]


def test_coding_tools_get_larger_default_tool_limit():
    from domain.chat.stream_engine import _default_tool_limit_for_connected_tools

    assert _default_tool_limit_for_connected_tools(4, {"coding_terminal_exec"}) == 12
    assert _default_tool_limit_for_connected_tools(4, {"coding_file_write"}) == 12
    assert _default_tool_limit_for_connected_tools(4, {"calculator"}) == 4
    assert _default_tool_limit_for_connected_tools(2, {"coding_terminal_exec"}) == 2
