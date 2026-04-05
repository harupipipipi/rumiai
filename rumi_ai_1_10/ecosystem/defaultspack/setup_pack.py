"""
setup_pack.py - Pack installation/setup infrastructure.

Provides:
- Pack enumeration during setup
- Pack display (name, description, risk, recommended)
- defaultspack-only 'all OK' permission granting
- Audit logging for pack install/revoke/reset
- Auto-discovery: place a pack in ecosystem/ and it's recognized
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PackRisk(str, Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PackPermissionLevel(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    STANDARD = "standard"
    ALL_OK = "all_ok"  # Only for defaultspack


@dataclass
class PackManifest:
    """Metadata for a pack visible during setup."""
    pack_id: str
    display_name: str
    description: str
    version: str
    risk: PackRisk = PackRisk.LOW
    recommended: bool = False
    is_defaults: bool = False
    permission_level: PackPermissionLevel = PackPermissionLevel.STANDARD
    author: str = ""
    tags: List[str] = field(default_factory=list)
    icon: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "risk": self.risk.value,
            "recommended": self.recommended,
            "is_defaults": self.is_defaults,
            "permission_level": self.permission_level.value,
            "author": self.author,
            "tags": self.tags,
            "icon": self.icon,
        }


@dataclass
class PackInstallResult:
    success: bool
    pack_id: str
    permission_level: PackPermissionLevel
    message: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "success": self.success,
            "pack_id": self.pack_id,
            "permission_level": self.permission_level.value,
            "message": self.message,
        }
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class AuditEntry:
    timestamp: float
    action: str
    pack_id: str
    user: str = "system"
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "pack_id": self.pack_id,
            "user": self.user,
            "detail": self.detail,
        }


class SetupPackManager:
    """
    Pack installation and setup manager.

    Key rules:
    - Only 'defaultspack' gets PackPermissionLevel.ALL_OK
    - Other packs get STANDARD or lower
    - No hardcoding of pack names beyond 'defaultspack' for ALL_OK
    - Packs are auto-discovered from ecosystem/ directory
    """

    DEFAULTS_PACK_ID = "defaultspack"

    def __init__(self, ecosystem_dir: Optional[Path] = None, audit_dir: Optional[Path] = None):
        self._ecosystem_dir = ecosystem_dir
        self._audit_dir = audit_dir
        self._installed: Dict[str, PackManifest] = {}
        self._audit_log: List[AuditEntry] = []

    def enumerate_packs(self) -> List[PackManifest]:
        """List all available packs. Auto-discovers from ecosystem/."""
        packs = []

        # Always include defaultspack
        defaults = PackManifest(
            pack_id=self.DEFAULTS_PACK_ID,
            display_name="Defaults Pack",
            description="Official first-party pack. Provides AI client, prompt, tool, "
                        "chat, agent, memory, knowledge, coding, frontend, CLI.",
            version="2.0.0",
            risk=PackRisk.SAFE,
            recommended=True,
            is_defaults=True,
            permission_level=PackPermissionLevel.ALL_OK,
            author="rumi",
            tags=["official", "core", "recommended"],
            icon="star",
        )
        packs.append(defaults)

        # Scan ecosystem/ for other packs
        if self._ecosystem_dir and self._ecosystem_dir.is_dir():
            for subdir in sorted(self._ecosystem_dir.iterdir()):
                if not subdir.is_dir() or subdir.name.startswith("."):
                    continue
                if subdir.name == self.DEFAULTS_PACK_ID:
                    continue
                eco_json = subdir / "ecosystem.json"
                if eco_json.is_file():
                    try:
                        data = json.loads(eco_json.read_text(encoding="utf-8"))
                        manifest = PackManifest(
                            pack_id=data.get("pack_id", subdir.name),
                            display_name=data.get("display_name", subdir.name),
                            description=data.get("description", ""),
                            version=data.get("version", "0.0.0"),
                            risk=PackRisk(data.get("risk", "low")),
                            recommended=data.get("recommended", False),
                            is_defaults=False,
                            permission_level=PackPermissionLevel.STANDARD,
                            author=data.get("author", ""),
                            tags=data.get("tags", []),
                        )
                        packs.append(manifest)
                    except Exception as exc:
                        logger.warning("Failed to read pack manifest: %s (%s)", subdir, exc)

        return packs

    def install_pack(self, pack_id: str, user: str = "system") -> PackInstallResult:
        """Install a pack. Only defaultspack gets ALL_OK."""
        packs = {p.pack_id: p for p in self.enumerate_packs()}
        manifest = packs.get(pack_id)

        if manifest is None:
            return PackInstallResult(
                success=False,
                pack_id=pack_id,
                permission_level=PackPermissionLevel.NONE,
                error=f"Pack '{pack_id}' not found",
            )

        # Permission level enforcement
        if pack_id == self.DEFAULTS_PACK_ID:
            permission = PackPermissionLevel.ALL_OK
        else:
            permission = PackPermissionLevel.STANDARD

        manifest.permission_level = permission
        self._installed[pack_id] = manifest

        self._log_audit("install", pack_id, user, f"permission={permission.value}")

        return PackInstallResult(
            success=True,
            pack_id=pack_id,
            permission_level=permission,
            message=f"Pack '{pack_id}' installed with {permission.value} permissions",
        )

    def revoke_pack(self, pack_id: str, user: str = "system") -> PackInstallResult:
        """Revoke (uninstall) a pack."""
        if pack_id not in self._installed:
            return PackInstallResult(
                success=False,
                pack_id=pack_id,
                permission_level=PackPermissionLevel.NONE,
                error=f"Pack '{pack_id}' not installed",
            )

        del self._installed[pack_id]
        self._log_audit("revoke", pack_id, user)

        return PackInstallResult(
            success=True,
            pack_id=pack_id,
            permission_level=PackPermissionLevel.NONE,
            message=f"Pack '{pack_id}' revoked",
        )

    def reset_pack(self, pack_id: str, user: str = "system") -> PackInstallResult:
        """Reset a pack to default state."""
        self.revoke_pack(pack_id, user)
        return self.install_pack(pack_id, user)

    def is_all_ok(self, pack_id: str) -> bool:
        """Check if a pack has ALL_OK permission."""
        m = self._installed.get(pack_id)
        return m is not None and m.permission_level == PackPermissionLevel.ALL_OK

    def get_installed(self) -> Dict[str, PackManifest]:
        return dict(self._installed)

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._audit_log]

    def _log_audit(self, action: str, pack_id: str, user: str = "system", detail: str = "") -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            action=action,
            pack_id=pack_id,
            user=user,
            detail=detail,
        )
        self._audit_log.append(entry)

        if self._audit_dir:
            try:
                self._audit_dir.mkdir(parents=True, exist_ok=True)
                log_file = self._audit_dir / "pack_audit.jsonl"
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict()) + "\n")
            except Exception as exc:
                logger.warning("Failed to write audit log: %s", exc)
