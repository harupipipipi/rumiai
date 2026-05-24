"""Rollback helpers for managed pack current pointers."""

from __future__ import annotations

from pathlib import Path

from ..pack_seed import read_current_pointer, write_current_pointer_atomic
from ..paths import MANAGED_PACKS_DIR, find_ecosystem_json
from .models import RollbackResult
from .versioning import parse_version_tuple, sort_versions


class RollbackError(RuntimeError):
    """Raised when rollback cannot be performed."""


def rollback_pack_version(pack_id: str, version: str | None = None, managed_dir: Path | None = None) -> RollbackResult:
    base = managed_dir or MANAGED_PACKS_DIR
    pack_root = base / pack_id
    current = read_current_pointer(pack_id, base)
    current_version = str((current or {}).get("version") or "")
    target_version = version or _previous_version(pack_root, current_version)
    if not target_version:
        raise RollbackError(f"no rollback version available for {pack_id}")
    target = pack_root / "versions" / target_version
    eco, _ = find_ecosystem_json(target)
    if eco is None:
        raise RollbackError(f"rollback target is invalid: {target_version}")
    write_current_pointer_atomic(pack_id, target_version, Path("versions") / target_version, base)
    return RollbackResult(
        target=f"pack:{pack_id}",
        pack_id=pack_id,
        previous_version=current_version,
        active_version=target_version,
        rolled_back=True,
    )


def rollback_available(pack_id: str, managed_dir: Path | None = None) -> bool:
    base = managed_dir or MANAGED_PACKS_DIR
    pack_root = base / pack_id
    current = read_current_pointer(pack_id, base)
    current_version = str((current or {}).get("version") or "")
    return _previous_version(pack_root, current_version) is not None


def _previous_version(pack_root: Path, current_version: str) -> str | None:
    versions_root = pack_root / "versions"
    if not versions_root.is_dir():
        return None
    versions = sort_versions([
        d.name for d in versions_root.iterdir()
        if d.is_dir() and d.name != current_version and (d / "ecosystem.json").is_file()
    ])
    current_tuple = parse_version_tuple(current_version)
    older = [version for version in versions if parse_version_tuple(version) < current_tuple]
    if older:
        return older[-1]
    return versions[-1] if versions else None
