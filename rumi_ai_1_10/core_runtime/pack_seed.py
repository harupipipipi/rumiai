"""Seed bundled packs into the managed user-data pack store."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .paths import (
    BUNDLED_LEGACY_ECOSYSTEM_DIR,
    MANAGED_PACKS_DIR,
    PACK_SEEDS_DIR,
    find_ecosystem_json,
)

CURRENT_SCHEMA = "rumi.pack_current.v1"


class PackSeedError(RuntimeError):
    """Raised when a seed pack cannot be installed."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_current_pointer(pack_id: str, managed_dir: Path | None = None) -> dict[str, Any] | None:
    pack_root = (managed_dir or MANAGED_PACKS_DIR) / pack_id
    pointer = pack_root / "current.json"
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def current_pointer_target(pack_id: str, managed_dir: Path | None = None) -> Path | None:
    pack_root = (managed_dir or MANAGED_PACKS_DIR) / pack_id
    current = read_current_pointer(pack_id, managed_dir)
    if not current:
        return None
    if current.get("schema") != CURRENT_SCHEMA or current.get("pack_id") != pack_id:
        return None
    rel = current.get("path")
    if not isinstance(rel, str) or not rel:
        return None
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts or "\x00" in rel:
        return None
    target = pack_root / rel_path
    try:
        target.resolve().relative_to(pack_root.resolve())
    except (OSError, ValueError):
        return None
    eco, _ = find_ecosystem_json(target)
    if eco is None:
        return None
    return target


def write_current_pointer_atomic(
    pack_id: str,
    version: str,
    path: str | Path,
    managed_dir: Path | None = None,
) -> Path:
    pack_root = (managed_dir or MANAGED_PACKS_DIR) / pack_id
    pack_root.mkdir(parents=True, exist_ok=True)
    rel_path = Path(path)
    if rel_path.is_absolute() or ".." in rel_path.parts or "\x00" in str(path):
        raise PackSeedError(f"unsafe current pointer path for {pack_id}: {path}")
    pointer = {
        "schema": CURRENT_SCHEMA,
        "pack_id": pack_id,
        "version": version,
        "path": rel_path.as_posix(),
        "updated_at": utc_now_iso(),
    }
    target = pack_root / "current.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def ensure_managed_defaultspack_installed() -> dict[str, Any]:
    return ensure_seed_pack_installed("defaultspack")


def ensure_seed_pack_installed(pack_id: str) -> dict[str, Any]:
    seed_dir, source = _seed_source_for_pack(pack_id)
    existing = current_pointer_target(pack_id)
    if existing is not None:
        current = read_current_pointer(pack_id) or {}
        seed_upgrade = _seed_upgrade_candidate(pack_id, current, seed_dir, managed_dir=MANAGED_PACKS_DIR)
        if seed_upgrade is not None:
            return install_seed_pack(pack_id, seed_upgrade, MANAGED_PACKS_DIR, source=source)
        return {
            "installed": False,
            "pack_id": pack_id,
            "version": current.get("version"),
            "path": str(existing),
            "reason": "current_valid",
        }

    if not seed_dir.is_dir():
        raise PackSeedError(f"Seed pack not found for {pack_id}")
    return install_seed_pack(pack_id, seed_dir, MANAGED_PACKS_DIR, source=source)


def _seed_source_for_pack(pack_id: str) -> tuple[Path, str]:
    seed_dir = PACK_SEEDS_DIR / pack_id
    if seed_dir.is_dir():
        return seed_dir, "seed"
    return BUNDLED_LEGACY_ECOSYSTEM_DIR / pack_id, "legacy_seed_migration"


