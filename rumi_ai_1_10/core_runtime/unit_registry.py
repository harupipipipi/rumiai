"""
unit_registry.py - Store 内 Unit 管理
"""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .store_registry import get_store_registry


APPROVALS_FILE = "user_data/units/approvals.json"


@dataclass
class UnitInfo:
    unit_id: str
    version: str
    kind: str
    entrypoint: Optional[str]
    declared_by_pack_id: str
    declared_at: str
    requires_individual_approval: bool
    exec_modes_allowed: List[str]
    permission_id: Optional[str]
    unit_dir: Path


class UnitRegistry:
    def __init__(self, approvals_file: str = None):
        self._approvals_path = Path(approvals_file or APPROVALS_FILE)
        self._approvals_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def publish_unit(self, store_id: str, source_path: str, actor: str = "system") -> Dict[str, Any]:
        store_registry = get_store_registry()
        store_root = store_registry.get_store_path(store_id)
        if store_root is None:
            return {"success": False, "error": "store_not_found"}

        src = Path(source_path).resolve()
        if not src.exists() or not src.is_dir():
            return {"success": False, "error": "source_not_found"}

        unit_json_path = src / "unit.json"
        if not unit_json_path.exists():
            return {"success": False, "error": "unit_json_missing"}

        unit_meta = self._load_unit_json(unit_json_path)
        validation_error = self._validate_unit_meta(unit_meta)
        if validation_error:
            return {"success": False, "error": validation_error}

        unit_id = unit_meta["unit_id"]
        version = unit_meta["version"]
        namespace, name = self._split_unit_id(unit_id)

        target_dir = (store_root / namespace / name / version).resolve()
        try:
            target_dir.relative_to(store_root)
        except ValueError:
            return {"success": False, "error": "invalid_unit_path"}

        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, target_dir)

        if unit_meta.get("requires_individual_approval"):
            self._set_unit_status(unit_id, version, "pending", actor)
        else:
            self._set_unit_status(unit_id, version, "approved", actor)

        return {
            "success": True,
            "store_id": store_id,
            "unit_id": unit_id,
            "version": version,
            "path": str(target_dir),
        }

    def list_units(self, store_id: Optional[str] = None) -> Dict[str, Any]:
        store_registry = get_store_registry()
        store_ids = [store_id] if store_id else list(store_registry.list_stores().get("stores", {}).keys())
        units: List[Dict[str, Any]] = []
        for sid in store_ids:
            store_root = store_registry.get_store_path(sid)
            if store_root is None or not store_root.exists():
                continue
            for unit_json in store_root.glob("**/unit.json"):
                try:
                    unit_meta = self._load_unit_json(unit_json)
                    unit_meta["store_id"] = sid
                    units.append(unit_meta)
                except Exception:
                    continue
        return {"units": units, "count": len(units)}

    def get_unit(self, store_id: str, unit_id: str, version: str) -> Optional[UnitInfo]:
        store_registry = get_store_registry()
        store_root = store_registry.get_store_path(store_id)
        if store_root is None:
            return None
        namespace, name = self._split_unit_id(unit_id)
        unit_dir = (store_root / namespace / name / version).resolve()
        try:
            unit_dir.relative_to(store_root)
        except ValueError:
            return None
        unit_json = unit_dir / "unit.json"
        if not unit_json.exists():
            return None
        meta = self._load_unit_json(unit_json)
        return UnitInfo(
            unit_id=meta["unit_id"],
            version=meta["version"],
            kind=meta["kind"],
            entrypoint=meta.get("entrypoint"),
            declared_by_pack_id=meta["declared_by_pack_id"],
            declared_at=meta["declared_at"],
            requires_individual_approval=bool(meta.get("requires_individual_approval", False)),
            exec_modes_allowed=list(meta.get("exec_modes_allowed", [])),
            permission_id=meta.get("permission_id"),
            unit_dir=unit_dir,
        )

    def is_unit_approved(self, unit_id: str, version: str) -> bool:
        with self._lock:
            approvals = self._load_approvals()
            key = self._approval_key(unit_id, version)
            return approvals.get(key, {}).get("status") == "approved"

    def approve_unit(self, unit_id: str, version: str, actor: str = "system") -> None:
        self._set_unit_status(unit_id, version, "approved", actor)

    def _set_unit_status(self, unit_id: str, version: str, status: str, actor: str) -> None:
        with self._lock:
            approvals = self._load_approvals()
            key = self._approval_key(unit_id, version)
            approvals[key] = {
                "unit_id": unit_id,
                "version": version,
                "status": status,
                "updated_at": self._now_ts(),
                "actor": actor,
            }
            self._save_approvals(approvals)

    def _approval_key(self, unit_id: str, version: str) -> str:
        return f"{unit_id}::{version}"

    def _load_approvals(self) -> Dict[str, Any]:
        if not self._approvals_path.exists():
            return {}
        try:
            return json.loads(self._approvals_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_approvals(self, data: Dict[str, Any]) -> None:
        self._approvals_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_unit_json(self, unit_json_path: Path) -> Dict[str, Any]:
        return json.loads(unit_json_path.read_text(encoding="utf-8"))

    def _validate_unit_meta(self, unit_meta: Dict[str, Any]) -> Optional[str]:
        required_fields = ["unit_id", "version", "kind", "declared_by_pack_id", "declared_at", "exec_modes_allowed"]
        for field in required_fields:
            if not unit_meta.get(field):
                return f"missing_{field}"
        kind = unit_meta.get("kind")
        if kind not in ("data", "python", "binary"):
            return "invalid_kind"
        if kind in ("python", "binary") and not unit_meta.get("entrypoint"):
            return "missing_entrypoint"
        return None

    def _split_unit_id(self, unit_id: str) -> Tuple[str, str]:
        if "/" in unit_id:
            parts = unit_id.split("/")
            return parts[0], "/".join(parts[1:])
        if ":" in unit_id:
            namespace, name = unit_id.split(":", 1)
            return namespace, name
        return "default", unit_id


_global_unit_registry: Optional[UnitRegistry] = None
_unit_lock = threading.Lock()


def get_unit_registry() -> UnitRegistry:
    global _global_unit_registry
    if _global_unit_registry is None:
        with _unit_lock:
            if _global_unit_registry is None:
                _global_unit_registry = UnitRegistry()
    return _global_unit_registry


def reset_unit_registry(approvals_file: str = None) -> UnitRegistry:
    global _global_unit_registry
    with _unit_lock:
        _global_unit_registry = UnitRegistry(approvals_file)
    return _global_unit_registry
