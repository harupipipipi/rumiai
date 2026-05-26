from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Iterable, Optional

from .activation import selected_extension_pack_ids
from .registry import ExtensionRegistry

_LOCK = threading.Lock()
_REGISTRY: Optional[ExtensionRegistry] = None
_EXTRA_EXTENSION_ROOTS_ENV = "RUMI_DEFAULTSPACK_EXTENSION_ROOTS"
_APP_ECOSYSTEM_ENVS = ("RUMI_APP_DIR", "RUMI_CORE_DIR")


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


def _pack_id_for_root(pack_root: Path) -> str:
    for manifest_name in ("rumi-pack.json", "ecosystem.json"):
        manifest_path = pack_root / manifest_name
        if not manifest_path.is_file():
            continue
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        for key in ("pack_id", "id"):
            value = str(raw.get(key) or "").strip()
            if value:
                return value
    return pack_root.name


def _append_ecosystem_extension_roots(
    roots: list[Path],
    ecosystem_dir: Path,
    *,
    pack_root: Path,
    selected_pack_ids: set[str] | None,
) -> None:
    if not ecosystem_dir.is_dir():
        return
    active_pack_name = pack_root.name
    active_pack_id = _pack_id_for_root(pack_root)
    for path in sorted(ecosystem_dir.iterdir()):
        extensions = path / "extensions"
        if path == pack_root or path.name in {active_pack_name, active_pack_id}:
            continue
        if selected_pack_ids is not None and path.name not in selected_pack_ids:
            continue
        if path.is_dir() and (path / "ecosystem.json").is_file() and extensions.is_dir():
            _append_unique_root(roots, extensions)


def _extra_extension_roots_from_env(raw: str | None = None) -> list[Path]:
    value = os.environ.get(_EXTRA_EXTENSION_ROOTS_ENV, "") if raw is None else raw
    roots: list[Path] = []
    for item in value.split(os.pathsep):
        item = item.strip()
        if not item:
            continue
        _append_unique_root(roots, item)
    return roots


def _app_ecosystem_dirs_from_env() -> list[Path]:
    dirs: list[Path] = []
    for env_name in _APP_ECOSYSTEM_ENVS:
        raw = str(os.environ.get(env_name, "") or "").strip()
        if not raw:
            continue
        app_dir = Path(raw).expanduser()
        candidates = [app_dir / "ecosystem"]
        if app_dir.name == "ecosystem":
            candidates.insert(0, app_dir)
        for candidate in candidates:
            if candidate.is_dir() and candidate not in dirs:
                dirs.append(candidate)
    return dirs


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

    _append_ecosystem_extension_roots(
        roots,
        ecosystem_dir,
        pack_root=pack_root,
        selected_pack_ids=selected_pack_ids,
    )
    for app_ecosystem_dir in _app_ecosystem_dirs_from_env():
        _append_ecosystem_extension_roots(
            roots,
            app_ecosystem_dir,
            pack_root=pack_root,
            selected_pack_ids=selected_pack_ids,
        )

    _append_unique_root(roots, pack_root / "user_data" / "shared" / "extensions")
    for root in extra_roots or ():
        _append_unique_root(roots, root)
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
