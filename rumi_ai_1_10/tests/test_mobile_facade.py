from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_mobile_bootstrap_returns_server_and_capability_flags():
    from blocks.mobile.bootstrap import run

    result = run({}, None)
    assert result["status"] == "ok"
    data = result["data"]
    assert "server" in data
    assert {"device_id", "label", "version"} <= set(data["server"])
    caps = data["capabilities"]
    assert caps["chat"] is True
    assert caps["tools"] is True
    assert caps["credential_transfer"] is False
    assert "cursor" in data


def test_mobile_manifest_exposes_facade_without_authority_routes():
    from blocks.mobile.manifest import run

    result = run({}, None)
    assert result["status"] == "ok"
    data = result["data"]
    assert data["kind"] == "rumi_mobile_manifest_v1"
    routes = data["routes"]
    assert routes
    assert all(route["path"].startswith("/api/mobile/v1/") for route in routes)
    assert all(not route["path"].startswith("/api/authority/") for route in routes)
    assert all(not str(route.get("feature", "")).endswith("_admin") for route in routes)
    assert data["authority_routes"] == []
    assert "mobile_client" in data["token_roles"]
    assert "mobile_approver" in data["token_roles"]
    assert data["token_roles"]["mobile_client"]["scopes"] == [
        "chat.read",
        "chat.write",
        "tools.observe",
    ]


def test_mobile_capabilities_returns_provider_and_model_catalogs():
    from blocks.mobile.capabilities import run

    result = run({}, None)
    assert result["status"] == "ok"
    data = result["data"]
    assert len(data["providers"]) > 0
    assert len(data["models"]) > 0

    provider = data["providers"][0]
    assert "provider_id" in provider
    assert "display_name" in provider
    assert "configured" in provider
    # Secrets must not leak: only env var names, never values.
    assert all(isinstance(name, str) for name in provider.get("env_vars", []))
    assert "api_key" not in str(provider).lower() or provider.get("configured_api_count") is not None

    model = data["models"][0]
    assert "id" in model
    assert "provider_id" in model
    assert "model_id" in model
    assert "max_context" in model

    assert "runtime" in data
    assert "preferred_model" in data["runtime"]
    assert "commands" in data
    assert any(command["name"] == "model" for command in data["commands"])


def test_mobile_capabilities_provider_filter_narrows_models():
    from blocks.mobile.capabilities import run

    all_models = run({}, None)["data"]["models"]
    if not all_models:
        return
    provider_id = all_models[0]["provider_id"]
    filtered = run({"provider": provider_id}, None)["data"]["models"]
    assert filtered
    assert all(m["provider_id"] == provider_id for m in filtered)


def test_mobile_capabilities_query_param_provider_filter():
    from blocks.mobile.capabilities import run

    all_models = run({}, None)["data"]["models"]
    if not all_models:
        return
    provider_id = all_models[0]["provider_id"]
    filtered = run({"query_params": {"provider": provider_id}}, None)["data"]["models"]
    assert filtered
    assert all(m["provider_id"] == provider_id for m in filtered)


def test_mobile_capabilities_include_templates_flag():
    from blocks.mobile.capabilities import run

    with_templates = run({"include_templates": True}, None)["data"]
    without = run({"include_templates": False}, None)["data"]
    assert "templates" in with_templates
    assert "templates" in without
    assert without["templates"] == []


def test_mobile_capabilities_no_secret_values_in_provider_entries():
    from blocks.mobile.capabilities import run

    providers = run({}, None)["data"]["providers"]
    blob = str(providers)
    # Active HMAC keys / API key values must never appear in catalog payloads.
    forbidden = ["sk-", "Bearer ", "hmac_secret"]
    for token in forbidden:
        assert token not in blob, f"unexpected secret token in catalog: {token}"


def test_mobile_capabilities_provider_summary_has_openai_compatible_flag():
    from blocks.mobile.capabilities import run

    providers = run({}, None)["data"]["providers"]
    assert any("openai_compatible" in p for p in providers)


def test_mobile_route_contract_is_reflected_in_registry():
    from domain.mobile.contract import iter_mobile_route_contracts
    from transport.registry import canonical_http_route_specs

    specs = {
        (spec.method, spec.pattern): spec
        for spec in canonical_http_route_specs(include_always_available=False)
    }

    for route in iter_mobile_route_contracts():
        spec = specs.get((route.method, route.pattern))
        assert spec is not None, f"missing mobile route spec: {route.method} {route.pattern}"
        assert spec.block_module == route.block_module
        assert spec.flow_id == route.flow_id
        assert spec.fallback_block_module == (
            route.fallback_block_module or route.block_module
        )
        if route.feature.endswith("_admin"):
            assert spec.sensitive is True
            assert spec.local_only is True


