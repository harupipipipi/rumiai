from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _Approval:
    def __init__(self, approved: bool, reason: str = "not_found"):
        self.approved = approved
        self.reason = reason

    def is_pack_approved_and_verified(self, pack_id: str):
        return self.approved, None if self.approved else self.reason


def _write_staging_meta(tmp_path, staging_id, detected_pack_ids, changed_paths=None):
    staging_dir = tmp_path / "staging" / staging_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "staging_id": staging_id,
        "detected_pack_ids": detected_pack_ids,
        "changed_paths": list(changed_paths or []),
        "is_multi_pack": False,
    }
    (staging_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


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


def test_stale_web_mount_stops_matching_after_pack_revoked():
    from core_runtime.pack_api_server import PackAPIHandler

    approval = _Approval(True)
    old_manager = PackAPIHandler.approval_manager
    old_mounts = list(PackAPIHandler._web_mounts)
    PackAPIHandler.approval_manager = approval
    PackAPIHandler._web_mounts = [
        {
            "path_prefix": "/stale",
            "web_root": Path("/tmp/stale-pack/web"),
            "spa_fallback": False,
            "auth_required": False,
            "pack_id": "stale_pack",
        }
    ]
    try:
        handler = object.__new__(PackAPIHandler)
        assert handler._match_web_mount("/stale/index.html") is not None

        approval.approved = False
        approval.reason = "not_approved"

        assert handler._match_web_mount("/stale/index.html") is None
    finally:
        PackAPIHandler.approval_manager = old_manager
        PackAPIHandler._web_mounts = old_mounts


def test_stale_web_mount_direct_serve_rechecks_hash_state():
    from core_runtime.pack_api_server import PackAPIHandler

    approval = _Approval(False, reason="hash_mismatch")
    old_manager = PackAPIHandler.approval_manager
    PackAPIHandler.approval_manager = approval
    try:
        handler = object.__new__(PackAPIHandler)
        sent = []
        handler._send_response = lambda response, status=200: sent.append((status, response))

        handler._serve_static_file(
            "/stale/index.html",
            {
                "path_prefix": "/stale",
                "web_root": Path("/tmp/stale-pack/web"),
                "spa_fallback": False,
                "auth_required": False,
                "pack_id": "stale_pack",
            },
        )

        assert sent[0][0] == 403
    finally:
        PackAPIHandler.approval_manager = old_manager


def test_stale_pre_auth_entry_stops_skipping_auth_after_revoke():
    from core_runtime.pack_api_server import PackAPIHandler

    approval = _Approval(True)
    old_manager = PackAPIHandler.approval_manager
    old_table = list(PackAPIHandler._pre_auth_table)
    PackAPIHandler.approval_manager = approval
    PackAPIHandler._pre_auth_table = [
        {
            "method": "GET",
            "path_prefix": "/api/stale",
            "pack_id": "stale_pack",
        }
    ]
    try:
        handler = object.__new__(PackAPIHandler)
        assert handler._is_pre_auth_route("GET", "/api/stale/status") is True

        approval.approved = False
        approval.reason = "not_approved"

        assert handler._is_pre_auth_route("GET", "/api/stale/status") is False
    finally:
        PackAPIHandler.approval_manager = old_manager
        PackAPIHandler._pre_auth_table = old_table


def test_stale_pre_auth_entry_stops_skipping_auth_after_hash_change():
    from core_runtime.pack_api_server import PackAPIHandler

    approval = _Approval(False, reason="hash_mismatch")
    old_manager = PackAPIHandler.approval_manager
    old_table = list(PackAPIHandler._pre_auth_table)
    PackAPIHandler.approval_manager = approval
    PackAPIHandler._pre_auth_table = [
        {
            "method": "POST",
            "path": "/api/stale/complete",
            "pack_id": "stale_pack",
        }
    ]
    try:
        handler = object.__new__(PackAPIHandler)

        assert handler._is_pre_auth_route("POST", "/api/stale/complete") is False
    finally:
        PackAPIHandler.approval_manager = old_manager
        PackAPIHandler._pre_auth_table = old_table


def test_function_registry_trusts_manifest_entrypoint_file(tmp_path):
    from tests.legacy_authority_contracts import (
        assert_profile_resolver_requires_authority_snapshot,
        assert_retired_module_absent,
    )
    from tests.v4_batch_support import assert_payload_mutations_denied, harness

    assert_retired_module_absent("core_runtime.function_registry")
    assert_profile_resolver_requires_authority_snapshot()
    assert_payload_mutations_denied(harness(tmp_path))


def test_function_registry_rejects_escaping_entrypoint(tmp_path):
    from tests.legacy_authority_contracts import (
        assert_profile_resolver_requires_authority_snapshot,
        assert_retired_module_absent,
    )
    from tests.v4_batch_support import assert_payload_mutations_denied, harness

    assert_retired_module_absent("core_runtime.function_registry")
    assert_profile_resolver_requires_authority_snapshot()
    assert_payload_mutations_denied(harness(tmp_path))


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


def test_pack_apply_revalidates_pack_id_from_staging_meta(tmp_path):
    from core_runtime.pack_applier import PackApplier

    staging_id = "a" * 16
    staging_root = tmp_path / "staging"
    staging_dir = staging_root / staging_id
    payload_dir = staging_dir / "payload"
    pack_dir = payload_dir / "safe_pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "ecosystem.json").write_text(
        json.dumps(
            {
                "pack_id": "safe_pack",
                "version": "1.0.0",
                "metadata": {"name": "Safe Pack"},
            }
        ),
        encoding="utf-8",
    )
    (staging_dir / "meta.json").write_text(
        json.dumps(
            {
                "staging_id": staging_id,
                "detected_pack_ids": ["../escape"],
                "is_multi_pack": False,
            }
        ),
        encoding="utf-8",
    )

    result = PackApplier(
        ecosystem_dir=str(tmp_path / "ecosystem"),
        backup_root=str(tmp_path / "backups"),
        staging_root=str(staging_root),
    ).apply(staging_id)

    assert result.success is False
    assert "Invalid pack_id" in (result.error or "")
    assert not (tmp_path / "escape").exists()


