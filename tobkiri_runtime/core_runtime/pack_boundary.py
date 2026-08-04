"""Finite Pack boundary resolver backed by the canonical v4 catalog.

Runtime code may resolve only an explicitly named Pack from the generated v4
catalog.  This module intentionally has no directory enumeration, globbing, or
manifest discovery fallback.
"""

from __future__ import annotations

import json
import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Mapping

from .validation import validate_pack_id


_CATALOG_PATH = Path(__file__).resolve().parents[1] / "schemas" / "pack_v4_catalog.v1.json"


class PackBoundaryError(RuntimeError):
    """Raised when an explicit Pack is absent from the canonical catalog."""


def load_pack_catalog(catalog_path: Path | None = None) -> dict[str, Mapping[str, Any]]:
    """Load the finite generated v4 Pack catalog keyed by Pack ID."""
    path = Path(catalog_path or _CATALOG_PATH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackBoundaryError(f"canonical Pack v4 catalog is unavailable: {path}") from exc
    records = payload.get("packs") if isinstance(payload, Mapping) else None
    if not isinstance(records, list):
        raise PackBoundaryError("canonical Pack v4 catalog has no packs list")
    result: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise PackBoundaryError("canonical Pack v4 catalog contains a malformed record")
        pack_id = str(record.get("pack_id") or "").strip()
        if not pack_id or not validate_pack_id(pack_id) or pack_id in result:
            raise PackBoundaryError(f"canonical Pack v4 catalog has invalid Pack ID: {pack_id!r}")
        result[pack_id] = dict(record)
    return result


def resolve_pack_root(
    pack_id: str,
    ecosystem_dir: Path | str | None = None,
) -> Path:
    """Resolve one explicitly selected Pack root; never enumerate siblings."""
    normalized = str(pack_id or "").strip()
    catalog = load_pack_catalog()
    if normalized not in catalog:
        raise PackBoundaryError(f"Pack is absent from the canonical v4 catalog: {normalized}")
    root = Path(ecosystem_dir) if ecosystem_dir is not None else _CATALOG_PATH.parent.parent / "ecosystem"
    pack_root = (root / normalized).resolve()
    try:
        pack_root.relative_to(root.resolve())
    except ValueError as exc:
        raise PackBoundaryError(f"Pack root escapes the ecosystem boundary: {normalized}") from exc
    if not pack_root.is_dir():
        raise PackBoundaryError(f"cataloged Pack root is missing: {normalized}")
    return pack_root


def resolve_selected_pack_roots(
    pack_ids: list[str] | tuple[str, ...],
    ecosystem_dir: Path | str | None = None,
) -> dict[str, Path]:
    """Resolve exactly the supplied Pack IDs in deterministic order."""
    normalized = tuple(sorted({str(item).strip() for item in pack_ids if str(item).strip()}))
    if len(normalized) != len(pack_ids):
        raise PackBoundaryError("selected Pack IDs must be unique and non-empty")
    return {pack_id: resolve_pack_root(pack_id, ecosystem_dir) for pack_id in normalized}


def declared_pack_dependencies(pack_id: str) -> tuple[str, ...]:
    """Return only catalog-declared Pack dependencies for one Pack."""
    record = load_pack_catalog().get(str(pack_id).strip())
    if record is None:
        raise PackBoundaryError(f"Pack is absent from the canonical v4 catalog: {pack_id}")
    dependencies = record.get("dependencies")
    if not isinstance(dependencies, Mapping):
        return ()
    result = tuple(sorted(str(item).strip() for item in dependencies if str(item).strip()))
    catalog_ids = load_pack_catalog()
    if any(item not in catalog_ids for item in result):
        raise PackBoundaryError(f"Pack {pack_id} declares an unknown v4 dependency")
    return result


def finite_children(root: Path, *, directories_only: bool = False) -> tuple[Path, ...]:
    """Return direct children of an already-resolved Pack or staging root."""
    if not root.is_dir():
        return ()
    try:
        entries = tuple(os.scandir(root))
    except OSError:
        return ()
    paths = [Path(entry.path) for entry in entries if not directories_only or entry.is_dir()]
    return tuple(sorted(paths))


def finite_files(
    root: Path,
    suffixes: tuple[str, ...],
    *,
    recursive: bool = False,
) -> tuple[Path, ...]:
    """Return files from one selected boundary, never from sibling Packs."""
    if not root.is_dir():
        return ()
    result: list[Path] = []
    walker = os.walk(root) if recursive else ((str(root), (), tuple(path.name for path in finite_children(root)),),)
    for current, _directories, names in walker:
        for name in names:
            path = Path(current) / name
            if path.is_file() and path.suffix.lower() in suffixes:
                result.append(path)
    return tuple(sorted(result))


def finite_matching_files(root: Path, patterns: tuple[str, ...]) -> tuple[Path, ...]:
    """Return direct files matching explicit names or glob patterns."""
    return tuple(
        path
        for path in finite_children(root)
        if path.is_file() and any(fnmatch(path.name, pattern) for pattern in patterns)
    )


__all__ = [
    "PackBoundaryError",
    "declared_pack_dependencies",
    "finite_children",
    "finite_files",
    "finite_matching_files",
    "load_pack_catalog",
    "resolve_pack_root",
    "resolve_selected_pack_roots",
]
