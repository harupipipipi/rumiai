"""
pack_importer.py - Pack import (directory/zip/rumipack) to staging

- Zip Slip 対策
- 単一トップディレクトリ強制
- ファイル数/サイズ上限
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from .paths import find_ecosystem_json


DEFAULT_MAX_FILES = 2000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_SINGLE_FILE_BYTES = 200 * 1024 * 1024


@dataclass
class PackImportResult:
    success: bool
    staging_id: Optional[str] = None
    pack_ids: List[str] = None
    error: Optional[str] = None
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "staging_id": self.staging_id,
            "pack_ids": self.pack_ids or [],
            "error": self.error,
            "meta": self.meta or {},
        }


class PackImporter:
    DEFAULT_STAGING_ROOT = "user_data/pack_staging"

    def __init__(self, staging_root: str = None):
        self._staging_root = Path(staging_root) if staging_root else Path(self.DEFAULT_STAGING_ROOT)
        self._staging_root.mkdir(parents=True, exist_ok=True)

        self._max_files = int(os.environ.get("RUMI_IMPORT_MAX_FILES", DEFAULT_MAX_FILES))
        self._max_uncompressed_bytes = int(
            os.environ.get("RUMI_IMPORT_MAX_UNCOMPRESSED_BYTES", DEFAULT_MAX_UNCOMPRESSED_BYTES)
        )
        self._max_single_file_bytes = int(
            os.environ.get("RUMI_IMPORT_MAX_SINGLE_FILE_BYTES", DEFAULT_MAX_SINGLE_FILE_BYTES)
        )

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def import_pack(self, source_path: str, notes: str = "", actor: str = "api_user") -> PackImportResult:
        self._audit_event("pack_import_started", True, {
            "source_path": source_path,
            "actor": actor,
        })
        try:
            staging_id = uuid.uuid4().hex
            staging_dir = self._staging_root / staging_id
            payload_dir = staging_dir / "payload"
            work_dir = staging_dir / "_import"
            payload_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=True)

            src = Path(source_path)
            if not src.is_absolute():
                src = (Path.cwd() / src).resolve()

            if not src.exists():
                raise ValueError("source_not_found")

            source_type = self._detect_source_type(src)
            if source_type == "directory":
                top_dir = self._prepare_directory_source(src)
                self._copy_directory_contents(top_dir, payload_dir)
            else:
                top_dir_name = self._extract_archive(src, work_dir)
                top_dir = work_dir / top_dir_name
                if not top_dir.exists() or not top_dir.is_dir():
                    raise ValueError("invalid_top_directory")
                self._copy_directory_contents(top_dir, payload_dir)

            pack_ids = self._detect_pack_ids(payload_dir)
            meta = {
                "staging_id": staging_id,
                "source_path": str(src),
                "source_type": source_type,
                "notes": notes,
                "imported_at": self._now_ts(),
                "pack_ids": pack_ids,
            }
            (staging_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            result = PackImportResult(True, staging_id=staging_id, pack_ids=pack_ids, meta=meta)
            self._audit_event("pack_import_completed", True, {
                "staging_id": staging_id,
                "pack_ids": pack_ids,
            })
            return result

        except Exception as e:
            self._audit_event("pack_import_failed", False, {
                "source_path": source_path,
                "error": str(e),
            })
            return PackImportResult(False, error=str(e))

    def _detect_source_type(self, src: Path) -> str:
        if src.is_dir():
            return "directory"
        suffix = src.suffix.lower()
        if suffix == ".zip":
            return "zip"
        if suffix == ".rumipack":
            return "rumipack"
        raise ValueError("unsupported_source_type")

    def _prepare_directory_source(self, src: Path) -> Path:
        if not src.is_dir():
            raise ValueError("source_not_directory")
        entries = [p for p in src.iterdir() if not p.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        if (src / "ecosystem.json").exists() or (src / "packs").exists():
            return src
        raise ValueError("invalid_top_directory")

    def _detect_pack_ids(self, payload_dir: Path) -> List[str]:
        packs_dir = payload_dir / "packs"
        if packs_dir.exists() and packs_dir.is_dir():
            pack_ids = []
            for pack_dir in sorted(packs_dir.iterdir()):
                if not pack_dir.is_dir():
                    continue
                eco_json, _ = find_ecosystem_json(pack_dir)
                if eco_json is None:
                    raise ValueError(f"ecosystem_json_not_found:{pack_dir.name}")
                pack_ids.append(pack_dir.name)
            if not pack_ids:
                raise ValueError("no_packs_found")
            return pack_ids

        eco_json, _ = find_ecosystem_json(payload_dir)
        if eco_json is None:
            raise ValueError("ecosystem_json_not_found")
        try:
            data = json.loads(eco_json.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        pack_id = data.get("pack_id")
        if not pack_id:
            raise ValueError("pack_id_missing")
        return [pack_id]

    def _extract_archive(self, src: Path, work_dir: Path) -> str:
        if not src.exists():
            raise ValueError("source_not_found")

        with zipfile.ZipFile(src, "r") as zf:
            entries = [e for e in zf.infolist() if e.filename and not e.filename.endswith("/")]
            self._validate_zip_entries(entries)
            top_dir_name = self._validate_top_level(entries)
            for entry in entries:
                self._safe_extract_entry(zf, entry, work_dir)
            return top_dir_name

    def _validate_top_level(self, entries: List[zipfile.ZipInfo]) -> str:
        top_dirs = set()
        for entry in entries:
            normalized = entry.filename.replace("\\", "/")
            parts = PurePosixPath(normalized).parts
            if not parts:
                continue
            top_dirs.add(parts[0])
        if len(top_dirs) != 1:
            raise ValueError("invalid_top_directory")
        top_dir = next(iter(top_dirs))
        if not top_dir or top_dir in (".", ".."):
            raise ValueError("invalid_top_directory")
        return top_dir

    def _validate_zip_entries(self, entries: List[zipfile.ZipInfo]) -> None:
        if len(entries) > self._max_files:
            raise ValueError("zip_too_many_files")

        total_size = 0
        for entry in entries:
            normalized = entry.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("zip_slip_detected")
            if self._is_symlink(entry):
                raise ValueError("zip_symlink_detected")
            if entry.file_size > self._max_single_file_bytes:
                raise ValueError("zip_file_too_large")
            total_size += entry.file_size
            if total_size > self._max_uncompressed_bytes:
                raise ValueError("zip_uncompressed_too_large")

    def _safe_extract_entry(self, zf: zipfile.ZipFile, entry: zipfile.ZipInfo, dest_dir: Path) -> None:
        normalized = entry.filename.replace("\\", "/")
        target_path = (dest_dir / normalized).resolve()
        try:
            target_path.relative_to(dest_dir.resolve())
        except ValueError:
            raise ValueError("zip_slip_detected")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(entry, "r") as src_f, open(target_path, "wb") as dst_f:
            shutil.copyfileobj(src_f, dst_f)

    def _is_symlink(self, entry: zipfile.ZipInfo) -> bool:
        if entry.create_system != 3:
            return False
        mode = entry.external_attr >> 16
        return (mode & 0o170000) == 0o120000

    def _copy_directory_contents(self, src_dir: Path, dest_dir: Path) -> None:
        file_count = 0
        total_size = 0
        src_dir = src_dir.resolve()
        for root, dirs, files in os.walk(src_dir):
            root_path = Path(root)
            if root_path.is_symlink():
                raise ValueError("symlink_detected")
            for dir_name in list(dirs):
                dir_path = root_path / dir_name
                if dir_path.is_symlink():
                    raise ValueError("symlink_detected")
            for file_name in files:
                file_path = root_path / file_name
                if file_path.is_symlink():
                    raise ValueError("symlink_detected")
                file_count += 1
                if file_count > self._max_files:
                    raise ValueError("too_many_files")
                file_size = file_path.stat().st_size
                if file_size > self._max_single_file_bytes:
                    raise ValueError("file_too_large")
                total_size += file_size
                if total_size > self._max_uncompressed_bytes:
                    raise ValueError("total_size_too_large")

        for root, _, files in os.walk(src_dir):
            root_path = Path(root)
            rel_root = root_path.relative_to(src_dir)
            target_root = dest_dir / rel_root
            target_root.mkdir(parents=True, exist_ok=True)
            for file_name in files:
                src_file = root_path / file_name
                if src_file.is_symlink():
                    raise ValueError("symlink_detected")
                shutil.copy2(src_file, target_root / file_name)

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


_global_pack_importer: Optional[PackImporter] = None
_importer_lock = threading.Lock()


def get_pack_importer() -> PackImporter:
    global _global_pack_importer
    if _global_pack_importer is None:
        with _importer_lock:
            if _global_pack_importer is None:
                _global_pack_importer = PackImporter()
    return _global_pack_importer


def reset_pack_importer(staging_root: str = None) -> PackImporter:
    global _global_pack_importer
    with _importer_lock:
        _global_pack_importer = PackImporter(staging_root)
    return _global_pack_importer
