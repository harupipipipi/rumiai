"""setup HTTP handlers."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict

from ..di_container import get_container
from ..pack_function_runtime import invoke_pack_function
from ..setup_pack import get_setup_pack_manager


logger = logging.getLogger(__name__)


class SetupHandlersMixin:
    def _refresh_runtime_pack_approvals(self) -> None:
        """Reload approvals written by a setup-pack install into this kernel.

        The setup-pack manager and the running API server may own different
        ApprovalManager instances.  The install transaction already performed
        the user-confirmed approval; this only makes the persisted result
        visible to the current kernel without requiring a restart.
        """
        kernel = getattr(self, "kernel", None)
        approval_manager = getattr(self, "approval_manager", None) or getattr(
            kernel, "approval_manager", None
        )
        initialize = getattr(approval_manager, "initialize", None)
        if callable(initialize):
            initialize()

    @staticmethod
    def _pack_function_state(pack_id: str, function_id: str) -> Dict[str, Any]:
        if not pack_id:
            return {
                "exists": False,
                "registry_available": False,
                "reason": "pack_id_missing",
            }
        function_registry = get_container().get_or_none("function_registry")
        if function_registry is None:
            return {
                "exists": False,
                "registry_available": False,
                "reason": "function_registry_unavailable",
            }
        qualified_name = (
            function_id if ":" in function_id else f"{pack_id}:{function_id}"
        )
        if function_registry.get(qualified_name) is None:
            return {
                "exists": False,
                "registry_available": True,
                "reason": "function_not_registered",
            }
        return {
            "exists": True,
            "registry_available": True,
            "reason": None,
        }

    @classmethod
    def _pack_function_exists(cls, pack_id: str, function_id: str) -> bool:
        return bool(cls._pack_function_state(pack_id, function_id).get("exists"))

    def _get_pack_migration_status(self, pack_id: str) -> Dict[str, Any]:
        if not pack_id:
            return {
                "pack_id": None,
                "available": False,
                "needs_user_migration": False,
                "registry_available": False,
                "reason": "pack_id_missing",
            }
        function_state = self._pack_function_state(pack_id, "get_migration_status")
        if not function_state.get("exists"):
            return {
                "pack_id": pack_id,
                "available": False,
                "needs_user_migration": False,
                "registry_available": bool(function_state.get("registry_available")),
                "reason": function_state.get("reason"),
            }
        status = invoke_pack_function(pack_id, "get_migration_status")
        payload = dict(status) if isinstance(status, dict) else {"result": status}
        payload.setdefault("needs_user_migration", False)
        payload["pack_id"] = pack_id
        payload["available"] = True
        payload["registry_available"] = True
        payload["reason"] = None
        return payload

    def _setup_list_packs(self) -> Dict[str, Any]:
        result = self._normalize_setup_pack_selection_payload(
            get_setup_pack_manager().list_packs()
        )
        result["recommended_default_profile"] = (
            self._recommended_default_profile_preview()
        )
        result["review_revision"] = self._setup_pack_review_revision(result.get("packs"))
        return result

    @staticmethod
    def _recommended_default_profile_preview() -> Dict[str, Any]:
        """Describe the exact, integrity-checked Defaults Profile v4 set."""
        try:
            from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog

            bundle_root = (
                Path(__file__).resolve().parents[2]
                / "ecosystem"
                / "defaultspack"
                / "v4"
            )
            catalog = BundledCatalog.load(bundle_root)
            profile = catalog.profiles.get("defaults")
            if not isinstance(profile, dict):
                raise ValueError("Defaults Profile is absent from the v4 catalog")

            base = profile.get("base")
            shell = profile.get("shell")
            if not isinstance(base, dict) or base.get("pack_id") != "defaults-basepack":
                raise ValueError("Defaults Profile has an unexpected Base")
            if "defaults-basepack" not in catalog.bases:
                raise ValueError("Defaults Base artifact is absent from the v4 catalog")
            if (
                not isinstance(shell, dict)
                or shell.get("provider_id") != "shell.tauri.default"
                or shell.get("contract_id") != "app.shell.v1"
                or "shell.tauri.default" not in catalog.shells
            ):
                raise ValueError("Defaults Profile has an unexpected Shell")

            selected = profile.get("packs")
            if not isinstance(selected, list):
                raise ValueError("Defaults Profile Pack set is invalid")
            pack_ids = [
                str(item.get("pack_id") or "").strip()
                for item in selected
                if isinstance(item, dict)
            ]
            if (
                len(pack_ids) != len(selected)
                or len(pack_ids) != len(set(pack_ids))
                or any(pack_id not in catalog.packs for pack_id in pack_ids)
            ):
                raise ValueError("Defaults Profile Pack set is not exact")

            requested_edges = profile.get("requested_edges")
            conversation_edges = [
                edge
                for edge in requested_edges
                if isinstance(edge, dict)
                and edge.get("contract_id") == "conversation.turn.v1"
            ] if isinstance(requested_edges, list) else []
            if len(conversation_edges) != 1:
                raise ValueError(
                    "Defaults Profile must select exactly one conversation provider"
                )

            definitions = get_setup_pack_manager().list_packs().get("packs") or []
            by_target_id = {
                str(item.get("target_pack_id") or item.get("pack_id") or "").strip():
                    item
                for item in definitions
                if isinstance(item, dict)
                and SetupHandlersMixin._is_official_bundled_setup_pack(item)
                and not item.get("schema_issues")
                if str(item.get("target_pack_id") or item.get("pack_id") or "").strip()
            }
            missing = [pack_id for pack_id in pack_ids if pack_id not in by_target_id]
            if missing:
                raise ValueError(
                    "Defaults Profile setup definitions are missing: "
                    + ", ".join(missing)
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
                            by_target_id.get(pack_id, {}).get("display_name")
                            or pack_id
                        ),
                    }
                    for pack_id in pack_ids
                ],
                "conversation_provider": str(
                    conversation_edges[0].get("target_provider_id") or ""
                ),
            }
        except Exception as exc:
            logger.warning("Unable to preview Defaults Profile", exc_info=True)
            return {
                "available": False,
                "profile_id": "defaults",
                "name": "Tobkiri Defaults",
                "base_pack": None,
                "shell": None,
                "pack_ids": [],
                "packs": [],
                "error": str(exc),
            }

    @staticmethod
    def _is_official_bundled_setup_pack(pack: Dict[str, Any]) -> bool:
        """Return whether a setup definition belongs to this Tobkiri bundle."""
        marketplace = pack.get("marketplace")
        marketplace = marketplace if isinstance(marketplace, dict) else {}
        signing = pack.get("signing")
        signing = signing if isinstance(signing, dict) else {}
        return (
            str(marketplace.get("publisher") or "rumi-ai").strip().lower()
            in {"rumi-ai", "tobkiri"}
            and str(marketplace.get("registry") or "bundled").strip().lower()
            in {"bundled", "rumi_local_pack_registry"}
            and str(marketplace.get("status") or "verified").strip().lower()
            == "verified"
            and str(signing.get("mode") or "repository_reviewed").strip().lower()
            == "repository_reviewed"
            and signing.get("verified") is not False
        )

    @staticmethod
    def _setup_pack_review_revision(packs: Any) -> str:
        reviewed = []
        for item in packs if isinstance(packs, list) else []:
            if not isinstance(item, dict):
                continue
            reviewed.append({
                key: item.get(key)
                for key in (
                    "pack_id", "version", "source_path", "description", "risk_level",
                    "supports_all_ok", "required_permissions", "depends_on", "conflicts_with",
                )
            })
        encoded = json.dumps(reviewed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "setup-review-v1:" + hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _setup_pack_requires_confirmation(pack: Dict[str, Any]) -> bool:
        """Return whether setup needs explicit item-level confirmation."""
        return (
            str(pack.get("risk_level") or "").strip().lower() == "high"
            or bool(pack.get("required_permissions"))
        )

    @staticmethod
    def _normalize_setup_pack_selection_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(payload or {})
        packs = result.get("packs")
        if not isinstance(packs, list):
            return result
        if not any(
            key in result
            for key in (
                "selected_setup_pack_id",
                "selected_setup_pack_ids",
                "active_setup_pack_id",
                "active_target_pack_id",
            )
        ):
            return result

        pack_by_id = {
            str(item.get("pack_id") or "").strip(): item
            for item in packs
            if isinstance(item, dict) and str(item.get("pack_id") or "").strip()
        }
        selected_ids: list[str] = []
        seen_selected: set[str] = set()
        for item in result.get("selected_setup_pack_ids") or []:
            pack_id = str(item or "").strip()
            if pack_id and pack_id in pack_by_id and pack_id not in seen_selected:
                selected_ids.append(pack_id)
                seen_selected.add(pack_id)

        legacy_selected = str(result.get("selected_setup_pack_id") or "").strip()
        if legacy_selected and legacy_selected in pack_by_id and legacy_selected not in seen_selected:
            selected_ids.append(legacy_selected)
            seen_selected.add(legacy_selected)

        active_setup_pack_id = str(result.get("active_setup_pack_id") or "").strip()
        if active_setup_pack_id not in seen_selected:
            active_setup_pack_id = ""
        active_pack = pack_by_id.get(active_setup_pack_id) if active_setup_pack_id else None
        active_target_pack_id = (
            str(active_pack.get("target_pack_id") or "").strip()
            if isinstance(active_pack, dict)
            else ""
        )

        for item in packs:
            if isinstance(item, dict):
                item["selected"] = str(item.get("pack_id") or "").strip() in seen_selected

        result["selected_setup_pack_ids"] = selected_ids
        result["selected_setup_pack_id"] = active_setup_pack_id or (
            selected_ids[0] if selected_ids else None
        )
        result["active_setup_pack_id"] = active_setup_pack_id or None
        result["active_target_pack_id"] = active_target_pack_id or None
        return result

    def _setup_install_pack(self, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(body or {})
        setup_pack_ids = payload.get("setup_pack_ids")
        if setup_pack_ids is None:
            setup_pack_id = str(payload.get("setup_pack_id", "")).strip()
            if not setup_pack_id:
                return {"error": "setup_pack_id or setup_pack_ids is required", "status_code": 400}
            setup_pack_ids = setup_pack_id

        selected = [str(item).strip() for item in (setup_pack_ids if isinstance(setup_pack_ids, list) else [setup_pack_ids]) if str(item).strip()]
        reviewed = [str(item).strip() for item in payload.get("reviewed_pack_ids") or [] if str(item).strip()]
        current = self._normalize_setup_pack_selection_payload(get_setup_pack_manager().list_packs())
        revision = self._setup_pack_review_revision(current.get("packs"))
        if payload.get("review_revision") != revision or reviewed != selected:
            return {"error": "Setup pack review is missing or stale; refresh and review the exact install plan", "status_code": 409}
        confirmed = {str(item).strip() for item in payload.get("confirmed_privileged_pack_ids") or [] if str(item).strip()}
        by_id = {str(item.get("pack_id") or ""): item for item in current.get("packs") or [] if isinstance(item, dict)}
        privileged = {
            pack_id
            for pack_id in selected
            if self._setup_pack_requires_confirmation(by_id.get(pack_id, {}))
        }
        if not privileged.issubset(confirmed):
            return {
                "error": (
                    "Each high-risk or permission-declaring pack requires "
                    "explicit item-level confirmation"
                ),
                "status_code": 400,
            }

        install_defaults_profile = bool(payload.get("install_defaults_profile"))
        default_profile_pack_ids: list[str] = []
        if install_defaults_profile:
            default_profile = self._recommended_default_profile_preview()
            default_profile_pack_ids = [
                str(pack_id).strip()
                for pack_id in default_profile.get("pack_ids") or []
                if str(pack_id).strip()
            ]
            reviewed_default_profile_pack_ids = [
                str(pack_id).strip()
                for pack_id in payload.get("reviewed_default_profile_pack_ids") or []
                if str(pack_id).strip()
            ]
            required_setup_pack_ids = {
                str(pack_id).strip()
                for pack_id in (default_profile.get("setup_pack_ids") or ["defaultspack"])
                if str(pack_id).strip()
            }
            if reviewed_default_profile_pack_ids != default_profile_pack_ids:
                return {
                    "error": (
                        "Defaults Profile review is missing or stale; refresh "
                        "and review every included pack"
                    ),
                    "status_code": 409,
                }
            if not required_setup_pack_ids.issubset(set(selected)):
                return {
                    "error": "Defaults Profile requires its recommended setup pack",
                    "status_code": 400,
                }
            if payload.get("confirmed_defaults_profile") is not True:
                return {
                    "error": "Defaults Profile requires explicit confirmation",
                    "status_code": 400,
                }
            return {
                "error": (
                    "Legacy Defaults Profile installation is disabled; use a "
                    "captured v4 dispatch session"
                ),
                "status_code": 409,
                "v4_dispatch_required": True,
                "required_operations": [
                    "pack.install",
                    "approval.candidate",
                    "approval.approve",
                    "pack.enable",
                    "profile.reload",
                ],
            }

        result = get_setup_pack_manager().install(setup_pack_ids)
        if "error" in result:
            return result

        installed_target_pack_ids = [
            str(pack_id).strip()
            for pack_id in (result.get("installed_target_pack_ids") or [])
            if str(pack_id).strip()
        ]
        if not installed_target_pack_ids:
            active_target_pack_id = str(result.get("active_target_pack_id") or "").strip()
            if active_target_pack_id:
                installed_target_pack_ids = [active_target_pack_id]

        self._refresh_runtime_pack_approvals()

        migration_statuses: Dict[str, Dict[str, Any]] = {}
        migrations: Dict[str, Any] = {}
        for target_pack_id in installed_target_pack_ids:
            status = self._get_pack_migration_status(target_pack_id)
            if (
                status.get("available")
                and status.get("needs_user_migration")
                and self._pack_function_exists(target_pack_id, "run_migration")
            ):
                migrations[target_pack_id] = invoke_pack_function(target_pack_id, "run_migration")
                status = self._get_pack_migration_status(target_pack_id)
            migration_statuses[target_pack_id] = status
        if migration_statuses:
            result["migration_statuses"] = migration_statuses
        if migrations:
            result["migrations"] = migrations
        return result

    def _setup_grant_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return get_setup_pack_manager().grant_all_ok(setup_pack_id)

    def _setup_revoke_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        return get_setup_pack_manager().revoke_all_ok(setup_pack_id)

    def _setup_get_migration_status(self) -> Dict[str, Any]:
        selection = get_setup_pack_manager().get_selection()
        active_target_pack_id = str(selection.get("active_target_pack_id") or "")
        if not active_target_pack_id:
            return {
                "pack_id": None,
                "available": False,
                "needs_user_migration": False,
                "registry_available": False,
                "reason": "active_target_not_selected",
            }
        return self._get_pack_migration_status(active_target_pack_id)