def test_pack_applier_audits_apply_actor(monkeypatch, tmp_path):
    from core_runtime.pack_applier import PackApplier

    staging_id = "a" * 16
    staging_root = tmp_path / "staging"
    staging_dir = staging_root / staging_id
    pack_dir = staging_dir / "payload" / "safe_pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "ecosystem.json").write_text(
        json.dumps(
            {
                "pack_id": "safe_pack",
                "version": "1.0.0",
                "metadata": {"name": "Safe Pack"},
            }
        ),
        encoding="utf-8",
    )
    (staging_dir / "meta.json").write_text(
        json.dumps(
            {
                "staging_id": staging_id,
                "detected_pack_ids": ["safe_pack"],
                "is_multi_pack": False,
            }
        ),
        encoding="utf-8",
    )
    audit_events = []

    class _Audit:
        def log_system_event(self, **kwargs):
            audit_events.append(kwargs)

    monkeypatch.setattr(
        "core_runtime.audit_logger.get_audit_logger",
        lambda: _Audit(),
    )
    monkeypatch.setattr(
        "core_runtime.approval_manager.get_approval_manager",
        lambda: SimpleNamespace(mark_modified=lambda _pack_id: None),
    )

    result = PackApplier(
        ecosystem_dir=str(tmp_path / "ecosystem"),
        backup_root=str(tmp_path / "backups"),
        staging_root=str(staging_root),
    ).apply(staging_id, actor="profile:work__surface:mobile")

    assert result.success is True
    assert [event["event_type"] for event in audit_events] == [
        "pack_apply_started",
        "pack_apply_completed",
    ]
    assert all(
        event["details"]["actor"] == "profile:work__surface:mobile"
        for event in audit_events
    )


def test_defaultspack_management_aliases_do_not_need_runtime_registry(monkeypatch):
    pack_root = Path(__file__).resolve().parent.parent / "ecosystem" / "defaultspack"
    monkeypatch.syspath_prepend(str(pack_root))

    from core_runtime.di_container import reset_container
    from domain.function_runtime.dispatcher import run_defaultspack_function

    reset_container()
    result = run_defaultspack_function(
        "pack_request_list",
        {},
        {"pack_id": "defaultspack"},
    )

    assert result["status"] == "ok"
    assert "requests" in result["data"]


def test_extension_manager_rejects_unsafe_request_ids(tmp_path):
    from ecosystem.defaultspack.backend.pack_extension.extension_manager import ExtensionManager

    manager = ExtensionManager(
        requests_root=tmp_path / "requests",
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
        staging_root=tmp_path / "staging",
    )

    with pytest.raises(ValueError):
        manager._request_path("../outside")

    safe_path = manager._request_path("req_" + "a" * 16)
    safe_path.resolve().relative_to((tmp_path / "requests").resolve())
    assert manager.get_request("../outside")["status_code"] == 400
    assert manager.approve_request("../outside")["status_code"] == 400
    assert manager.rollback_request("../outside")["status_code"] == 400


def test_extension_manager_rejects_mismatched_request_file_id(tmp_path):
    from ecosystem.defaultspack.backend.pack_extension.extension_manager import ExtensionManager

    requests_root = tmp_path / "requests"
    requests_root.mkdir()
    (requests_root / ("req_" + "a" * 16 + ".json")).write_text(
        json.dumps(
            {
                "request_id": "../outside",
                "mode": "request_extension",
                "actor": "tester",
                "target_pack_id": "safe_pack",
                "notes": "bad",
            }
        ),
        encoding="utf-8",
    )
    manager = ExtensionManager(
        requests_root=requests_root,
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
        staging_root=tmp_path / "staging",
    )

    result = manager.get_request("req_" + "a" * 16)

    assert result["status_code"] == 404


