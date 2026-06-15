from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _has_change_request_backend() -> bool:
    for module_name in ("blocks.change_requests", "domain.change_request.store"):
        try:
            if importlib.util.find_spec(module_name) is not None:
                return True
        except ModuleNotFoundError:
            continue
    block_dir = DEFAULTSPACK_ROOT / "blocks" / "change_request"
    if any(block_dir.glob("*.py")):
        return True
    return False


def test_change_request_api_routes_are_registered_when_backend_exists():
    if not _has_change_request_backend():
        pytest.skip("change_request backend implementation is not present yet")

    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    routes = {(spec.method, spec.pattern): spec for spec in canonical_http_route_specs()}

    assert ("GET", "/api/change-requests") in routes
    assert ("POST", "/api/change-requests") in routes
    assert ("GET", "/api/change-requests/{id}") in routes

    for method, pattern in routes:
        if "/api/change-requests" not in pattern:
            continue
        spec = routes[(method, pattern)]
        target_text = " ".join(
            str(value)
            for value in (
                pattern,
                spec.block_module,
                spec.function_name,
                spec.flow_id,
                spec.fallback_block_module,
                spec.handler_name,
            )
        ).lower()
        forbidden_terms = (
            "pull" + "_" + "request",
            "pull" + "-" + "request",
            "local" + "_" + "pr",
            "local" + "-" + "pr",
        )
        for forbidden_term in forbidden_terms:
            assert forbidden_term not in target_text
