"""Fail-closed contract for the retired mutable Startup Profile registry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core_runtime.startup_profiles import StartupProfileManager


def _active() -> object:
    return SimpleNamespace(
        activation={"activation_id": "activation:defaults-test"},
        resolved=SimpleNamespace(
            profile={
                "profile_id": "defaults",
                "profile_api_version": "io.tobkiri.profile.v4",
                "catalog_revision": "sha256:" + "1" * 64,
            },
            lock={
                "effective_set": [
                    {
                        "role": "base",
                        "identity": "defaults-basepack",
                        "artifact_digest": "sha256:" + "2" * 64,
                    }
                ]
            },
            plan={
                "profile_revision": "sha256:" + "3" * 64,
                "plan_digest": "sha256:" + "4" * 64,
                "security_epoch": 1,
                "base": {"pack_id": "defaults-basepack"},
                "shell": {"provider_id": "shell.tauri.default"},
            },
        ),
    )


def test_facade_lists_only_verified_v4_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core_runtime.bootstrap.profile_capture.capture_default_profile",
        lambda: _active(),
    )

    payload = StartupProfileManager().list_profiles_payload()

    assert payload["active_profile_id"] == "defaults"
    assert payload["profile_authority"] == "io.tobkiri.profile.v4"
    assert payload["profiles"][0]["activation_id"] == "activation:defaults-test"
    assert payload["profiles"][0]["immutable"] is True


def test_facade_exposes_confirmation_candidate_without_creating_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core_runtime.bootstrap.profile_capture.capture_default_profile",
        lambda: (_ for _ in ()).throw(RuntimeError("not active")),
    )
    monkeypatch.setattr(
        "core_runtime.bootstrap.profile_capture.prepare_default_profile_confirmation",
        lambda: {
            "profile_id": "defaults",
            "profile_revision": "sha256:" + "3" * 64,
            "plan_digest": "sha256:" + "4" * 64,
            "base": {"pack_id": "defaults-basepack"},
            "shell": {"provider_id": "shell.tauri.default"},
        },
    )

    payload = StartupProfileManager().list_profiles_payload()

    assert payload["profiles"] == []
    assert payload["active_profile_id"] is None
    assert payload["candidate"]["status"] == "confirmation_required"


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_profile", ({},)),
        ("update_profile", ("defaults", {})),
        ("delete_profile", ("defaults",)),
        ("duplicate_profile", ("defaults",)),
        ("launch_profile", ("defaults",)),
        ("compile_profile_preview", ("defaults", {})),
        ("add_pack", ("defaults", "example.pack")),
        ("remove_pack", ("defaults", "example.pack")),
        ("set_node_override", ("defaults", "port", "node")),
        ("clear_node_override", ("defaults", "port")),
    ],
)
def test_legacy_mutations_are_typed_retired(method: str, args: tuple[object, ...]) -> None:
    result = getattr(StartupProfileManager(), method)(*args)

    assert result["status_code"] == 410
    assert result["code"] == "LEGACY_STARTUP_PROFILE_RETIRED"


def test_activate_requires_exact_defaults_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = StartupProfileManager()
    assert manager.activate_profile("other")["status_code"] == 404
    monkeypatch.setattr(
        "core_runtime.bootstrap.profile_capture.capture_default_profile",
        lambda: (_ for _ in ()).throw(RuntimeError("not active")),
    )
    result = manager.activate_profile("defaults")
    assert result["status_code"] == 409
    assert result["code"] == "PROFILE_CONFIRMATION_REQUIRED"
