"""Dataclasses shared by layered update managers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PackUpdateCheck:
    target: str
    pack_id: str
    current_version: str
    latest_version: str
    update_available: bool
    channel: str = "stable"
    staged: bool = False
    rollback_available: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "pack_id": self.pack_id,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "channel": self.channel,
            "staged": self.staged,
            "applied": False,
            "restart_required": False,
            "routes_reload_recommended": True,
            "rollback_available": self.rollback_available,
            "backup_dir": None,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class StagedPackUpdate:
    stage_id: str
    pack_id: str
    version: str
    staging_dir: str
    bundle_path: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "pack_id": self.pack_id,
            "version": self.version,
            "staged": True,
            "staging_dir": self.staging_dir,
            "bundle_path": self.bundle_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class PackUpdateResult:
    target: str
    pack_id: str
    current_version: str
    latest_version: str
    applied: bool
    staged: bool
    restart_required: bool = False
    routes_reload_recommended: bool = True
    rollback_available: bool = True
    backup_dir: str | None = None
    errors: list[str] = field(default_factory=list)
    applied_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "pack_id": self.pack_id,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": False,
            "staged": self.staged,
            "applied": self.applied,
            "restart_required": self.restart_required,
            "routes_reload_recommended": self.routes_reload_recommended,
            "rollback_available": self.rollback_available,
            "backup_dir": self.backup_dir,
            "errors": self.errors,
            "applied_files": self.applied_files,
            "skipped_files": self.skipped_files,
            "applied_count": len(self.applied_files),
            "skipped_count": len(self.skipped_files),
        }


@dataclass(frozen=True)
class RollbackResult:
    target: str
    pack_id: str
    previous_version: str
    active_version: str
    rolled_back: bool
    restart_required: bool = False
    routes_reload_recommended: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "pack_id": self.pack_id,
            "previous_version": self.previous_version,
            "active_version": self.active_version,
            "rolled_back": self.rolled_back,
            "restart_required": self.restart_required,
            "routes_reload_recommended": self.routes_reload_recommended,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class AutoUpdateRunResult:
    enabled_targets: list[str]
    due: bool
    checked_at: str | None
    results: list[dict[str, Any]]
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_targets": self.enabled_targets,
            "due": self.due,
            "checked_at": self.checked_at,
            "results": self.results,
            "skipped_reason": self.skipped_reason,
        }


@dataclass(frozen=True)
class CoreUpdateResult:
    target: str
    current_version: str
    latest_version: str
    update_available: bool = False
    staged: bool = False
    applied: bool = False
    restart_required: bool = True
    routes_reload_recommended: bool = False
    rollback_available: bool = False
    backup_dir: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "staged": self.staged,
            "applied": self.applied,
            "restart_required": self.restart_required,
            "routes_reload_recommended": self.routes_reload_recommended,
            "rollback_available": self.rollback_available,
            "backup_dir": self.backup_dir,
            "errors": self.errors,
        }
