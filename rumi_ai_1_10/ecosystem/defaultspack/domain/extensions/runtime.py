from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from .registry import ExtensionRegistry

_LOCK = threading.Lock()
_REGISTRY: Optional[ExtensionRegistry] = None


def get_extensions_root() -> Path:
    # .../ecosystem/defaultspack/domain/extensions/runtime.py -> .../defaultspack
    pack_root = Path(__file__).resolve().parents[2]
    return pack_root / "extensions"


def get_extension_registry(
    *,
    force_reload: bool = False,
    strict: bool = False,
) -> ExtensionRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        with _LOCK:
            if _REGISTRY is None:
                _REGISTRY = ExtensionRegistry(get_extensions_root(), strict=strict)
    if force_reload:
        _REGISTRY.reload()
    return _REGISTRY

