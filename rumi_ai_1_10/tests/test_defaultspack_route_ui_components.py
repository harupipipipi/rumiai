from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402
from domain.frontend.registry import FrontendRegistry  # noqa: E402
from transport.registry import build_fallback_http_routes, component_http_route_specs  # noqa: E402


class _FakeServer:
    def _invoke_fallback_block(self, *args, **kwargs):
        return {"status": "ok", "args": args, "kwargs": kwargs}

    def _handle_health(self, *_args, **_kwargs):
        return {"status": "ok"}

    def _handle_context_info(self, *_args, **_kwargs):
        return {"status": "ok"}

    def _handle_desktop_system_info(self, *_args, **_kwargs):
        return {"status": "ok"}

    def _handle_chat_redirect(self, *_args, **_kwargs):
        return {"status": "ok"}

    def _handle_static(self, *_args, **_kwargs):
        return {"status": "ok"}

    def _handle_static_file(self, *_args, **_kwargs):
        return {"status": "ok"}


def test_component_route_specs_include_manifest_backed_routes():
    route_pairs = {(spec.method, spec.pattern, spec.block_module) for spec in component_http_route_specs()}

    assert ("POST", "/api/integrations/line/webhook", "blocks.integrations.line") in route_pairs
    assert ("POST", "/api/integrations/discord/interactions", "blocks.integrations.discord") in route_pairs
    assert ("POST", "/api/integrations/slack/events", "blocks.integrations.slack") in route_pairs
    assert ("GET", "/api/ui/catalog", "blocks.ui.catalog") in route_pairs


def test_fallback_routes_dedupe_component_routes_without_reordering_core_paths():
    routes = build_fallback_http_routes(_FakeServer())
    pairs = [(method, compiled.pattern) for method, compiled, *_rest in routes]

    assert len(pairs) == len(set(pairs))
    assert any(method == "POST" and "api/integrations/line/webhook" in pattern for method, pattern in pairs)
    assert any(method == "GET" and "api/ui/catalog" in pattern for method, pattern in pairs)


def test_ui_catalog_exposes_component_route_and_surface_metadata():
    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))
    assert registry.get("ui_surfaces", "default_shell").id == "default_shell"
    assert registry.get("transports", "http").id == "http"

    with patch("domain.frontend.registry.AIClient") as mock_client:
        mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
        catalog = FrontendRegistry(DEFAULTSPACK_ROOT).build_catalog()

    route_pairs = {
        (route["method"], route["path"])
        for route in catalog["routes"]["manifest_backed"]
    }
    sidebar_ids = {item["id"] for item in catalog["sidebar"]["items"]}

    assert ("POST", "/api/integrations/line/webhook") in route_pairs
    assert ("GET", "/api/ui/catalog") in route_pairs
    assert "component-manifests" in sidebar_ids
