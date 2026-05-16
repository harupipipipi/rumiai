from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_fallback_sorting_keeps_static_agent_company_status_before_generic_status():
    from ecosystem.defaultspack.transport.registry import (
        HttpRouteSpec,
        build_http_routes_from_specs,
    )

    class Server:
        def _invoke_fallback_block(self, block_module, request_data, path_params, inject=None):
            return {"block_module": block_module}

    routes = build_http_routes_from_specs(
        Server(),
        [
            HttpRouteSpec(
                "GET",
                "/api/agent/{id}/status",
                block_module="blocks.agent.status",
                path_inject={"id": "execution_id"},
            ),
            HttpRouteSpec(
                "GET",
                "/api/agent/company/status",
                block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.status",
            ),
        ],
    )
    patterns = [compiled.pattern for method, compiled, _, _, _ in routes if method == "GET"]

    assert patterns.index("^/api/agent/company/status$") < patterns.index(
        "^/api/agent/(?P<id>[^/]+)/status$"
    )


def test_registry_sorting_keeps_static_agent_company_status_before_generic_status():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    def generic_status(request_data, context):
        return {"handler": "generic", "request_data": request_data}

    def company_status(request_data, context):
        return {"handler": "company", "request_data": request_data}

    class Facade:
        def get_interface(self, key, strategy=None):
            if key != "io.http.route":
                return None
            return [
                {
                    "method": "GET",
                    "pattern": "/api/agent/{id}/status",
                    "handler": generic_status,
                    "path_inject": {"id": "execution_id"},
                },
                {
                    "method": "GET",
                    "pattern": "/api/agent/company/status",
                    "handler": company_status,
                    "path_inject": {},
                },
            ]

    server = DefaultsHttpServer(Facade())
    handler, params, source, path_inject = server._match_route("GET", "/api/agent/company/status")

    assert handler is company_status
    assert params == {}
    assert source == "registry"
    assert path_inject == {}


@pytest.mark.parametrize(
    ("method", "path", "block_module", "path_params", "inject", "payload"),
    [
        (
            "GET",
            "/api/agent/companies/acme/status",
            "blocks.company.status",
            {"company_id": "acme"},
            {"company_id": "company_id"},
            {"_method": "GET"},
        ),
        (
            "PUT",
            "/api/agent/companies/acme/agents/bot",
            "blocks.company.agents",
            {"company_id": "acme", "agent_id": "bot"},
            {"company_id": "company_id", "agent_id": "agent_id"},
            {"_method": "PUT", "action": "update"},
        ),
        (
            "POST",
            "/api/integrations/p2p/events",
            "blocks.integrations.p2p",
            {},
            {},
            {"_method": "POST"},
        ),
        (
            "POST",
            "/api/p2p/messages/send",
            "blocks.p2p.messages_send",
            {},
            {},
            {"_method": "POST"},
        ),
        (
            "DELETE",
            "/api/p2p/peers/peer-a",
            "blocks.p2p.peers",
            {"peer_id": "peer-a"},
            {"peer_id": "peer_id"},
            {"_method": "DELETE"},
        ),
        (
            "POST",
            "/api/chat/conversations/c1/compact",
            "blocks.chat.compact",
            {"id": "c1"},
            {"id": "conversation_id"},
            {"_method": "POST"},
        ),
        (
            "GET",
            "/api/coding/workspaces/ws1",
            "blocks.coding.workspace.get",
            {"workspace_id": "ws1"},
            {"workspace_id": "workspace_id"},
            {"_method": "GET"},
        ),
        (
            "POST",
            "/api/coding/workspaces/ws1/trust",
            "blocks.coding.workspace.trust",
            {"workspace_id": "ws1"},
            {"workspace_id": "workspace_id"},
            {"_method": "POST"},
        ),
    ],
)
def test_new_fallback_routes_dispatch_to_expected_blocks(
    method,
    path,
    block_module,
    path_params,
    inject,
    payload,
):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    calls = []

    def fake_invoke(module_name, request_data, params, route_inject=None):
        calls.append(
            {
                "block_module": module_name,
                "request_data": request_data,
                "path_params": params,
                "inject": route_inject or {},
            }
        )
        return {"status": "ok"}

    server._invoke_fallback_block = fake_invoke
    handler, params, source, path_inject = server._match_route(method, path)

    assert handler is not None
    assert source == "fallback"
    assert params == path_params
    assert path_inject == inject
    assert handler({"body": "kept"}, params) == {"status": "ok"}
    assert calls[-1]["block_module"] == block_module
    assert calls[-1]["path_params"] == path_params
    assert calls[-1]["inject"] == inject
    for key, value in payload.items():
        assert calls[-1]["request_data"][key] == value