def test_mobile_route_contract_legacy_routes_build_fallback_table():
    from domain.mobile.contract import iter_mobile_route_contracts
    from transport.registry import build_fallback_http_routes

    class _Server:
        def __getattr__(self, name):
            if name.startswith("_handle_"):
                return lambda _request_data, _path_params: {"status": "ok"}
            raise AttributeError(name)

        def _invoke_fallback_block(self, *_args, **_kwargs):
            return {"status": "ok"}

        def _invoke_flow_route(self, *_args, **_kwargs):
            return {"status": "ok"}

        def _invoke_function_route(self, *_args, **_kwargs):
            return {"status": "ok"}

    routes = build_fallback_http_routes(_Server())
    compiled_routes = {(method, pattern.pattern) for method, pattern, *_ in routes}

    for route in iter_mobile_route_contracts():
        assert (
            route.method,
            _compiled_pattern_for(route.pattern),
        ) in compiled_routes, (
            "mobile fallback route is not buildable: "
            f"{route.method} {route.pattern}"
        )


def test_mobile_pc_equivalent_routes_exist_for_parity_guard():
    from domain.mobile.contract import iter_mobile_route_contracts
    from transport.registry import canonical_http_route_specs

    specs = {
        f"{spec.method} {spec.pattern}"
        for spec in canonical_http_route_specs(include_always_available=False)
    }
    equivalents = [
        route.pc_equivalent
        for route in iter_mobile_route_contracts()
        if route.pc_equivalent
    ]

    assert equivalents
    for equivalent in equivalents:
        assert equivalent in specs


def test_mobile_contract_covers_pc_conversation_routes():
    from domain.mobile.contract import iter_mobile_route_contracts
    from transport.registry import canonical_http_route_specs

    pc_conversation_routes = {
        f"{spec.method} {spec.pattern}"
        for spec in canonical_http_route_specs(include_always_available=False)
        if spec.pattern.startswith("/api/chat/conversations")
    }
    mobile_equivalents = {
        route.pc_equivalent
        for route in iter_mobile_route_contracts()
        if route.pc_equivalent
    }

    assert pc_conversation_routes <= mobile_equivalents


def test_mobile_device_scope_contract_blocks_unknown_routes():
    from domain.mobile.contract import required_device_scope

    assert required_device_scope("GET", "/api/mobile/v1/conversations") == "chat.read"
    assert (
        required_device_scope(
            "POST",
            "/api/mobile/v1/conversations/convo-1/stream",
        )
        == "chat.write"
    )
    assert (
        required_device_scope("POST", "/api/mobile/v1/commands/execute")
        == "chat.write"
    )
    assert required_device_scope("GET", "/api/packs") == ""
    assert required_device_scope("GET", "/api/mobile/v1/approvals") == ""
    assert required_device_scope("POST", "/api/mobile/v1/approvals/auth_1/approve") == ""
    assert required_device_scope("GET", "/api/mobile/v1/pairings/pair-1/review") == ""
    assert required_device_scope("POST", "/api/mobile/v1/pairings/pair-1/approve") == ""
    assert required_device_scope("POST", "/api/mobile/v1/pairings/pair-1/reject") == ""


def test_mobile_manifest_does_not_expose_legacy_approval_facade():
    from blocks.mobile.manifest import run
    from domain.mobile.contract import iter_mobile_route_contracts

    contract_paths = {route.pattern for route in iter_mobile_route_contracts()}
    assert "/api/mobile/v1/approvals" not in contract_paths
    assert "/api/mobile/v1/approvals/{id}/approve" not in contract_paths
    assert "/api/mobile/v1/approvals/{id}/deny" not in contract_paths

    manifest = run({}, None)["data"]
    route_paths = {route["path"] for route in manifest["routes"]}
    assert "/api/mobile/v1/approvals" not in route_paths
    assert not manifest["authority_routes"]


def test_mobile_commands_execute_uses_pc_slash_registry():
    from blocks.mobile.commands import run

    result = run({"command": "model", "args": {}, "mode": "chat"}, None)
    assert result["status"] == "ok"
    data = result["data"]
    assert data["command"]["name"] == "model"
    assert data["action"] == "open_model_picker"


def _compiled_pattern_for(pattern: str) -> str:
    import re

    compiled = re.sub(
        r"\{(\w+)\}",
        lambda match: rf"(?P<{match.group(1)}>[^/]+)",
        pattern,
    )
    return f"^{compiled}$"
