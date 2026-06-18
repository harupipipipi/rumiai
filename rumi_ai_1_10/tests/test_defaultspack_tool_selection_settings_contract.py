from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _tools():
    return [
        {
            "tool_id": "web_search",
            "name": "Web Search",
            "summary": "Search the web.",
            "tags": ["web", "search"],
            "action_class": "search",
        },
        {
            "tool_id": "github_issue_search",
            "name": "GitHub Issues",
            "summary": "Search GitHub issues and pull requests.",
            "tags": ["github", "issue"],
            "action_class": "search",
            "metadata": {"service_id": "github"},
            "schema": {
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                }
            },
        },
        {
            "tool_id": "coding_file_read",
            "name": "Read File",
            "summary": "Read a workspace file.",
            "tags": ["coding", "file"],
            "action_class": "read",
        },
    ]


def test_all_schemas_exposes_every_schema_without_recommendations():
    from domain.chat.tool_selection_schema import ToolSelectionRequest
    from domain.chat.tool_selection_service import ToolSelectionService

    decision = ToolSelectionService(settings={"tools": {"selection_strategy": "all_schemas"}}).select(
        "show me the project state",
        _tools(),
        selection=ToolSelectionRequest(mode="auto", strategy="all_schemas"),
    )

    assert [tool["tool_id"] for tool in decision.selected_tools] == [
        "web_search",
        "github_issue_search",
        "coding_file_read",
    ]
    assert decision.provider_schema_count == 3
    assert decision.recommendations == []


def test_all_with_hints_exposes_every_schema_and_keeps_recommendations(monkeypatch):
    from domain.chat import tool_selection_orchestrator
    from domain.chat.tool_selection_schema import ToolSelectionRequest
    from domain.chat.tool_selection_service import ToolSelectionService

    def fake_call_model(input_data, context, *, call_handler=None):
        del input_data, context, call_handler
        return {
            "status": "ok",
            "output": {
                "selected_tools": [
                    {"tool_id": "github_issue_search", "confidence": 0.91, "reason": "GitHub context"}
                ]
            },
        }

    class FakeEmbeddingIndex:
        def search(self, user_text, tools, *, limit, backend="auto", model=""):
            del user_text, tools, limit, backend, model
            return {
                "tool_ids": ["github_issue_search"],
                "results": [],
                "stage": "semantic",
                "cache_hit": False,
                "catalog_hash": "fake",
                "duration_ms": 1,
            }

    monkeypatch.setattr(tool_selection_orchestrator, "call_model", fake_call_model)
    monkeypatch.setattr("domain.chat.tool_selection_service.ToolEmbeddingIndex", lambda: FakeEmbeddingIndex())

    decision = ToolSelectionService(settings={"tools": {"selection_strategy": "all_with_hints"}}).select(
        "check GitHub issues",
        _tools(),
        selection=ToolSelectionRequest(mode="auto", strategy="all_with_hints"),
    )

    assert [tool["tool_id"] for tool in decision.selected_tools] == [
        "web_search",
        "github_issue_search",
        "coding_file_read",
    ]
    assert decision.provider_schema_count == 3
    assert [item.tool_id for item in decision.recommendations] == ["github_issue_search"]
    assert decision.metrics["recommended_tools"][0]["reason"] == "GitHub context"


def test_catalog_ai_direct_sends_every_compact_candidate_to_selector(monkeypatch):
    from domain.chat import tool_selection_orchestrator
    from domain.chat.tool_selection_schema import ToolSelectionRequest
    from domain.chat.tool_selection_service import ToolSelectionService

    captured = {}

    def fake_call_model(input_data, context, *, call_handler=None):
        del context, call_handler
        captured["question"] = input_data["question"]
        return {
            "status": "ok",
            "output": {
                "selected_tools": [
                    {"tool_id": "web_search", "confidence": 0.8, "reason": "web search"}
                ]
            },
        }

    class FakeEmbeddingIndex:
        def search(self, user_text, tools, *, limit, backend="auto", model=""):
            del user_text, tools, limit, backend, model
            return {
                "tool_ids": ["web_search"],
                "results": [],
                "stage": "semantic",
                "cache_hit": False,
                "catalog_hash": "fake",
                "duration_ms": 1,
            }

    monkeypatch.setattr(tool_selection_orchestrator, "call_model", fake_call_model)
    monkeypatch.setattr("domain.chat.tool_selection_service.ToolEmbeddingIndex", lambda: FakeEmbeddingIndex())

    decision = ToolSelectionService(settings={"tools": {"selection_strategy": "catalog_ai", "catalog_ai_direct_limit": 20}}).select(
        "search the web and GitHub",
        _tools(),
        selection=ToolSelectionRequest(mode="auto", strategy="catalog_ai"),
    )

    assert decision.stage == "catalog_ai_direct"
    assert decision.candidate_count == 3
    question = captured["question"]
    assert "web_search" in question
    assert "github_issue_search" in question
    assert "coding_file_read" in question
    assert "Candidate tools:" in question
    assert "properties" not in question


