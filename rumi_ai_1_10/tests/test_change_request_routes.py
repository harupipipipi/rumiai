from __future__ import annotations

import importlib
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
    assert ("POST", "/api/change-requests/{id}/comments") in routes
    assert ("PATCH", "/api/change-requests/{id}/comments/{comment_id}") in routes
    assert ("POST", "/api/change-requests/{id}/decision") in routes
    assert ("PATCH", "/api/change-requests/{id}/viewed-files") in routes
    assert ("GET", "/api/change-requests/{id}/checks") in routes
    assert ("POST", "/api/change-requests/{id}/checks/run") in routes
    assert ("GET", "/api/change-requests/{id}/seal") in routes
    assert ("POST", "/api/change-requests/{id}/commit") not in routes
    assert ("POST", "/api/change-requests/{id}/export-patch") in routes

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


def test_change_request_routes_are_sensitive_local_routes_with_origin_and_csrf_checks():
    from domain.safety.local_guard import is_sensitive_coding_path, require_local_guard

    assert is_sensitive_coding_path("/api/change-requests", "GET") is True
    assert is_sensitive_coding_path("/api/change-requests", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test", "GET") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test", "PATCH") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/refresh", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/export-patch", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/comments", "GET") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/comments", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/comments/comment_1", "GET") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/comments/comment_1", "PATCH") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/decision", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/viewed-files", "GET") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/viewed-files", "PATCH") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/viewed-files", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/checks", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/checks", "GET") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/checks/check_1", "GET") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/checks/run", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/checks/run-check", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/run-check", "POST") is True
    assert is_sensitive_coding_path("/api/change-requests/cr_test/checks/run", "GET") is False
    assert is_sensitive_coding_path("/api/change-requests/cr_test/seal", "GET") is True

    assert require_local_guard(
        "/api/change-requests/cr_test/seal",
        "GET",
        {"Origin": "https://example.test"},
        ("127.0.0.1", 54321),
    ) == (403, "origin not allowed for sensitive local route", "ORIGIN_DENIED")
    assert require_local_guard(
        "/api/change-requests/cr_test/export-patch",
        "POST",
        {"Origin": "http://localhost:8766"},
        ("127.0.0.1", 54321),
    ) == (403, "CSRF header required for sensitive local mutation", "CSRF_REQUIRED")
    assert require_local_guard(
        "/api/change-requests/cr_test/export-patch",
        "POST",
        {"Origin": "http://localhost:8766", "X-Rumi-CSRF": "1"},
        ("127.0.0.1", 54321),
    ) is None


def test_change_request_commit_route_is_default_off_and_flagged(monkeypatch):
    if not _has_change_request_backend():
        pytest.skip("change_request backend implementation is not present yet")

    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    monkeypatch.delenv("RUMI_REVIEW_ENABLE_COMMIT", raising=False)
    routes = {(spec.method, spec.pattern) for spec in canonical_http_route_specs()}
    assert ("POST", "/api/change-requests/{id}/commit") not in routes

    monkeypatch.setenv("RUMI_REVIEW_ENABLE_COMMIT", "1")
    routes = {(spec.method, spec.pattern) for spec in canonical_http_route_specs()}
    assert ("POST", "/api/change-requests/{id}/commit") in routes


def test_change_request_setup_commit_route_is_default_off_and_flagged(monkeypatch):
    if not _has_change_request_backend():
        pytest.skip("change_request backend implementation is not present yet")

    from ecosystem.defaultspack.blocks.change_request import setup

    class Registry:
        def __init__(self) -> None:
            self.routes = []

        def register(self, _kind, value, meta=None):
            self.routes.append((value["method"], value["pattern"]))

    monkeypatch.delenv("RUMI_REVIEW_ENABLE_COMMIT", raising=False)
    registry = Registry()
    result = setup.run({"interface_registry": registry})
    assert ("POST", "/api/change-requests/{id}/commit") not in registry.routes
    assert "/api/change-requests/{id}/commit" not in result["registered"]

    monkeypatch.setenv("RUMI_REVIEW_ENABLE_COMMIT", "1")
    registry = Registry()
    result = setup.run({"interface_registry": registry})
    assert ("POST", "/api/change-requests/{id}/commit") in registry.routes
    assert "/api/change-requests/{id}/commit" in result["registered"]


def test_change_request_function_ids_are_registered_when_backend_exists(monkeypatch):
    if not _has_change_request_backend():
        pytest.skip("change_request backend implementation is not present yet")

    monkeypatch.delenv("RUMI_REVIEW_ENABLE_COMMIT", raising=False)
    from domain.function_runtime.registry import block_module_for

    assert block_module_for("coding_change_request_list") == "blocks.change_request.collection"
    assert block_module_for("coding_change_request_comment") == "blocks.change_request.comments"
    assert block_module_for("coding_change_request_run_check") == "blocks.change_request.checks"
    assert block_module_for("coding_change_request_commit") is None
    assert block_module_for("coding_change_request_export_patch") == "blocks.change_request.export_patch"


def test_change_request_commit_function_is_default_off_and_flagged(monkeypatch):
    if not _has_change_request_backend():
        pytest.skip("change_request backend implementation is not present yet")

    import domain.function_runtime.manifest_factory as manifest_factory
    import domain.function_runtime.registry as registry

    try:
        monkeypatch.delenv("RUMI_REVIEW_ENABLE_COMMIT", raising=False)
        importlib.reload(manifest_factory)
        importlib.reload(registry)
        assert registry.block_module_for("coding_change_request_commit") is None
        assert "coding_change_request_commit" not in manifest_factory.FUNCTION_SPECS_BY_ID

        monkeypatch.setenv("RUMI_REVIEW_ENABLE_COMMIT", "1")
        importlib.reload(manifest_factory)
        importlib.reload(registry)
        assert registry.block_module_for("coding_change_request_commit") == "blocks.change_request.commit"
        assert "coding_change_request_commit" in manifest_factory.FUNCTION_SPECS_BY_ID
    finally:
        monkeypatch.delenv("RUMI_REVIEW_ENABLE_COMMIT", raising=False)
        importlib.reload(manifest_factory)
        importlib.reload(registry)


def test_change_request_commit_function_bridge_registration_is_default_off_and_flagged(monkeypatch):
    if not _has_change_request_backend():
        pytest.skip("change_request backend implementation is not present yet")

    from domain.function_runtime.bridge import ensure_defaultspack_functions_registered

    class Registry:
        def __init__(self) -> None:
            self.function_ids = []

        def register(self, *, pack_id, function_id, manifest, function_dir):
            self.function_ids.append(str(function_id))
            return True

    class Container:
        def __init__(self, registry) -> None:
            self.registry = registry

        def get_or_none(self, key):
            if key == "function_registry":
                return self.registry
            return None

    monkeypatch.delenv("RUMI_REVIEW_ENABLE_COMMIT", raising=False)
    registry = Registry()
    ensure_defaultspack_functions_registered(Container(registry))
    assert "coding_change_request_commit" not in registry.function_ids

    monkeypatch.setenv("RUMI_REVIEW_ENABLE_COMMIT", "1")
    registry = Registry()
    ensure_defaultspack_functions_registered(Container(registry))
    assert "coding_change_request_commit" in registry.function_ids
