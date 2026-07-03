"""Compatibility bridge for legacy transport -> block dispatch.

Transport code should not import individual block handlers directly. This
module centralizes the legacy adapter path so block-backed transports can
continue to work while function-first routes become the primary path.
"""

from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from typing import Any, Dict

_PACK_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACK_ROOT.parent.parent
_PACK_LOCAL_PACKAGES = ("blocks", "domain", "transport", "ecosystem")
_IMPORT_LOCK = threading.RLock()


def _path_is_inside_pack(path: Path) -> bool:
    try:
        path.resolve().relative_to(_PACK_ROOT)
        return True
    except (OSError, ValueError):
        return False


def _path_contains_pack(path: Path) -> bool:
    try:
        _PACK_ROOT.resolve().relative_to(path.resolve())
        return True
    except (OSError, ValueError):
        return False


def _module_is_from_pack(module: Any) -> bool:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        module_paths = getattr(module, "__path__", None)
        if module_paths is None:
            return False
        return any(
            _path_is_inside_pack(Path(item)) or _path_contains_pack(Path(item))
            for item in module_paths
        )
    return _path_is_inside_pack(Path(module_file))


def _drop_foreign_top_level_package(package_name: str) -> None:
    module = sys.modules.get(package_name)
    if module is None or _module_is_from_pack(module):
        return
    prefix = package_name + "."
    for loaded_name in list(sys.modules):
        if loaded_name == package_name or loaded_name.startswith(prefix):
            sys.modules.pop(loaded_name, None)


def _prepare_pack_imports() -> None:
    pack_root = str(_PACK_ROOT)
    sys.path = [item for item in sys.path if item != pack_root]
    repo_root = str(_REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    sys.path.insert(0, pack_root)
    for package_name in _PACK_LOCAL_PACKAGES:
        _drop_foreign_top_level_package(package_name)


def invoke_block(module_name: str, input_data: Dict[str, Any], context: Dict[str, Any]) -> Any:
    # The standalone HTTP server handles UI bootstrap requests concurrently.
    # Import preparation mutates sys.path/sys.modules, so keep it serialized.
    with _IMPORT_LOCK:
        _prepare_pack_imports()
        module = importlib.import_module(module_name)
    handler = getattr(module, "run", None)
    if handler is None:
        raise AttributeError(f"run not found in {module_name}")
    return handler(input_data, context)