def test_rollback_revalidates_applied_pack_ids(tmp_path):
    from ecosystem.defaultspack.backend.pack_extension.extension_manager import (
        ExtensionManager,
        ExtensionRequest,
        PatchMode,
    )

    outside = tmp_path / "escape"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    manager = ExtensionManager(
        requests_root=tmp_path / "requests",
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
        staging_root=tmp_path / "staging",
    )
    request = ExtensionRequest(
        request_id="req_" + "a" * 16,
        mode=PatchMode.REQUEST_EXTENSION,
        pack_id="tester",
        target_pack_id="safe_pack",
        summary="bad rollback",
        status="applied",
        applied_pack_ids=["../escape"],
    )
    manager._write_request(request)

    result = manager.rollback_request(request.request_id)

    assert result["status_code"] == 400
    assert "Invalid pack_id" in result["error"]
    assert (outside / "keep.txt").exists()


def test_create_pack_request_snapshots_staging_meta(tmp_path):
    from ecosystem.defaultspack.backend.pack_extension.extension_manager import (
        ExtensionManager,
        PatchMode,
    )

    staging_id = "a" * 16
    _write_staging_meta(tmp_path, staging_id, ["nice_pack"], ["ecosystem.json"])
    manager = ExtensionManager(
        requests_root=tmp_path / "requests",
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
        staging_root=tmp_path / "staging",
    )

    created = manager.create_pack_request(
        mode=PatchMode.REQUEST_EXTENSION.value,
        staging_id=staging_id,
        actor="tester",
        target_pack_id="nice_pack",
    )

    assert created["request_id"] == "req_" + staging_id
    assert created["detected_pack_ids"] == ["nice_pack"]
    assert created["changed_paths"] == ["ecosystem.json"]
    assert len(created["staging_meta_sha256"]) == 64


def test_create_pack_request_rejects_target_pack_mismatch(tmp_path):
    from ecosystem.defaultspack.backend.pack_extension.extension_manager import (
        ExtensionManager,
        PatchMode,
    )

    staging_id = "a" * 16
    _write_staging_meta(tmp_path, staging_id, ["nice_pack"])
    manager = ExtensionManager(
        requests_root=tmp_path / "requests",
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
        staging_root=tmp_path / "staging",
    )

    result = manager.create_pack_request(
        mode=PatchMode.REQUEST_EXTENSION.value,
        staging_id=staging_id,
        actor="tester",
        target_pack_id="evil_pack",
    )

    assert result["status_code"] == 400
    assert "target_pack_id" in result["error"]


def test_approve_request_rechecks_staging_meta_before_apply(monkeypatch, tmp_path):
    from ecosystem.defaultspack.backend.pack_extension.extension_manager import (
        ExtensionManager,
        PatchMode,
    )

    staging_id = "a" * 16
    _write_staging_meta(tmp_path, staging_id, ["nice_pack"])
    calls = []

    class _Applier:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def apply(self, staging_id, *, mode="replace", actor="api_user"):
            calls.append(("apply", staging_id, mode, actor))
            raise AssertionError("apply should not run after staging metadata changes")

    monkeypatch.setattr("core_runtime.pack_applier.PackApplier", _Applier)
    manager = ExtensionManager(
        requests_root=tmp_path / "requests",
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
        staging_root=tmp_path / "staging",
    )
    created = manager.create_pack_request(
        mode=PatchMode.REQUEST_EXTENSION.value,
        staging_id=staging_id,
        actor="tester",
        target_pack_id="nice_pack",
    )
    _write_staging_meta(tmp_path, staging_id, ["evil_pack"])

    result = manager.approve_request(created["request_id"], reviewer="reviewer")

    assert result["status_code"] == 409
    assert "staging metadata changed" in result["error"]
    assert calls == []


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
        def __init__(self, *, ecosystem_dir, backup_root, staging_root):
            calls.append(("init", ecosystem_dir, backup_root, staging_root))

        def apply(self, staging_id, *, mode="replace", actor="api_user"):
            calls.append(("apply", staging_id, mode, actor))
            return _ApplyResult()

    monkeypatch.setattr("core_runtime.pack_applier.PackApplier", _Applier)
    _write_staging_meta(tmp_path, "a" * 16, ["new_pack"])
    manager = ExtensionManager(
        requests_root=tmp_path / "requests",
        ecosystem_dir=tmp_path / "ecosystem",
        backup_root=tmp_path / "backups",
        staging_root=tmp_path / "staging",
    )
    created = manager.create_pack_request(
        mode=PatchMode.REQUEST_EXTENSION.value,
        staging_id="a" * 16,
        actor="tester",
        target_pack_id="new_pack",
    )

    result = manager.approve_request(created["request_id"], reviewer="reviewer")

    assert result["status"] == "applied"
    assert result["applied_pack_ids"] == ["new_pack"]
    assert calls[0] == (
        "init",
        str(tmp_path / "ecosystem"),
        str(tmp_path / "backups"),
        str(tmp_path / "staging"),
    )
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
