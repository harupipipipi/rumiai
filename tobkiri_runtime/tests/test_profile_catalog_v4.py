"""Security and projection tests for the Protocol v4 Profile catalog."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest

from core_runtime.profile_catalog_v4 import (
    bundle_lock_digest,
    profile_catalog_digest,
    project_profile_catalog,
    require_profile_catalog_binding,
)
from core_runtime.bootstrap.profile_capture import (
    capture_default_profile,
    prepare_default_profile_confirmation,
)
from core_runtime.runtime_surface_v4 import (
    RuntimeProfileChangeService,
    RuntimeSurfaceError,
    RuntimeSurfaceErrorCode,
    RuntimeSurfaceService,
)
from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog
from tobkiri_protocol.canonical import canonical_digest


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = RUNTIME_ROOT / "ecosystem" / "defaultspack" / "v4"


def _bundle_root() -> Path:
    return Path(os.environ["TOBKIRI_TEST_DEFAULTS_BUNDLE_ROOT"])


@pytest.fixture
def active_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(tmp_path / "user-data"))
    return capture_default_profile(confirmation=prepare_default_profile_confirmation())


def _catalog_with_second_profile(catalog: BundledCatalog) -> BundledCatalog:
    second = {
        **catalog.profiles["defaults"],
        "profile_id": "defaults.alternate",
        "display_name": "Tobkiri Alternate",
        "provenance": {
            **catalog.profiles["defaults"]["provenance"],
            "source_path": ("ecosystem/defaultspack/v4/defaults.alternate.profile.v4.json"),
        },
    }
    return replace(
        catalog,
        profiles={**catalog.profiles, "defaults.alternate": second},
    )


def test_multiple_profile_projection_has_exact_bindings_and_active_marker(
    active_runtime,
) -> None:
    catalog = _catalog_with_second_profile(BundledCatalog.load(_bundle_root()))

    projection = project_profile_catalog(catalog, active_runtime)

    assert projection["count"] == 2
    assert [item["profile_id"] for item in projection["profiles"]] == [
        "defaults",
        "defaults.alternate",
    ]
    active, candidate = projection["profiles"]
    assert active["active"] is True
    assert candidate["active"] is False
    assert candidate["available"] is True
    assert candidate["bindings"]["base"]["pack_id"] == "defaults-basepack"
    assert candidate["bindings"]["shell"]["provider_id"] == "shell.tauri.default"
    assert candidate["bindings"]["application"]["pack_id"] == ("runtime.tauri.application.default")
    assert {item["pack_id"] for item in candidate["pack_closure"]} >= {
        "defaults-basepack",
        "shell.tauri.default",
        "runtime.tauri.application.default",
    }
    assert candidate["authority_snapshot"]["state"] == "captured_on_resolve"
    assert candidate["candidate"]["state"] == "not_staged"


def test_catalog_refresh_exposes_new_profile_without_changing_active_pointer(
    active_runtime,
) -> None:
    base_catalog = BundledCatalog.load(_bundle_root())
    refreshed = _catalog_with_second_profile(base_catalog)
    service = RuntimeSurfaceService(
        snapshot_loader=lambda: active_runtime,
        catalog_loader=lambda: refreshed,
    )
    before_activation = dict(active_runtime.activation)

    result = service.read_profile_catalog()

    assert result["surface"] == "profiles"
    assert result["data"]["active_profile_id"] == "defaults"
    assert result["data"]["count"] == 2
    assert active_runtime.activation == before_activation


def test_catalog_binding_rejects_unknown_stale_and_tampered_profiles() -> None:
    catalog = BundledCatalog.load(_bundle_root())
    definition_digest = canonical_digest(catalog.profiles["defaults"])
    catalog_digest = profile_catalog_digest(catalog)
    lock_digest = bundle_lock_digest(catalog)

    assert (
        require_profile_catalog_binding(
            catalog,
            profile_id="defaults",
            expected_definition_digest=definition_digest,
            expected_catalog_digest=catalog_digest,
            expected_bundle_lock_digest=lock_digest,
        )["profile_id"]
        == "defaults"
    )

    invalid = (
        ("unknown", definition_digest, catalog_digest, lock_digest),
        ("defaults", "sha256:" + "0" * 64, catalog_digest, lock_digest),
        ("defaults", definition_digest, "sha256:" + "0" * 64, lock_digest),
        ("defaults", definition_digest, catalog_digest, "sha256:" + "0" * 64),
    )
    for profile_id, definition, catalog_value, lock_value in invalid:
        with pytest.raises(ValueError):
            require_profile_catalog_binding(
                catalog,
                profile_id=profile_id,
                expected_definition_digest=definition,
                expected_catalog_digest=catalog_value,
                expected_bundle_lock_digest=lock_value,
            )


def test_authoritative_resolve_binds_selected_catalog_profile(
    active_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _catalog_with_second_profile(BundledCatalog.load(_bundle_root()))
    service = RuntimeSurfaceService(
        snapshot_loader=lambda: active_runtime,
        catalog_loader=lambda: catalog,
    )
    projected = service.read_profile_catalog()["data"]
    candidate = projected["profiles"][1]
    captured: dict[str, object] = {}

    def resolve(pack_ids, **bindings):
        captured["pack_ids"] = pack_ids
        captured.update(bindings)
        selected = {
            **active_runtime.resolved.profile,
            "profile_id": "defaults.alternate",
        }
        return replace(active_runtime.resolved, profile=selected)

    monkeypatch.setattr(
        "core_runtime.pack_control_v4.resolve_profile_pack_set",
        resolve,
    )
    ceremony = RuntimeProfileChangeService(surface_service=service)
    result = ceremony.resolve(
        {
            "profile_id": "defaults.alternate",
            "expected_profile_revision": active_runtime.resolved.plan["profile_revision"],
            "expected_plan_digest": active_runtime.resolved.plan["plan_digest"],
            "desired_pack_ids": [
                item["pack_id"]
                for item in candidate["pack_closure"]
                if item["role"] not in {"base", "shell", "application"}
            ],
            "profile_definition_digest": candidate["definition"]["digest"],
            "profile_catalog_digest": projected["catalog_digest"],
            "bundle_lock_digest": projected["bundle_lock_digest"],
        },
        session_id="session-a",
    )

    assert result["state"] == "resolved"
    assert captured["profile_id"] == "defaults.alternate"
    assert captured["expected_profile_definition_digest"] == (candidate["definition"]["digest"])
    assert (
        result["review"]["catalog_binding"]["profile_catalog_digest"]
        == (projected["catalog_digest"])
    )


def test_non_default_resolve_without_catalog_binding_fails_closed(
    active_runtime,
) -> None:
    ceremony = RuntimeProfileChangeService(
        surface_service=RuntimeSurfaceService(
            snapshot_loader=lambda: active_runtime,
            catalog_loader=lambda: _catalog_with_second_profile(
                BundledCatalog.load(_bundle_root())
            ),
        )
    )
    with pytest.raises(RuntimeSurfaceError) as rejected:
        ceremony.resolve(
            {
                "profile_id": "defaults.alternate",
                "expected_profile_revision": active_runtime.resolved.plan["profile_revision"],
                "expected_plan_digest": active_runtime.resolved.plan["plan_digest"],
                "desired_pack_ids": ["defaultspack"],
            },
            session_id="session-a",
        )
    assert rejected.value.code is RuntimeSurfaceErrorCode.INVALID_REQUEST
