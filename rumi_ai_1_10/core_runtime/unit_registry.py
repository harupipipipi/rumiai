"""
unit_registry.py - ストア内ユニットの登録・列挙・メタ読み取り

Store 配下のユニット（data / python / binary）を管理する。
公式は意味を解釈しない（No Favoritism）。

ユニット格納構造:
  <store_root>/<unit_namespace>/<unit_name>/<unit_version>/
    unit.json（必須）
    + 実体ファイル群
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import is_path_within


VALID_KINDS = frozenset({"data", "python", "binary"})
VALID_EXEC_MODES = frozenset({"pack_container", "host_capability", "sandbox"})


@dataclass
class UnitMeta:
    unit_id: str
    version: str
    kind: str
    entrypoint: Optional[str] = None
    declared_by_pack_id: str = ""
    declared_at: str = ""
    requires_individual_approval: bool = True
    exec_modes_allowed: List[str] = field(default_factory=list)
    permission_id: str = ""
    unit_dir: Optional[Path] = None
    store_id: str = ""
    namespace: str = ""
    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "version": self.version,
            "kind": self.kind,
            "entrypoint": self.entrypoint,
            "declared_by_pack_id": self.declared_by_pack_id,
            "declared_at": self.declared_at,
            "requires_individual_approval": self.requires_individual_approval,
            "exec_modes_allowed": self.exec_modes_allowed,
            "permission_id": self.permission_id,
            "store_id": self.store_id,
            "namespace": self.namespace,
            "name": self.name,
            "unit_dir": str(self.unit_dir) if self.unit_dir else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnitMeta":
        ud = data.get("unit_dir")
        return cls(
            unit_id=data.get("unit_id", ""),
            version=data.get("version", ""),
            kind=data.get("kind", "data"),
            entrypoint=data.get("entrypoint"),
            declared_by_pack_id=data.get("declared_by_pack_id", ""),
            declared_at=data.get("declared_at", ""),
            requires_individual_approval=data.get("requires_individual_approval", True),
            exec_modes_allowed=data.get("exec_modes_allowed", []),
            permission_id=data.get("permission_id", ""),
            unit_dir=Path(ud) if ud else None,
            store_id=data.get("store_id", ""),
            namespace=data.get("namespace", ""),
            name=data.get("name", ""),
        )


@dataclass
class UnitRef:
    store_id: str
    unit_id: str
    version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store_id": self.store_id,
            "unit_id": self.unit_id,
            "version": self.version,
        }


@dataclass
class PublishResult:
    success: bool
    unit_id: str = ""
    version: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "unit_id": self.unit_id,
            "version": self.version,
            "error": self.error,
        }


class UnitRegistry:
    def __init__(self):
        self._lock = threading.RLock()

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def list_units(self, store_root: Path) -> List[UnitMeta]:
        results = []
        if not store_root.is_dir():
            return results
        for ns_dir in sorted(store_root.iterdir()):
            if not ns_dir.is_dir() or ns_dir.name.startswith("."):
                continue
            for name_dir in sorted(ns_dir.iterdir()):
                if not name_dir.is_dir() or name_dir.name.startswith("."):
                    continue
                for ver_dir in sorted(name_dir.iterdir()):
                    if not ver_dir.is_dir() or ver_dir.name.startswith("."):
                        continue
                    unit_json = ver_dir / "unit.json"
                    if unit_json.exists():
                        meta = self._load_unit_json(
                            unit_json, ver_dir, ns_dir.name, name_dir.name,
                        )
                        if meta:
                            results.append(meta)
        return results

    def get_unit(
        self,
        store_root: Path,
        namespace: str,
        name: str,
        version: str,
    ) -> Optional[UnitMeta]:
        unit_dir = store_root / namespace / name / version
        if not unit_dir.is_dir():
            return None
        if not is_path_within(unit_dir, store_root):
            return None
        unit_json = unit_dir / "unit.json"
        if not unit_json.exists():
            return None
        return self._load_unit_json(unit_json, unit_dir, namespace, name)

    def get_unit_by_ref(
        self,
        store_root: Path,
        unit_ref: UnitRef,
    ) -> Optional[UnitMeta]:
        if not store_root.is_dir():
            return None
        for ns_dir in sorted(store_root.iterdir()):
            if not ns_dir.is_dir() or ns_dir.name.startswith("."):
                continue
            for name_dir in sorted(ns_dir.iterdir()):
                if not name_dir.is_dir() or name_dir.name.startswith("."):
                    continue
                for ver_dir in sorted(name_dir.iterdir()):
                    if not ver_dir.is_dir() or ver_dir.name.startswith("."):
                        continue
                    unit_json = ver_dir / "unit.json"
                    if unit_json.exists():
                        meta = self._load_unit_json(
                            unit_json, ver_dir, ns_dir.name, name_dir.name,
                        )
                        if (
                            meta
                            and meta.unit_id == unit_ref.unit_id
                            and meta.version == unit_ref.version
                        ):
                            meta.store_id = unit_ref.store_id
                            return meta
        return None

    def publish_unit(
        self,
        store_root: Path,
        source_dir: Path,
        namespace: str,
        name: str,
        version: str,
        store_id: str = "",
    ) -> PublishResult:
        src_unit_json = source_dir / "unit.json"
        if not src_unit_json.exists():
            return PublishResult(success=False, error="unit.json not found in source")

        meta = self._load_unit_json(src_unit_json, source_dir, namespace, name)
        if meta is None:
            return PublishResult(success=False, error="Failed to parse unit.json")

        if meta.kind not in VALID_KINDS:
            return PublishResult(
                success=False, unit_id=meta.unit_id,
                error=f"Invalid kind: {meta.kind}",
            )
        if meta.kind in ("python", "binary") and not meta.entrypoint:
            return PublishResult(
                success=False, unit_id=meta.unit_id,
                error=f"entrypoint is required for kind={meta.kind}",
            )
        for mode in meta.exec_modes_allowed:
            if mode not in VALID_EXEC_MODES:
                return PublishResult(
                    success=False, unit_id=meta.unit_id,
                    error=f"Invalid exec_mode: {mode}",
                )

        dest_dir = store_root / namespace / name / version
        if not is_path_within(dest_dir, store_root):
            return PublishResult(
                success=False, unit_id=meta.unit_id,
                error="Path traversal detected in publish destination",
            )
        if dest_dir.exists():
            return PublishResult(
                success=False, unit_id=meta.unit_id, version=version,
                error=f"Unit already exists at {dest_dir}",
            )

        try:
            shutil.copytree(str(source_dir), str(dest_dir), symlinks=False)
        except Exception as e:
            return PublishResult(
                success=False, unit_id=meta.unit_id, error=f"Failed to copy: {e}",
            )

        self._audit("unit_published", True, {
            "store_id": store_id,
            "unit_id": meta.unit_id,
            "version": version,
            "kind": meta.kind,
            "namespace": namespace,
            "name": name,
        })
        return PublishResult(success=True, unit_id=meta.unit_id, version=version)

    @staticmethod
    def compute_entrypoint_sha256(unit_dir: Path, entrypoint: str) -> Optional[str]:
        ep_path = unit_dir / entrypoint
        if not ep_path.exists():
            return None
        if not is_path_within(ep_path, unit_dir):
            return None
        h = hashlib.sha256()
        with open(ep_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _load_unit_json(
        self,
        unit_json_path: Path,
        unit_dir: Path,
        namespace: str,
        name: str,
    ) -> Optional[UnitMeta]:
        try:
            with open(unit_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            return UnitMeta(
                unit_id=data.get("unit_id", ""),
                version=data.get("version", ""),
                kind=data.get("kind", "data"),
                entrypoint=data.get("entrypoint"),
                declared_by_pack_id=data.get("declared_by_pack_id", ""),
                declared_at=data.get("declared_at", ""),
                requires_individual_approval=data.get("requires_individual_approval", True),
                exec_modes_allowed=data.get("exec_modes_allowed", []),
                permission_id=data.get("permission_id", ""),
                unit_dir=unit_dir,
                namespace=namespace,
                name=name,
            )
        except Exception:
            return None

    @staticmethod
    def _audit(event_type: str, success: bool, details: Dict[str, Any]) -> None:
        try:
            from .audit_logger import get_audit_logger
            get_audit_logger().log_system_event(
                event_type=event_type, success=success, details=details,
            )
        except Exception:
            pass


_global_unit_registry: Optional[UnitRegistry] = None
_unit_lock = threading.Lock()


def get_unit_registry() -> UnitRegistry:
    global _global_unit_registry
    if _global_unit_registry is None:
        with _unit_lock:
            if _global_unit_registry is None:
                _global_unit_registry = UnitRegistry()
    return _global_unit_registry
