from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterable, Optional

from .activation import selected_extension_pack_ids
from .registry import ExtensionRegistry

_LOCK = threading.Lock()
_REGISTRY: Optional[ExtensionRegistry] = None
_EXTRA_EXTENSION_ROOTS_ENV = "RUMI_DEFAULTSPACK_EXTENSION_ROOTS"


def get_extensions_root() -> Path:
    # .../ecosystem/defaultspack/domain/extensions/runtime.py -> .../defaultspack
    pack_root = Path(__file__).resolve().parents[2]
    return pack_root / "extensions"


def _coerce_extension_root(path: Path | str) -> Path:
    candidate = Path(path).expanduser()
    if (candidate / "ecosystem.json").is_file():
        return candidate / "extensions"
    return candidate


def _append_unique_root(roots: list[Path], root: Path | str) -> None:
    candidate = _coerce_extension_root(root)
    if candidate not in roots:
        roots.append(candidate)


def _pack_roots_in_ecosystem_dir(
    ecosystem_dir: Path,
    *,
    selected_pack_ids: set[str] | None = None,
) -> list[Path]:
    if not ecosystem_dir.is_dir():
        return []
    roots: list[Path] = []
    for path in sorted(ecosystem_dir.iterdir()):
        if selected_pack_ids is not None and path.name not in selected_pack_ids:
            continue
        extensions = path / "extensions"
        if path.is_dir() and (path / "ecosystem.json").is_file() and extensions.is_dir():
            roots.append(path)
    return roots


def _append_resolved_extension_roots(
    roots: list[Path],
    root: Path | str,
    *,
    selected_pack_ids: set[str] | None = None,
    allow_direct_root: bool = True,
) -> None:
    candidate = Path(root).expanduser()
    if (candidate / "ecosystem.json").is_file():
        _append_unique_root(roots, candidate)
        return
    for ecosystem_dir in (candidate, candidate / "ecosystem"):
        pack_roots = _pack_roots_in_ecosystem_dir(
            ecosystem_dir,
            selected_pack_ids=selected_pack_ids,
        )
        if not pack_roots:
            continue
        for pack_root in pack_roots:
            _append_unique_root(roots, pack_root)
        return
    if allow_direct_root:
        _append_unique_root(roots, candidate)


def _extra_extension_roots_from_env(raw: str | None = None) -> list[Path]:
    roots: list[Path] = []
    sources = (
        [(raw, True)]
        if raw is not None
        else [
            (os.environ.get(_EXTRA_EXTENSION_ROOTS_ENV, ""), True),
            (os.environ.get("RUMI_APP_DIR", ""), False),
            (os.environ.get("RUMI_HOME", ""), False),
        ]
    )
    for value, allow_direct_root in sources:
        for item in str(value or "").split(os.pathsep):
            item = item.strip()
            if not item:
                continue
            _append_resolved_extension_roots(
                roots,
                item,
                allow_direct_root=allow_direct_root,
            )
    return roots


def build_extensions_roots(
    pack_root: Path | str,
    *,
    extra_roots: Iterable[Path | str] | None = None,
) -> list[Path]:
    pack_root = Path(pack_root)
    ecosystem_dir = pack_root.parent
    roots: list[Path] = []
    default_root = pack_root / "extensions"
    selected_pack_ids = selected_extension_pack_ids(pack_root)

    # Core defaults must load first so sibling packs and user/env roots can
    # extend or override them by id.
    _append_unique_root(roots, default_root)

    if ecosystem_dir.is_dir():
        for path in sorted(ecosystem_dir.iterdir()):
            extensions = path / "extensions"
            if path == pack_root:
                continue
            if selected_pack_ids is not None and path.name not in selected_pack_ids:
                continue
            if path.is_dir() and (path / "ecosystem.json").is_file() and extensions.is_dir():
                _append_unique_root(roots, extensions)

    _append_unique_root(roots, pack_root / "user_data" / "shared" / "extensions")
    for root in extra_roots or ():
        _append_resolved_extension_roots(
            roots,
            root,
            selected_pack_ids=selected_pack_ids,
        )
    return roots


def get_extensions_roots() -> list[Path]:
    pack_root = Path(__file__).resolve().parents[2]
    return build_extensions_roots(
        pack_root,
        extra_roots=_extra_extension_roots_from_env(),
    )


def get_extension_registry(
    *,
    force_reload: bool = False,
    strict: bool = False,
) -> ExtensionRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        with _LOCK:
            if _REGISTRY is None:
                _REGISTRY = ExtensionRegistry(get_extensions_roots(), strict=strict)
    elif force_reload:
        with _LOCK:
            if _REGISTRY is None:
                _REGISTRY = ExtensionRegistry(get_extensions_roots(), strict=strict)
            else:
                roots = get_extensions_roots()
                _REGISTRY._roots = [Path(root) for root in roots]
                _REGISTRY._root = _REGISTRY._roots[0] if _REGISTRY._roots else Path(".")
                _REGISTRY._strict = strict
                _REGISTRY.reload()
    return _REGISTRY