def _seed_upgrade_candidate(
    pack_id: str,
    current: Mapping[str, Any],
    seed_dir: Path,
    *,
    managed_dir: Path,
) -> Path | None:
    if not seed_dir.is_dir():
        return None
    current_version = str(current.get("version") or "")
    if not current_version:
        return None
    record = _read_install_record(pack_id, managed_dir)
    if record.get("source") not in {"seed", "legacy_seed_migration"}:
        return None
    if record.get("pack_id") != pack_id or str(record.get("version") or "") != current_version:
        return None
    eco_json, pack_subdir = find_ecosystem_json(seed_dir)
    if eco_json is None or pack_subdir is None:
        return None
    manifest = _read_json(pack_subdir / "rumi-pack.json")
    ecosystem = _read_json(eco_json)
    declared_id = str((manifest or {}).get("pack_id") or ecosystem.get("pack_id") or pack_id)
    if declared_id != pack_id:
        raise PackSeedError(f"Seed pack id mismatch: expected {pack_id}, got {declared_id}")
    seed_version = _seed_version(manifest, ecosystem)
    _validate_version_path(seed_version)
    return seed_dir if _version_newer(seed_version, current_version) else None


def _read_install_record(pack_id: str, managed_dir: Path) -> dict[str, Any]:
    record_path = managed_dir / pack_id / "install_record.json"
    try:
        data = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def install_seed_pack(
    pack_id: str,
    seed_dir: Path,
    managed_dir: Path,
    *,
    source: str = "seed",
) -> dict[str, Any]:
    eco_json, pack_subdir = find_ecosystem_json(seed_dir)
    if eco_json is None or pack_subdir is None:
        raise PackSeedError(f"Seed pack {pack_id} is missing ecosystem.json")

    manifest = _read_json(pack_subdir / "rumi-pack.json")
    ecosystem = _read_json(eco_json)
    declared_id = str((manifest or {}).get("pack_id") or ecosystem.get("pack_id") or pack_id)
    if declared_id != pack_id:
        raise PackSeedError(f"Seed pack id mismatch: expected {pack_id}, got {declared_id}")
    version = _seed_version(manifest, ecosystem)
    _validate_version_path(version)

    pack_root = managed_dir / pack_id
    version_dir = pack_root / "versions" / version
    version_dir.parent.mkdir(parents=True, exist_ok=True)
    if not version_dir.exists():
        _copy_seed_tree(pack_subdir, version_dir)

    write_current_pointer_atomic(pack_id, version, Path("versions") / version, managed_dir)
    record = {
        "schema": "rumi.pack_install_record.v1",
        "pack_id": pack_id,
        "version": version,
        "source": source,
        "seed_dir": str(seed_dir),
        "installed_at": utc_now_iso(),
        "current_pointer": "current.json",
    }
    _write_json_atomic(pack_root / "install_record.json", record)
    return {
        "installed": True,
        "pack_id": pack_id,
        "version": version,
        "path": str(version_dir),
        "source": source,
    }


def _seed_version(manifest: Mapping[str, Any] | None, ecosystem: Mapping[str, Any]) -> str:
    if manifest and manifest.get("version"):
        return str(manifest["version"])
    if ecosystem.get("version"):
        return str(ecosystem["version"])
    return "0.0.0-seed"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PackSeedError(f"Expected JSON object: {path}")
    return data


def _validate_version_path(version: str) -> None:
    rel = Path(version)
    if rel.is_absolute() or ".." in rel.parts or "/" in version or "\\" in version or "\x00" in version:
        raise PackSeedError(f"Unsafe pack version: {version}")


def _version_newer(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def _version_tuple(version: str) -> tuple[int, int, int]:
    clean = str(version or "").strip().removeprefix("v").split("-", 1)[0].split("+", 1)[0]
    parts = clean.split(".")
    if len(parts) != 3:
        return (0, 0, 0)
    parsed: list[int] = []
    for part in parts:
        try:
            parsed.append(int(part))
        except ValueError:
            parsed.append(0)
    return (parsed[0], parsed[1], parsed[2])


def _copy_seed_tree(src: Path, dst: Path) -> None:
    def ignore(_current: str, names: list[str]) -> set[str]:
        return {
            name for name in names
            if name in {"state", "staging", "backups", "secrets", "user_data"}
            or name.endswith(".local")
        }

    shutil.copytree(src, dst, symlinks=False, ignore=ignore)


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
