"""Tests for the sole live Defaults Profile v4 setup transaction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from core_runtime.api.setup_handlers import SetupHandlersMixin


class _Handler(SetupHandlersMixin):
    pass


def _preview() -> dict[str, object]:
    return {
        "available": True,
        "profile_id": "defaults",
        "name": "Tobkiri Defaults",
        "base_pack": "defaults-basepack",
        "shell": {
            "provider_id": "shell.tauri.default",
            "contract_id": "app.shell.v1",
        },
        "pack_ids": ["defaultspack", "provider.local"],
        "packs": [
            {"pack_id": "defaultspack", "display_name": "Tobkiri"},
            {"pack_id": "provider.local", "display_name": "Local Provider"},
        ],
        "conversation_provider": "provider.local",
    }


def _active() -> SimpleNamespace:
    return SimpleNamespace(
        resolved=SimpleNamespace(
            profile={"profile_id": "defaults"},
            plan={
                "profile_revision": "profile-revision:test",
                "plan_digest": "sha256:" + "1" * 64,
            },
        ),
        activation={
            "activation_id": "activation:test",
            "security_epoch": 7,
            "fencing_token": 11,
        },
    )


def test_setup_lists_one_typed_finite_v4_transaction() -> None:
    with patch.object(
        SetupHandlersMixin,
        "_recommended_default_profile_preview",
        return_value=_preview(),
    ):
        result = _Handler()._setup_list_packs()

    assert result["setup_api_version"] == "io.tobkiri.setup-state.v4"
    assert result["state"] == "review_required"
    assert result["recommended_default_profile"] == _preview()
    assert result["required_transaction"] == [
        "catalog.verify",
        "profile.resolve",
        "authority.snapshot",
        "activation.prepare",
        "activation.commit",
        "runtime.capture",
    ]


def test_setup_requires_exact_reviewed_profile() -> None:
    with patch.object(
        SetupHandlersMixin,
        "_recommended_default_profile_preview",
        return_value=_preview(),
    ):
        result = _Handler()._setup_install_pack(
            {
                "install_defaults_profile": True,
                "reviewed_default_profile_pack_ids": ["defaultspack"],
                "confirmed_defaults_profile": True,
            }
        )

    assert result["status_code"] == 409
    assert result["state"] == "review_required"
    assert result["required_pack_ids"] == _preview()["pack_ids"]


def test_setup_requires_explicit_confirmation() -> None:
    with patch.object(
        SetupHandlersMixin,
        "_recommended_default_profile_preview",
        return_value=_preview(),
    ):
        result = _Handler()._setup_install_pack(
            {
                "install_defaults_profile": True,
                "reviewed_default_profile_pack_ids": _preview()["pack_ids"],
            }
        )

    assert result["status_code"] == 409
    assert result["state"] == "confirmation_required"


def test_setup_completes_canonical_capture_without_restart() -> None:
    with (
        patch.object(
            SetupHandlersMixin,
            "_recommended_default_profile_preview",
            return_value=_preview(),
        ),
        patch(
            "core_runtime.api.setup_handlers.capture_default_profile",
            return_value=_active(),
        ) as capture,
    ):
        result = _Handler()._setup_install_pack(
            {
                "install_defaults_profile": True,
                "reviewed_default_profile_pack_ids": _preview()["pack_ids"],
                "confirmed_defaults_profile": True,
            }
        )

    capture.assert_called_once_with()
    assert result == {
        "success": True,
        "setup_api_version": "io.tobkiri.setup-state.v4",
        "state": "active",
        "profile_id": "defaults",
        "profile_revision": "profile-revision:test",
        "plan_digest": "sha256:" + "1" * 64,
        "activation_id": "activation:test",
        "security_epoch": 7,
        "fencing_token": 11,
        "restart_required": False,
    }


def test_non_v4_install_shape_is_retired_without_capture() -> None:
    with patch(
        "core_runtime.api.setup_handlers.capture_default_profile"
    ) as capture:
        result = _Handler()._setup_install_pack({"setup_pack_ids": ["legacy"]})

    capture.assert_not_called()
    assert result["status_code"] == 410
    assert result["state"] == "legacy_setup_retired"


def test_second_approval_and_runtime_migration_surfaces_are_retired() -> None:
    handler = _Handler()
    for result in (
        handler._setup_grant_all_ok("legacy"),
        handler._setup_revoke_all_ok("legacy"),
        handler._setup_get_migration_status(),
    ):
        assert result["status_code"] == 410
        assert result["state"] == "legacy_setup_retired"


def test_real_preview_is_exact_and_integrity_checked() -> None:
    preview = SetupHandlersMixin._recommended_default_profile_preview()

    assert preview["profile_id"] == "defaults"
    assert preview["base_pack"] == "defaults-basepack"
    assert preview["shell"]["provider_id"] == "shell.tauri.default"
    assert len(preview["pack_ids"]) == len(set(preview["pack_ids"]))
    assert preview["conversation_provider"]
