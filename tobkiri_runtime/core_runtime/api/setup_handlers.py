"""Canonical Defaults Profile v4 setup HTTP handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog

class SetupHandlersMixin:
    """Expose one finite setup transaction with no legacy Registry authority."""

    @staticmethod
    def _recommended_default_profile_preview() -> Dict[str, Any]:
        """Return the exact integrity-checked Defaults Profile selection."""

        bundle_root = (
            Path(__file__).resolve().parents[2]
            / "ecosystem"
            / "defaultspack"
            / "v4"
        )
        catalog = BundledCatalog.load(bundle_root)
        profile = catalog.profiles["defaults"]
        base = profile["base"]
        shell = profile["shell"]
        selected = profile["packs"]
        pack_ids = [str(item["pack_id"]) for item in selected]
        if (
            base["pack_id"] != "defaults-basepack"
            or shell["provider_id"] != "shell.tauri.default"
            or len(pack_ids) != len(set(pack_ids))
            or any(pack_id not in catalog.packs for pack_id in pack_ids)
        ):
            raise ValueError("Defaults Profile selection is not exact")
        conversation_edges = [
            edge
            for edge in profile["requested_edges"]
            if edge["contract_id"] == "conversation.turn.v1"
        ]
        if len(conversation_edges) != 1:
            raise ValueError(
                "Defaults Profile must select exactly one conversation provider"
            )
        return {
            "available": True,
            "profile_id": "defaults",
            "name": str(profile.get("display_name") or "Tobkiri Defaults"),
            "base_pack": "defaults-basepack",
            "shell": {
                "provider_id": "shell.tauri.default",
                "contract_id": "app.shell.v1",
            },
            "pack_ids": pack_ids,
            "packs": [
                {
                    "pack_id": pack_id,
                    "display_name": str(
                        catalog.packs[pack_id]["pack"]["display_name"]
                    ),
                }
                for pack_id in pack_ids
            ],
            "conversation_provider": str(
                conversation_edges[0]["target_provider_id"]
            ),
        }

    def _setup_list_packs(self) -> Dict[str, Any]:
        """Return the sole canonical setup candidate and its typed state."""

        preview = self._recommended_default_profile_preview()
        return {
            "setup_api_version": "io.tobkiri.setup-state.v4",
            "state": "review_required",
            "packs": preview["packs"],
            "recommended_default_profile": preview,
            "required_transaction": [
                "catalog.verify",
                "profile.resolve",
                "authority.snapshot",
                "activation.prepare",
                "activation.commit",
                "runtime.capture",
            ],
        }

    def _setup_install_pack(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Complete the explicitly confirmed Defaults v4 activation transaction."""

        if body.get("install_defaults_profile") is not True:
            return self._retired_state()
        preview = self._recommended_default_profile_preview()
        reviewed = [
            str(pack_id)
            for pack_id in body.get("reviewed_default_profile_pack_ids") or []
        ]
        if reviewed != preview["pack_ids"]:
            return {
                "error": "Defaults Profile review is missing or stale",
                "status_code": 409,
                "state": "review_required",
                "required_pack_ids": preview["pack_ids"],
            }
        if body.get("confirmed_defaults_profile") is not True:
            return {
                "error": "Defaults Profile requires explicit confirmation",
                "status_code": 409,
                "state": "confirmation_required",
            }
        from ..bootstrap.profile_capture import capture_default_profile

        active = capture_default_profile()
        return {
            "success": True,
            "setup_api_version": "io.tobkiri.setup-state.v4",
            "state": "active",
            "profile_id": active.resolved.profile["profile_id"],
            "profile_revision": active.resolved.plan["profile_revision"],
            "plan_digest": active.resolved.plan["plan_digest"],
            "activation_id": active.activation["activation_id"],
            "security_epoch": active.activation["security_epoch"],
            "fencing_token": active.activation["fencing_token"],
            "restart_required": False,
        }

    @staticmethod
    def _retired_state() -> Dict[str, Any]:
        return {
            "error": "Legacy setup-pack authority is retired; activate Defaults v4",
            "status_code": 410,
            "state": "legacy_setup_retired",
            "action": "install_defaults_profile",
        }

    @classmethod
    def _retired_setup_complete_state(cls) -> Dict[str, Any]:
        """Return the no-write contract for the retired setup completion route."""

        return {
            **cls._retired_state(),
            "setup_api_version": "io.tobkiri.setup-state.v4",
            "retired_route": "/api/setup/complete",
            "write_set": [],
        }

    def _setup_grant_all_ok(self, _setup_pack_id: str) -> Dict[str, Any]:
        """Reject the retired blanket approval surface."""

        return self._retired_state()

    def _setup_revoke_all_ok(self, _setup_pack_id: str) -> Dict[str, Any]:
        """Reject the retired blanket approval surface."""

        return self._retired_state()

    def _setup_get_migration_status(self) -> Dict[str, Any]:
        """Report that legacy executable migration is not a runtime operation."""

        return self._retired_state()


__all__ = ["SetupHandlersMixin"]
