"""Managed pack-store helpers."""

from __future__ import annotations

from pathlib import Path

from .pack_seed import current_pointer_target, read_current_pointer
from .paths import MANAGED_PACKS_DIR


def pack_root(pack_id: str, managed_dir: Path | None = None) -> Path:
    return (managed_dir or MANAGED_PACKS_DIR) / pack_id


def active_pack_dir(pack_id: str, managed_dir: Path | None = None) -> Path | None:
    return current_pointer_target(pack_id, managed_dir)


def active_pack_version(pack_id: str, managed_dir: Path | None = None) -> str | None:
    current = read_current_pointer(pack_id, managed_dir)
    if not current:
        return None
    version = current.get("version")
    return str(version) if version else None


def version_dir(pack_id: str, version: str, managed_dir: Path | None = None) -> Path:
    return pack_root(pack_id, managed_dir) / "versions" / version
