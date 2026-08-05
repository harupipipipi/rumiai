"""Typed retirement facade for the removed legacy Startup Profile registry.

Production Profile authority is the finite Profile v4 activation captured by
``bootstrap.profile_capture``.  This module exists temporarily so old panel
routes fail with an explicit migration response instead of recreating mutable
``startup_profiles.json`` state.
"""

from __future__ import annotations

from typing import Any, Mapping


_RETIRED_CODE = "LEGACY_STARTUP_PROFILE_RETIRED"


def _retired(operation: str) -> dict[str, Any]:
    return {
        "error": "Legacy Startup Profile mutation is retired; use Profile v4 activation",
        "code": _RETIRED_CODE,
        "operation": operation,
        "status_code": 410,
    }


def _profile_payload(active: Any) -> dict[str, Any]:
    profile = active.resolved.profile
    lock = active.resolved.lock
    plan = active.resolved.plan
    return {
        "profile_id": str(profile["profile_id"]),
        "profile_api_version": str(profile["profile_api_version"]),
        "catalog_revision": str(profile["catalog_revision"]),
        "profile_revision": str(plan["profile_revision"]),
        "plan_digest": str(plan["plan_digest"]),
        "activation_id": str(active.activation["activation_id"]),
        "security_epoch": int(plan["security_epoch"]),
        "base": dict(plan["base"]),
        "shell": dict(plan["shell"]),
        "effective_set": [dict(item) for item in lock["effective_set"]],
        "status": "active",
        "immutable": True,
    }


class StartupProfileManager:
    """Read the v4 Profile or reject every legacy mutation deterministically."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def list_profiles_payload(self) -> dict[str, Any]:
        from .bootstrap.profile_capture import (
            capture_default_profile,
            prepare_default_profile_confirmation,
        )

        try:
            active = capture_default_profile()
        except Exception:
            confirmation = prepare_default_profile_confirmation()
            return {
                "profiles": [],
                "active_profile_id": None,
                "candidate": {
                    "profile_id": str(confirmation["profile_id"]),
                    "profile_revision": str(confirmation["profile_revision"]),
                    "plan_digest": str(confirmation["plan_digest"]),
                    "base": dict(confirmation["base"]),
                    "shell": dict(confirmation["shell"]),
                    "status": "confirmation_required",
                },
                "profile_authority": "io.tobkiri.profile.v4",
            }
        payload = _profile_payload(active)
        return {
            "profiles": [payload],
            "active_profile_id": payload["profile_id"],
            "profile_authority": "io.tobkiri.profile.v4",
        }

    def activate_profile(self, profile_id: str) -> dict[str, Any]:
        if str(profile_id).strip() != "defaults":
            return {
                "error": "Only the canonical defaults Profile is bundled",
                "code": "PROFILE_NOT_FOUND",
                "profile_id": str(profile_id),
                "status_code": 404,
            }
        try:
            from .bootstrap.profile_capture import capture_default_profile

            active = capture_default_profile()
        except Exception:
            return {
                "error": "Explicit digest-bound Defaults confirmation is required",
                "code": "PROFILE_CONFIRMATION_REQUIRED",
                "profile_id": "defaults",
                "status_code": 409,
            }
        return _profile_payload(active)

    def create_profile(self, body: Mapping[str, Any]) -> dict[str, Any]:
        del body
        return _retired("create")

    def update_profile(
        self,
        profile_id: str,
        body: Mapping[str, Any],
    ) -> dict[str, Any]:
        del profile_id, body
        return _retired("update")

    def delete_profile(self, profile_id: str) -> dict[str, Any]:
        del profile_id
        return _retired("delete")

    def duplicate_profile(self, profile_id: str) -> dict[str, Any]:
        del profile_id
        return _retired("duplicate")

    def launch_profile(self, profile_id: str) -> dict[str, Any]:
        del profile_id
        return _retired("launch")

    def compile_profile_preview(
        self,
        profile_id: str,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del profile_id, body
        return _retired("compile_preview")

    def add_pack(self, profile_id: str, pack_id: str) -> dict[str, Any]:
        del profile_id, pack_id
        return _retired("pack_add")

    def remove_pack(self, profile_id: str, pack_id: str) -> dict[str, Any]:
        del profile_id, pack_id
        return _retired("pack_remove")

    def set_node_override(
        self,
        profile_id: str,
        port_key: str,
        node_id: str,
    ) -> dict[str, Any]:
        del profile_id, port_key, node_id
        return _retired("node_override_set")

    def clear_node_override(
        self,
        profile_id: str,
        port_key: str,
    ) -> dict[str, Any]:
        del profile_id, port_key
        return _retired("node_override_clear")


__all__ = ["StartupProfileManager"]
