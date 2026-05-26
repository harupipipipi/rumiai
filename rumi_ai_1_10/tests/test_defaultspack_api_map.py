from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from ecosystem.defaultspack.domain.api_map.builder import build_api_map
from ecosystem.defaultspack.transport.registry import HttpRouteSpec


def test_api_map_contains_route_tool_and_webhook_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeToolRegistry:
        def list_tools(self):
            return [
                {
                    "tool_id": "web_search",
                    "name": "web_search",
                    "display_name": "Web Search",
                    "execution": {"handler": "domain.search:web_search"},
                }
            ]

    class _FakeEndpointStore:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_endpoints(self):
            return [{"id": "research-webhook", "input_profile_id": "ingress.research"}]

    class _FakeInputProfileRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_profiles(self):
            return [SimpleNamespace(id="ingress.research", display_name="Ingress Research")]

    class _FakeProfileWorkspaceManager:
        def load_profile_yaml(self, profile_id: str):
            return {
                "profile_id": profile_id,
                "name": "Research Profile",
                "metadata": {
                    "selected": {
                        "tools": ["web_search"],
                        "webhooks": ["research-webhook"],
                        "api_routes": ["POST /api/chat/conversations/{id}/messages"],
                    }
                },
                "policy": {
                    "api_route_allowlist": ["POST /api/chat/conversations/{id}/messages"],
                    "enforce_api_route_allowlist": False,
                },
            }

    monkeypatch.setattr(
        "ecosystem.defaultspack.domain.api_map.builder.canonical_http_route_specs",
        lambda include_always_available=True: [
            HttpRouteSpec(
                method="POST",
                pattern="/api/chat/conversations/{id}/messages",
                block_module="chat.messages",
                function_name="post_messages",
                flow_id="research.flow",
            )
        ],
    )
    monkeypatch.setattr("ecosystem.defaultspack.domain.api_map.builder.ToolRegistry", _FakeToolRegistry)
    monkeypatch.setattr("ecosystem.defaultspack.domain.api_map.builder.WebhookEndpointStore", _FakeEndpointStore)
    monkeypatch.setattr("ecosystem.defaultspack.domain.api_map.builder.InputProfileRegistry", _FakeInputProfileRegistry)
    monkeypatch.setattr("ecosystem.defaultspack.domain.api_map.builder.ProfileWorkspaceManager", _FakeProfileWorkspaceManager)
    monkeypatch.setattr("ecosystem.defaultspack.domain.api_map.builder.active_profile_id", lambda: "research-profile")

    payload = build_api_map(profile_id="research-profile")
    edges = {(edge["from_id"], edge["to_id"], edge["kind"]) for edge in payload["edges"]}

    assert ("api:POST /api/chat/conversations/{id}/messages", "flow:research.flow", "enters_flow") in edges
    assert ("api:POST /api/chat/conversations/{id}/messages", "block:chat.messages", "handled_by") in edges
    assert ("tool:web_search", "handler:domain.search:web_search", "executes_handler") in edges
    assert ("webhook:research-webhook", "node:ingress.research", "uses_input_profile") in edges
    assert ("profile:research-profile", "tool:web_search", "selects") in edges
    route = next(
        node
        for node in payload["nodes"]
        if node["id"] == "api:POST /api/chat/conversations/{id}/messages"
    )
    assert route["metadata"]["source_type"] == "flow"
    assert route["metadata"]["runtime_role"] == "entrypoint"
    block = next(node for node in payload["nodes"] if node["id"] == "block:chat.messages")
    assert block["metadata"]["runtime_role"] == "implementation"
    assert payload["summary"]["operation_count"] >= 2
    assert payload["summary"]["implementation_count"] >= 1
    assert payload["profile_runtime"]["policy"]["api_route_allowlist"] == [
        "POST /api/chat/conversations/{id}/messages"
    ]
    assert any(
        diagnostic.get("code") == "api_route_allowlist_not_enforced"
        for diagnostic in payload["diagnostics"]
    )