def test_fallback_specs_list_company_p2p_compact_and_workspace_routes():
    from ecosystem.defaultspack.transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

    routes = {(spec.method, spec.pattern, spec.block_module) for spec in _FALLBACK_HTTP_ROUTE_SPECS}
    expected = {
        ("GET", "/api/agent/companies", "blocks.company.list"),
        ("POST", "/api/agent/companies", "blocks.company.create"),
        ("GET", "/api/company", "blocks.company.list"),
        ("POST", "/api/company/bootstrap", "blocks.company.bootstrap"),
        ("GET", "/api/agent/companies/{company_id}/status", "blocks.company.status"),
        ("PUT", "/api/agent/companies/{company_id}/agents/{agent_id}", "blocks.company.agents"),
        ("POST", "/api/agent/companies/{company_id}/channels/{channel_id}/messages", "blocks.company.messages"),
        ("PUT", "/api/agent/companies/{company_id}/tasks/{task_id}", "blocks.company.tasks"),
        ("DELETE", "/api/agent/companies/{company_id}/inbound-routes/{route_id}", "blocks.company.inbound_routes"),
        ("GET", "/api/p2p/status", "blocks.p2p.status"),
        ("POST", "/api/p2p/identity/rotate", "blocks.p2p.identity"),
        ("PUT", "/api/p2p/peers/{peer_id}", "blocks.p2p.peers"),
        ("POST", "/api/p2p/messages/inbound", "blocks.p2p.messages_inbound"),
        ("POST", "/api/integrations/p2p/events", "blocks.integrations.p2p"),
        ("POST", "/api/chat/conversations/{id}/compact", "blocks.chat.compact"),
        ("POST", "/api/chat/conversations/{id}/auto-compact", "blocks.chat.auto_compact"),
        ("GET", "/api/coding/workspaces/get", "blocks.coding.workspace.get"),
        ("POST", "/api/coding/workspaces/select", "blocks.coding.workspace.select"),
        ("GET", "/api/coding/workspaces/{workspace_id}", "blocks.coding.workspace.get"),
        ("POST", "/api/coding/workspaces/{workspace_id}/trust", "blocks.coding.workspace.trust"),
    }

    assert expected <= routes


def test_p2p_pre_auth_only_exposes_signed_integration_event():
    manifest = json.loads((DEFAULTSPACK_ROOT / "ecosystem.json").read_text(encoding="utf-8"))
    pre_auth_routes = manifest["pre_auth_routes"]
    method_paths = {
        (route.get("method"), route.get("path"))
        for route in pre_auth_routes
        if route.get("path")
    }

    assert ("POST", "/api/integrations/p2p/events") in method_paths
    assert not any(
        str(route.get("path") or route.get("path_prefix") or "").startswith("/api/p2p")
        for route in pre_auth_routes
    )


def test_routes_json_documents_new_route_groups():
    routes = json.loads((DEFAULTSPACK_ROOT / "routes.json").read_text(encoding="utf-8"))["routes"]
    method_paths = {(route["method"], route["path"]) for route in routes}
    expected = {
        ("POST", "/api/chat/conversations/{id}/compact"),
        ("GET", "/api/agent/companies/{company_id}/status"),
        ("POST", "/api/agent/companies/{company_id}/dispatch"),
        ("POST", "/api/agent/companies/{company_id}/inbound-routes/{route_id}/ingest"),
        ("GET", "/api/p2p/status"),
        ("POST", "/api/p2p/pairing/start"),
        ("POST", "/api/integrations/p2p/events"),
        ("GET", "/api/coding/workspaces/{workspace_id}"),
        ("POST", "/api/coding/workspaces/{workspace_id}/select"),
    }

    assert expected <= method_paths
