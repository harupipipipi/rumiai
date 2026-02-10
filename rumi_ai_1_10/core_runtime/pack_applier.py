"""
pack_applier.py - Apply staging packs to ecosystem
"""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import find_ecosystem_json


@dataclass
class PackApplyResult:
    success: bool
    pack_ids: List[str] = None
    backups: Dict[str, str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "pack_ids": self.pack_ids or [],
            "backups": self.backups or {},
            "error": self.error,
        }


class PackApplier:
    DEFAULT_STAGING_ROOT = "user_data/pack_staging"
    DEFAULT_ECOSYSTEM_ROOT = "ecosystem"
    DEFAULT_BACKUP_ROOT = "user_data/pack_backups"

    def __init__(
        self,
        staging_root: str = None,
        ecosystem_root: str = None,
        backup_root: str = None,
    ):
        self._staging_root = Path(staging_root) if staging_root else Path(self.DEFAULT_STAGING_ROOT)
        self._ecosystem_root = Path(ecosystem_root) if ecosystem_root else Path(self.DEFAULT_ECOSYSTEM_ROOT)
        self._backup_root = Path(backup_root) if backup_root else Path(self.DEFAULT_BACKUP_ROOT)
        self._lock = threading.RLock()

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def apply(self, staging_id: str, mode: str = "replace", actor: str = "api_user") -> PackApplyResult:
        self._audit_event("pack_apply_started", True, {
            "staging_id": staging_id,
            "actor": actor,
        })
        if mode != "replace":
            return PackApplyResult(False, error="unsupported_mode")
        try:
            staging_dir = self._staging_root / staging_id
            payload_dir = staging_dir / "payload"
            if not payload_dir.exists():
                raise ValueError("staging_not_found")

            pack_entries = self._detect_pack_entries(payload_dir)
            backups: Dict[str, str] = {}

            with self._lock:
                for pack_id, pack_dir in pack_entries:
                    target_dir = self._ecosystem_root / pack_id
                    if target_dir.exists():
                        self._ensure_pack_identity_match(pack_id, pack_dir, target_dir)
                        backup_path = self._backup_root / pack_id / self._now_ts()
                        backup_path.parent.mkdir(parents=True, exist_ok=True)
                        if backup_path.exists():
                            shutil.rmtree(backup_path)
                        shutil.copytree(target_dir, backup_path)
                        backups[pack_id] = str(backup_path)
                        shutil.rmtree(target_dir)
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(pack_dir, target_dir)

            result = PackApplyResult(True, pack_ids=[pid for pid, _ in pack_entries], backups=backups)
            self._audit_event("pack_apply_completed", True, {
                "staging_id": staging_id,
                "pack_ids": result.pack_ids,
                "backups": backups,
            })
            return result
        except Exception as e:
            self._audit_event("pack_apply_failed", False, {
                "staging_id": staging_id,
                "error": str(e),
            })
            return PackApplyResult(False, error=str(e))

    def _detect_pack_entries(self, payload_dir: Path) -> List[tuple]:
        packs_dir = payload_dir / "packs"
        entries: List[tuple] = []
        if packs_dir.exists() and packs_dir.is_dir():
            for pack_dir in sorted(packs_dir.iterdir()):
                if not pack_dir.is_dir():
                    continue
                eco_json, _ = find_ecosystem_json(pack_dir)
                if eco_json is None:
                    raise ValueError(f"ecosystem_json_not_found:{pack_dir.name}")
                entries.append((pack_dir.name, pack_dir))
            if not entries:
                raise ValueError("no_packs_found")
            return entries

        eco_json, _ = find_ecosystem_json(payload_dir)
        if eco_json is None:
            raise ValueError("ecosystem_json_not_found")
        data = json.loads(eco_json.read_text(encoding="utf-8"))
        pack_id = data.get("pack_id")
        if not pack_id:
            raise ValueError("pack_id_missing")
        entries.append((pack_id, payload_dir))
        return entries

    def _ensure_pack_identity_match(self, pack_id: str, new_pack_dir: Path, existing_dir: Path) -> None:
        new_identity = self._read_pack_identity(new_pack_dir)
        existing_identity = self._read_pack_identity(existing_dir)
        if existing_identity and new_identity and existing_identity != new_identity:
            raise ValueError("pack_identity_mismatch")
        if existing_identity and not new_identity:
            raise ValueError("pack_identity_missing")
        if new_identity and not existing_identity:
            raise ValueError("pack_identity_missing")

    def _read_pack_identity(self, pack_dir: Path) -> Optional[str]:
        eco_json, _ = find_ecosystem_json(pack_dir)
        if eco_json is None or not eco_json.exists():
            return None
        try:
            data = json.loads(eco_json.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data.get("pack_identity")

    def _audit_event(self, event_type: str, success: bool, details: Dict[str, Any]) -> None:
        try:
            from .audit_logger import get_audit_logger
            audit = get_audit_logger()
            audit.log_system_event(
                event_type=event_type,
                success=success,
                details=details,
            )
        except Exception:
            pass


_global_pack_applier: Optional[PackApplier] = None
_applier_lock = threading.Lock()


def get_pack_applier() -> PackApplier:
    global _global_pack_applier
    if _global_pack_applier is None:
        with _applier_lock:
            if _global_pack_applier is None:
                _global_pack_applier = PackApplier()
    return _global_pack_applier


def reset_pack_applier(
    staging_root: str = None,
    ecosystem_root: str = None,
    backup_root: str = None,
) -> PackApplier:
    global _global_pack_applier
    with _applier_lock:
        _global_pack_applier = PackApplier(staging_root, ecosystem_root, backup_root)
    return _global_pack_applier
