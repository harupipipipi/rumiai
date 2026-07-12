from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any

_LEGACY_PREFIXES = {
    "blocks.": "ecosystem.defaultspack.blocks.",
    "bridge.": "ecosystem.defaultspack.bridge.",
    "domain.": "ecosystem.defaultspack.domain.",
    "transport.": "ecosystem.defaultspack.transport.",
}


def normalize_module_name(module_name: str) -> str:
    name = str(module_name or "").strip()
    if not name:
        raise ValueError("module name is required")
    if name.startswith("ecosystem.defaultspack."):
        return name
    for legacy_prefix, canonical_prefix in _LEGACY_PREFIXES.items():
        if name.startswith(legacy_prefix):
            return canonical_prefix + name[len(legacy_prefix) :]
    return name


def _register_aliases(module: ModuleType, original_name: str, canonical_name: str) -> None:
    aliases = {canonical_name, original_name}
    for legacy_prefix, canonical_prefix in _LEGACY_PREFIXES.items():
        if canonical_name.startswith(canonical_prefix):
            aliases.add(legacy_prefix + canonical_name[len(canonical_prefix) :])
    for alias in aliases:
        registered = sys.modules.setdefault(alias, module)
        parent_name, separator, child_name = alias.rpartition(".")
        parent = sys.modules.get(parent_name) if separator else None
        if parent is not None:
            setattr(parent, child_name, registered)


def import_module(module_name: str) -> ModuleType:
    original_name = str(module_name or "").strip()
    canonical_name = normalize_module_name(original_name)
    try:
        module = importlib.import_module(canonical_name)
    except ModuleNotFoundError:
        if canonical_name == original_name:
            raise
        module = importlib.import_module(original_name)
    _register_aliases(module, original_name or canonical_name, canonical_name)
    return module


def import_entrypoint(entrypoint: str) -> Any:
    raw = str(entrypoint or "").strip()
    if ":" not in raw:
        raise ValueError(f"invalid entrypoint format: {raw}")
    module_name, attr_name = raw.split(":", 1)
    module = import_module(module_name)
    return getattr(module, attr_name)
