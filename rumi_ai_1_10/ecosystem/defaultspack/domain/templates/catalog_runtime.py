from __future__ import annotations

import hashlib
import json
import threading
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import default_template_roots
from .models import CURRENT_TEMPLATE_SCHEMA_VERSION


@dataclass(frozen=True)
class TemplateCatalogSnapshot:
    catalog: dict[str, Any]
    generation: str
    source_files: tuple[str, ...]
    diagnostics: tuple[dict[str, Any], ...]


class TemplateCatalogProvider:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshots: dict[tuple[str, tuple[str, ...]], TemplateCatalogSnapshot] = {}

    def get_snapshot(
        self,
        *,
        defaultspack_root: str | Path | None = None,
        roots: list[str | Path] | None = None,
        force_reload: bool = False,
    ) -> TemplateCatalogSnapshot:
        root_key = str(_default_root(defaultspack_root))
        roots_key = tuple(str(Path(root).resolve()) for root in roots or [])
        cache_key = (root_key, roots_key)
        generation, source_files = _catalog_generation(
            defaultspack_root=defaultspack_root,
            roots=roots,
        )
        with self._lock:
            snapshot = self._snapshots.get(cache_key)
            if snapshot is not None and snapshot.generation == generation and not force_reload:
                return snapshot
            catalog = _build_catalog(defaultspack_root=defaultspack_root, roots=roots)
            catalog["catalog_generation"] = generation
            catalog["schema_version"] = CURRENT_TEMPLATE_SCHEMA_VERSION
            diagnostics = tuple(
                dict(item)
                for item in catalog.get("template_diagnostics", [])
                if isinstance(item, dict)
            )
            snapshot = TemplateCatalogSnapshot(
                catalog=deepcopy(catalog),
                generation=generation,
                source_files=tuple(source_files),
                diagnostics=diagnostics,
            )
            self._snapshots[cache_key] = snapshot
            return snapshot

    def invalidate(
        self,
        *,
        defaultspack_root: str | Path | None = None,
    ) -> None:
        root_key = str(_default_root(defaultspack_root))
        with self._lock:
            for cache_key in list(self._snapshots):
                if cache_key[0] == root_key:
                    self._snapshots.pop(cache_key, None)


_PROVIDER = TemplateCatalogProvider()


def get_template_catalog_snapshot(
    *,
    defaultspack_root: str | Path | None = None,
    roots: list[str | Path] | None = None,
    force_reload: bool = False,
) -> TemplateCatalogSnapshot:
    return _PROVIDER.get_snapshot(
        defaultspack_root=defaultspack_root,
        roots=roots,
        force_reload=force_reload,
    )


def invalidate_template_catalog(
    *,
    defaultspack_root: str | Path | None = None,
) -> None:
    _PROVIDER.invalidate(defaultspack_root=defaultspack_root)


def current_template_catalog_generation(
    *,
    defaultspack_root: str | Path | None = None,
    roots: list[str | Path] | None = None,
) -> str:
    return _catalog_generation(defaultspack_root=defaultspack_root, roots=roots)[0]


def _build_catalog(
    *,
    defaultspack_root: str | Path | None,
    roots: list[str | Path] | None,
) -> dict[str, Any]:
    from .projectors import build_template_catalog

    return build_template_catalog(defaultspack_root=defaultspack_root, roots=roots)


def _catalog_generation(
    *,
    defaultspack_root: str | Path | None,
    roots: list[str | Path] | None,
) -> tuple[str, list[str]]:
    root_paths = _template_root_paths(defaultspack_root=defaultspack_root, roots=roots)
    files = _template_files(root_paths)
    payload = {
        "roots": [str(path) for path in root_paths],
        "schema_version": CURRENT_TEMPLATE_SCHEMA_VERSION,
        "files": [
            {
                "path": _relative_template_path(path, root_paths),
                "sha256": _file_sha256(path),
            }
            for path in files
        ],
    }
    generation = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()
    return generation, [str(path) for path in files]


def _template_root_paths(
    *,
    defaultspack_root: str | Path | None,
    roots: list[str | Path] | None,
) -> list[Path]:
    if roots is not None:
        return sorted({Path(root).resolve() for root in roots})
    return sorted(
        {
            template_root.path.resolve()
            for template_root in default_template_roots(defaultspack_root)
        }
    )


def _template_files(root_paths: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in root_paths:
        if root.is_file() and root.name == "template.json":
            files.add(root.resolve())
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("template.json"):
            if path.is_file():
                files.add(path.resolve())
    return sorted(files)


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _relative_template_path(path: Path, roots: list[Path]) -> str:
    resolved = path.resolve()
    for root in roots:
        try:
            return str(resolved.relative_to(root.resolve()))
        except (OSError, ValueError):
            continue
    return resolved.name


def _default_root(defaultspack_root: str | Path | None) -> Path:
    return (
        Path(defaultspack_root).resolve()
        if defaultspack_root is not None
        else Path(__file__).resolve().parents[2]
    )