def test_semantic_auto_resolves_configured_embedding_model(monkeypatch):
    from domain.chat import tool_selection_service as service_module
    from domain.chat.tool_selection_schema import ToolSelectionRequest

    captured = {}

    class FakeEmbeddingIndex:
        def search(self, user_text, tools, *, limit, backend="auto", model=""):
            del user_text, tools, limit, backend
            captured["model"] = model
            return {
                "tool_ids": ["web_search"],
                "results": [],
                "stage": "semantic",
                "cache_hit": False,
                "catalog_hash": "fake",
                "duration_ms": 1,
            }

    monkeypatch.setattr(service_module, "ToolEmbeddingIndex", lambda: FakeEmbeddingIndex())
    monkeypatch.setattr(
        service_module,
        "search_models",
        lambda filters: {
            "models": [
                {
                    "profile_id": "google/text-embedding-004",
                    "qualified_model_id": "google/text-embedding-004",
                    "type": "embedding",
                    "configured": True,
                }
            ],
            "filters_applied": filters,
        },
    )

    decision = service_module.ToolSelectionService(
        settings={"tools": {"selection_strategy": "semantic", "embedding_model": ""}}
    ).select(
        "search the web",
        _tools(),
        selection=ToolSelectionRequest(mode="auto", strategy="semantic"),
    )

    assert captured["model"] == "google/text-embedding-004"
    assert [tool["tool_id"] for tool in decision.selected_tools] == ["web_search"]


def test_embedding_index_calls_ai_client_embed_with_selected_model(tmp_path, monkeypatch):
    from domain.chat import tool_embedding_index

    calls = []

    class FakeAIClient:
        def embed(self, model, texts):
            calls.append((model, list(texts)))
            if len(texts) == 2:
                return {"embeddings": [[1.0, 0.0], [0.0, 1.0]]}
            return {"embeddings": [[1.0, 0.0]]}

    monkeypatch.setattr(tool_embedding_index, "AIClient", lambda: FakeAIClient())

    result = tool_embedding_index.ToolEmbeddingIndex(pack_root=tmp_path).search(
        "search the web",
        _tools()[:2],
        limit=1,
        model="google/text-embedding-004",
    )

    assert result["stage"] == "semantic"
    assert result["tool_ids"] == ["web_search"]
    assert calls[0][0] == "google/text-embedding-004"
    assert calls[1][0] == "google/text-embedding-004"


def test_conversation_tool_preferences_mode_overrides_default_turn_selection():
    from domain.chat.tool_selection_schema import ToolSelectionRequest
    from domain.chat.tool_selection_service import ToolSelectionService

    decision = ToolSelectionService(settings={"tools": {"selection_strategy": "all_schemas"}}).select(
        "search the web",
        _tools(),
        selection=ToolSelectionRequest(mode="auto", scope="turn", source="tool_selection"),
        context={"conversation_tool_preferences": {"mode": "none", "include": [{"kind": "service", "id": "github"}]}},
    )

    assert decision.mode == "none"
    assert decision.selected_tools == []
    assert decision.provider_schema_count == 0


def test_settings_permissions_auto_confirm_block_and_service_overrides():
    from domain.tool.permission_resolver import ToolPermissionResolver

    resolver = ToolPermissionResolver(
        {
            "tools": {
                "standard_permissions": {
                    "create": "auto",
                    "update": "confirm",
                    "delete": "auto",
                },
                "service_permission_overrides": {
                    "github": {"update": "auto"},
                },
            }
        }
    )

    assert resolver.resolve({"tool_id": "doc_create", "action_class": "create"})["permission"] == "auto"
    assert resolver.resolve({"tool_id": "doc_update", "action_class": "update"})["permission"] == "confirm"
    assert resolver.resolve({"tool_id": "github_update_issue", "action_class": "update", "metadata": {"service_id": "github"}})["permission"] == "auto"
    assert resolver.resolve({"tool_id": "file_delete", "action_class": "delete"})["permission"] == "confirm"
    assert resolver.resolve({"tool_id": "external_send", "action_class": "send", "requires_approval": True})["permission"] == "confirm"


def test_full_tool_selection_trace_creates_hidden_child_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "conversations.json"))

    from domain.chat import run_request
    from domain.chat.store import ChatStore
    from domain.chat.tool_selection_schema import ToolSelectionDecision

    store = ChatStore()
    parent = store.create_conversation(model="stub/default")
    context = {
        "conversation_id": parent["id"],
        "model": "stub/default",
        "tool_selection": {"selection_id": "sel-full", "strategy": "catalog_ai"},
    }
    decision = ToolSelectionDecision(
        selection_id="sel-full",
        mode="auto",
        strategy="catalog_ai",
        stage="catalog_ai_direct",
        selected_tools=[{"tool_id": "web_search"}],
    )

    run_request._persist_tool_selection_trace(
        context,
        {"tools": {"selector_trace": "full"}},
        decision,
        user_text="search the web",
        trace={"selection_id": "sel-full", "input": "full trace payload"},
    )

    child_id = context["tool_selection"]["trace_conversation_id"]
    child = store.get_conversation(child_id)
    assert child["conversation_kind"] == "tool_selection_trace"
    assert child["parent_conversation_id"] == parent["id"]
    assert child["metadata"]["hidden"] is True
    assert child["metadata"]["tool_selection_trace"] is True
    assert child["is_archived"] is True
    assert child["messages"][0]["metadata"]["hidden"] is True

    visible, total = store.list_conversations(include_messages=True)
    assert total == 1
    assert [item["id"] for item in visible] == [parent["id"]]
