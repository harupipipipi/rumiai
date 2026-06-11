from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _Approval:
    def __init__(self, approved: bool):
        self.approved = approved

    def is_pack_approved_and_verified(self, pack_id: str):
        return self.approved, None if self.approved else "not_found"


def test_api_routes_skip_unapproved_pack():
    from core_runtime.pack_api_server import PackAPIHandler

    pack_info = SimpleNamespace(
        ecosystem={
            "api_routes": [
                {"method": "GET", "path": "/api/evil", "function_id": "run"},
            ],
        },
    )
    registry = SimpleNamespace(packs={"evil_pack": pack_info})
    old_manager = PackAPIHandler.approval_manager
    PackAPIHandler.approval_manager = _Approval(False)
    try:
        count = PackAPIHandler.load_api_routes(registry)
    finally:
        PackAPIHandler.approval_manager = old_manager

    assert count == 0
    assert ("GET", "/api/evil") not in PackAPIHandler._api_route_exact


def test_api_route_dispatch_rechecks_pack_approval():
    from core_runtime.pack_api_server import PackAPIHandler

    PackAPIHandler._api_route_exact = {
        ("POST", "/api/evil"): {
            "pack_id": "evil_pack",
            "handler": "",
            "function_id": "run",
            "pass_body": True,
            "response_mode": "result",
            "args": {},
            "path_param_map": {},
        }
    }
    PackAPIHandler._api_route_patterns = []
    handler = PackAPIHandler.__new__(PackAPIHandler)
    sent = []
    handler._send_response = lambda response, status=200: sent.append((response, status))

    with patch.object(
        PackAPIHandler,
        "_is_pack_approved_for_runtime_routes",
        return_value=False,
    ):
        assert handler._dispatch_api_route("POST", "/api/evil", {"x": 1}) is True

    assert sent[0][1] == 403


def test_function_registry_trusts_manifest_entrypoint_file(tmp_path):
    from core_runtime.function_registry import FunctionRegistry

    func_dir = tmp_path / "func"
    func_dir.mkdir()
    (func_dir / "main.py").write_text("def run(ctx, args): return {'wrong': True}\n", encoding="utf-8")
    trusted = func_dir / "trusted.py"
    trusted.write_text("def run(ctx, args): return {'ok': True}\n", encoding="utf-8")

    registry = FunctionRegistry()
    assert registry.register(
        pack_id="pack",
        function_id="fn",
        manifest={"entrypoint": "trusted.py:run"},
        function_dir=func_dir,
    )
    entry = registry.get("pack:fn")
    assert entry is not None
    assert Path(entry.main_py_path).resolve() == trusted.resolve()


def test_function_registry_rejects_escaping_entrypoint(tmp_path):
    from core_runtime.function_registry import FunctionRegistry

    func_dir = tmp_path / "func"
    func_dir.mkdir()
    (tmp_path / "evil.py").write_text("def run(ctx, args): return {}\n", encoding="utf-8")

    with pytest.raises(ValueError):
        FunctionRegistry().register(
            pack_id="pack",
            function_id="fn",
            manifest={"entrypoint": "../evil.py:run"},
            function_dir=func_dir,
        )


def test_staging_helpers_reject_path_like_ids(tmp_path):
    from core_runtime.pack_applier import PackApplier
    from core_runtime.pack_importer import PackImporter

    importer = PackImporter(staging_root=str(tmp_path / "staging"))
    applier = PackApplier(
        ecosystem_dir=str(tmp_path / "ecosystem"),
        backup_root=str(tmp_path / "backups"),
        staging_root=str(tmp_path / "staging"),
    )

    assert importer.get_staging_meta("../outside") is None
    assert importer.cleanup_staging("../outside") is False
    result = applier.apply("../outside")
    assert result.success is False
    assert "Invalid staging_id" in (result.error or "")


def test_extension_approval_applies_staging(monkeypatch, tmp_path):
    from ecosystem.defaultspack.backend.pack_extension.extension_manager import (
        ExtensionManager,
        PatchMode,
    )

    calls = []

    class _ApplyResult:
        success = True
        applied_pack_ids = ["new_pack"]
        backup_paths = {"old_pack": str(tmp_path / "backups" / "old_pack")}

        def to_dict(self):
            return {
                "success": True,
                "applied_pack_ids": self.applied_pack_ids,
                "backup_paths": self.backup_paths,
            }

    class _Applier:
        def __init__(self, *, ecosystem_dir, backup_root):
            calls.append(("init", ecosystem_dir, backup_root))

        def apply(self, staging_id, *, mode="replace", actor="api_user"):
            calls.append(("apply", staging_id, mode, actor))
            return _ApplyResult()

    monkeypatch.setattr("core_runtime.pack_applier.PackApplier", _Applier)
    manager = ExtensionManager(
        requests_root=tmp_path / "requests",
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
    )
    created = manager.create_pack_request(
        mode=PatchMode.REQUEST_EXTENSION.value,
        staging_id="a" * 16,
        actor="tester",
        target_pack_id="defaultspack",
    )

    result = manager.approve_request(created["request_id"], reviewer="reviewer")

    assert result["status"] == "applied"
    assert result["applied_pack_ids"] == ["new_pack"]
    assert calls[-1] == ("apply", "a" * 16, "replace", "reviewer")


def test_defaultspack_management_routes_are_fallback_http_routes():
    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    routes = {
        (spec.method, spec.pattern): spec.function_name
        for spec in canonical_http_route_specs(include_always_available=False)
    }

    assert routes[("GET", "/api/defaultspack/modules")] == "defaultspack:management_list_modules"
    assert routes[("GET", "/api/defaultspack/pack-requests")] == "defaultspack:pack_request_list"
    assert (
        routes[("GET", "/api/defaultspack/migration/status")]
        == "defaultspack:management_get_migration_status"
    )
