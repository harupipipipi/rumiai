"""
setup_pack.py - setup-pack discovery / install / grants
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import BASE_DIR, discover_pack_locations

logger = logging.getLogger(__name__)

SETUP_PACK_ROOT = BASE_DIR / "ecosystem" / "setup_pack"
SETUP_PACK_SELECTION_FILE = (
    BASE_DIR / "user_data" / "settings" / "setup_pack_selection.json"
)
DEFAULTSPACK_ALL_OK_PERMISSIONS = [
    "function.call",
    "pack.update",
    "pack.install",
    "pack.uninstall",
    "pack.migrate",
    "defaultspack.module.manage",
]


@dataclass(frozen=True)
class SetupPackDefinition:
    pack_id: str
    display_name: str
    description: str
    target_pack_id: str
    recommended: bool = False
    risk_level: str = "medium"
    supports_all_ok: bool = False
    source_path: str = ""


class SetupPackManager:
    def __init__(
        self,
        root: Path | None = None,
        selection_file: Path | None = None,
    ) -> None:
        self.root = Path(root or SETUP_PACK_ROOT)
        self.selection_file = Path(selection_file or SETUP_PACK_SELECTION_FILE)

    def _definition_files(self) -> List[Path]:
        if not self.root.is_dir():
            return []
        return sorted(self.root.glob("*/pack.json"))

    def _load_definitions(self) -> Dict[str, SetupPackDefinition]:
        result: Dict[str, SetupPackDefinition] = {}
        for path in self._definition_files():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to parse setup_pack file %s: %s", path, exc)
                continue
            pack_id = str(raw.get("pack_id") or path.parent.name)
            result[pack_id] = SetupPackDefinition(
                pack_id=pack_id,
                display_name=str(raw.get("display_name", pack_id)),
                description=str(raw.get("description", "")),
                target_pack_id=str(raw.get("target_pack_id", pack_id)),
                recommended=bool(raw.get("recommended", False)),
                risk_level=str(raw.get("risk_level", "medium")),
                supports_all_ok=bool(raw.get("supports_all_ok", False)),
                source_path=str(path.parent.resolve()),
            )
        return result

    def list_packs(self) -> Dict[str, Any]:
        definitions = self._load_definitions()
        selection = self.get_selection()
        packs = []
        for pack_id in sorted(definitions):
            item = definitions[pack_id]
            packs.append({
                "pack_id": item.pack_id,
                "display_name": item.display_name,
                "description": item.description,
                "target_pack_id": item.target_pack_id,
                "recommended": item.recommended,
                "risk_level": item.risk_level,
                "supports_all_ok": item.supports_all_ok,
                "source_path": item.source_path,
                "selected": selection.get("setup_pack_id") == item.pack_id,
            })
        return {
            "packs": packs,
            "count": len(packs),
            "selected_setup_pack_id": selection.get("setup_pack_id"),
        }

    def get_selection(self) -> Dict[str, Any]:
        if not self.selection_file.is_file():
            return {}
        try:
            data = json.loads(self.selection_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse setup_pack selection file %s: %s", self.selection_file, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def _log_system_event(
        self,
        action: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        try:
            from .audit_logger import get_audit_logger

            audit = get_audit_logger()
            audit.log_system_event(
                action=action,
                success=success,
                details=details or {},
                error=error,
            )
        except Exception:
            logger.debug("Failed to audit setup_pack system event", exc_info=True)

    def _log_permission_event(
        self,
        action: str,
        success: bool,
        principal_id: str,
        permission_id: str,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        try:
            from .audit_logger import get_audit_logger

            audit = get_audit_logger()
            audit.log_permission_event(
                principal_id=principal_id,
                permission_id=permission_id,
                action=action,
                success=success,
                details=details or {},
                error=error,
            )
        except Exception:
            logger.debug("Failed to audit setup_pack permission event", exc_info=True)

    def install(self, setup_pack_id: str) -> Dict[str, Any]:
        definitions = self._load_definitions()
        definition = definitions.get(setup_pack_id)
        if definition is None:
            self._log_system_event(
                "setup_pack.install",
                False,
                details={"setup_pack_id": setup_pack_id},
                error="unknown_setup_pack",
            )
            return {"error": f"Unknown setup_pack: {setup_pack_id}", "status_code": 404}

        locations = {
            loc.pack_id: loc for loc in discover_pack_locations()
        }
        target = locations.get(definition.target_pack_id)
        if target is None:
            self._log_system_event(
                "setup_pack.install",
                False,
                details={
                    "setup_pack_id": definition.pack_id,
                    "target_pack_id": definition.target_pack_id,
                },
                error="target_pack_not_found",
            )
            return {
                "error": f"Target pack not found: {definition.target_pack_id}",
                "status_code": 404,
            }

        selection = {
            "setup_pack_id": definition.pack_id,
            "target_pack_id": definition.target_pack_id,
            "display_name": definition.display_name,
        }
        self.selection_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.selection_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.selection_file)

        try:
            from backend_core.ecosystem.active_ecosystem import get_active_ecosystem_manager

            active = get_active_ecosystem_manager()
            eco = json.loads(target.ecosystem_json_path.read_text(encoding="utf-8"))
            active.active_pack_identity = eco.get("pack_identity")
        except Exception:
            logger.debug("Failed to switch active_pack_identity during setup_pack install", exc_info=True)

        try:
            from .approval_manager import get_approval_manager

            am = get_approval_manager()
            if getattr(am, "_initialized", False):
                am.approve(definition.target_pack_id)
        except Exception:
            logger.debug("Failed to auto-approve setup pack target", exc_info=True)

        self._log_system_event(
            "setup_pack.install",
            True,
            details={
                "setup_pack_id": definition.pack_id,
                "target_pack_id": definition.target_pack_id,
            },
        )
        return {
            "installed": True,
            "setup_pack_id": definition.pack_id,
            "target_pack_id": definition.target_pack_id,
            "selection": selection,
        }

    def grant_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        definitions = self._load_definitions()
        definition = definitions.get(setup_pack_id)
        if definition is None:
            self._log_permission_event(
                "grant_all_ok",
                False,
                principal_id="",
                permission_id="*",
                details={"setup_pack_id": setup_pack_id},
                error="unknown_setup_pack",
            )
            return {"error": f"Unknown setup_pack: {setup_pack_id}", "status_code": 404}
        if definition.pack_id != "defaultspack" or not definition.supports_all_ok:
            self._log_permission_event(
                "grant_all_ok",
                False,
                principal_id=definition.target_pack_id,
                permission_id="*",
                details={"setup_pack_id": definition.pack_id},
                error="all_ok_not_supported",
            )
            return {
                "error": "all OK is only available for defaultspack",
                "status_code": 403,
            }
        from .capability_grant_manager import get_capability_grant_manager

        gm = get_capability_grant_manager()
        result = gm.batch_grant([
            {
                "principal_id": definition.target_pack_id,
                "permission_id": permission_id,
                "config": {
                    "mode": "all_ok",
                    "source": "setup_pack",
                    "setup_pack_id": definition.pack_id,
                },
            }
            for permission_id in DEFAULTSPACK_ALL_OK_PERMISSIONS
        ])
        self._log_permission_event(
            "grant_all_ok",
            result.failed_count == 0,
            principal_id=definition.target_pack_id,
            permission_id="*",
            details={
                "setup_pack_id": definition.pack_id,
                "granted_count": result.granted_count,
                "failed_count": result.failed_count,
            },
            error=None if result.failed_count == 0 else "partial_grant_failure",
        )
        return {
            "granted": result.failed_count == 0,
            "principal_id": definition.target_pack_id,
            "permission_ids": list(DEFAULTSPACK_ALL_OK_PERMISSIONS),
            "granted_count": result.granted_count,
            "failed_count": result.failed_count,
        }

    def revoke_all_ok(self, setup_pack_id: str) -> Dict[str, Any]:
        definitions = self._load_definitions()
        definition = definitions.get(setup_pack_id)
        if definition is None:
            self._log_permission_event(
                "revoke_all_ok",
                False,
                principal_id="",
                permission_id="*",
                details={"setup_pack_id": setup_pack_id},
                error="unknown_setup_pack",
            )
            return {"error": f"Unknown setup_pack: {setup_pack_id}", "status_code": 404}
        if definition.pack_id != "defaultspack" or not definition.supports_all_ok:
            self._log_permission_event(
                "revoke_all_ok",
                False,
                principal_id=definition.target_pack_id,
                permission_id="*",
                details={"setup_pack_id": definition.pack_id},
                error="all_ok_not_supported",
            )
            return {
                "error": "all OK is only available for defaultspack",
                "status_code": 403,
            }
        from .capability_grant_manager import get_capability_grant_manager

        gm = get_capability_grant_manager()
        revoked = []
        for permission_id in DEFAULTSPACK_ALL_OK_PERMISSIONS:
            revoked.append(gm.revoke_permission(definition.target_pack_id, permission_id))
        self._log_permission_event(
            "revoke_all_ok",
            True,
            principal_id=definition.target_pack_id,
            permission_id="*",
            details={
                "setup_pack_id": definition.pack_id,
                "revoked_count": sum(1 for item in revoked if item),
            },
        )
        return {
            "revoked": True,
            "principal_id": definition.target_pack_id,
            "permission_ids": list(DEFAULTSPACK_ALL_OK_PERMISSIONS),
            "revoked_count": sum(1 for item in revoked if item),
        }


_global_setup_pack_manager: SetupPackManager | None = None


def get_setup_pack_manager() -> SetupPackManager:
    global _global_setup_pack_manager
    if _global_setup_pack_manager is None:
        _global_setup_pack_manager = SetupPackManager()
    return _global_setup_pack_manager
