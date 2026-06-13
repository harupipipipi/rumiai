"""Manifest-driven Capability Graph binding registration."""

from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .interface_registry import InterfaceRegistry
from .paths import (
    CORE_PACK_DIR,
    CORE_PACK_ID_PREFIX,
    ECOSYSTEM_DIR,
    PackLocation,
    discover_pack_locations,
)


TRUSTED_BUILTIN_PACK_IDS = {"defaultspack", "rumi_default_tools_pack"}


@dataclass
class CapabilityBindingRegistrationResult:
    ok: bool = True
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    registered: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "registered": list(self.registered),
            "skipped": list(self.skipped),
            "diagnostics": list(self.diagnostics),
        }


def register_pack_binding_handlers(
    *,
    interface_registry: InterfaceRegistry,
    approval_manager: Any = None,
    ecosystem_dir: Optional[str] = None,
    registry: Any = None,
) -> CapabilityBindingRegistrationResult:
    """Register explicit pack-owned binding handlers from approved packs."""
    result = CapabilityBindingRegistrationResult()
    for pack_id, pack_location in _iter_pack_locations(registry, ecosystem_dir):
        ok, reason = _is_pack_approved(approval_manager, pack_id)
        if not ok:
            result.skipped.append(pack_id)
            result.diagnostics.append(
                _diagnostic(
                    "warning",
                    "binding_registration_pack_skipped_unapproved",
                    f"Pack '{pack_id}' binding registration skipped: {reason}",
                    pack_id=pack_id,
                    reason=reason,
                )
            )
            continue

        manifest = _read_manifest(pack_location.ecosystem_json_path, result, pack_id)
        register_path = _register_path_from_manifest(manifest)
        if not register_path:
            result.skipped.append(pack_id)
            continue
        if not _register_path_allowed(register_path, pack_id):
            result.ok = False
            result.skipped.append(pack_id)
            result.diagnostics.append(
                _diagnostic(
                    "error",
                    "binding_registration_path_not_allowed",
                    f"Pack '{pack_id}' cannot register binding path '{register_path}'",
                    pack_id=pack_id,
                    register=register_path,
                )
            )
            continue
        ok, reason = _host_registration_allowed(pack_id, pack_location, manifest)
        if not ok:
            result.skipped.append(pack_id)
            result.diagnostics.append(
                _diagnostic(
                    "warning",
                    "binding_registration_host_execution_required",
                    f"Pack '{pack_id}' binding registration skipped: {reason}",
                    pack_id=pack_id,
                    register=register_path,
                    reason=reason,
                )
            )
            continue

        try:
            registered = _call_register_function(
                register_path,
                pack_location=pack_location,
                interface_registry=interface_registry,
            )
        except Exception as exc:
            result.ok = False
            result.skipped.append(pack_id)
            result.diagnostics.append(
                _diagnostic(
                    "error",
                    "binding_registration_failed",
                    f"Pack '{pack_id}' binding registration failed: {exc}",
                    pack_id=pack_id,
                    register=register_path,
                )
            )
            continue

        result.registered.append(pack_id)
        result.diagnostics.append(
            _diagnostic(
                "info",
                "binding_registration_registered",
                f"Pack '{pack_id}' binding handlers are registered",
                pack_id=pack_id,
                register=register_path,
                registered=registered,
            )
        )
    return result


def _iter_pack_locations(registry: Any, ecosystem_dir: Optional[str]) -> List[Tuple[str, PackLocation]]:
    if registry is not None and isinstance(getattr(registry, "packs", None), dict):
        pairs = []
        for pack_id, pack_info in registry.packs.items():
            eco_path = getattr(pack_info, "ecosystem_json_path", None)
            pack_subdir = getattr(pack_info, "pack_subdir", None) or getattr(pack_info, "subdir", None) or getattr(pack_info, "path", None)
            pack_dir = getattr(pack_info, "pack_dir", None) or pack_subdir
            if eco_path and pack_subdir and pack_dir:
                pairs.append(
                    (
                        str(pack_id),
                        PackLocation(
                            pack_dir=Path(pack_dir),
                            pack_id=str(pack_id),
                            ecosystem_json_path=Path(eco_path),
                            pack_subdir=Path(pack_subdir),
                        ),
                    )
                )
        if pairs:
            return pairs
    return [(loc.pack_id, loc) for loc in discover_pack_locations(ecosystem_dir)]


def _is_pack_approved(approval_manager: Any, pack_id: str) -> Tuple[bool, Optional[str]]:
    if approval_manager is None:
        try:
            from .approval_manager import get_approval_manager

            approval_manager = get_approval_manager()
        except Exception:
            return False, "approval_manager_unavailable"
    checker = getattr(approval_manager, "is_pack_approved_and_verified", None)
    if not callable(checker):
        return False, "approval_checker_unavailable"
    try:
        checked = checker(pack_id)
    except Exception as exc:
        return False, f"approval_check_error:{exc}"
    if isinstance(checked, tuple):
        return bool(checked[0]), checked[1] if len(checked) > 1 else None
    return bool(checked), None


def _read_manifest(path: Path, result: CapabilityBindingRegistrationResult, pack_id: str) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        result.ok = False
        result.diagnostics.append(
            _diagnostic(
                "error",
                "binding_registration_manifest_unreadable",
                f"Pack '{pack_id}' ecosystem.json could not be read: {exc}",
                pack_id=pack_id,
                path=str(path),
            )
        )
        return {}
    return data if isinstance(data, dict) else {}


def _register_path_from_manifest(manifest: Dict[str, Any]) -> Optional[str]:
    capability_bindings = manifest.get("capability_bindings")
    if isinstance(capability_bindings, dict) and isinstance(capability_bindings.get("register"), str):
        return capability_bindings["register"].strip() or None
    return None


def _register_path_allowed(register_path: str, pack_id: str) -> bool:
    module_path, _, fn_name = register_path.rpartition(".")
    if not module_path or not fn_name.isidentifier():
        return False
    allowed_prefixes = (
        f"{pack_id}.",
        f"ecosystem.{pack_id}.",
    )
    return register_path.startswith(allowed_prefixes)


def _host_registration_allowed(
    pack_id: str,
    pack_location: PackLocation,
    manifest: Dict[str, Any],
) -> Tuple[bool, str]:
    if _is_trusted_host_registration_pack(pack_id, pack_location):
        return True, "trusted_builtin_pack"
    if manifest.get("host_execution") is not True:
        return False, "host_execution_not_requested"
    if os.environ.get("RUMI_ALLOW_HOST_EXECUTION") != "true":
        return False, "host_execution_not_allowed"
    return True, "host_execution_allowed"


def _is_trusted_host_registration_pack(pack_id: str, pack_location: PackLocation) -> bool:
    normalized_pack_id = str(pack_id or "").strip()
    try:
        pack_dir = pack_location.pack_dir.resolve()
    except OSError:
        pack_dir = pack_location.pack_dir
    if normalized_pack_id.startswith(CORE_PACK_ID_PREFIX):
        try:
            core_pack_root = Path(CORE_PACK_DIR).resolve()
        except OSError:
            core_pack_root = Path(CORE_PACK_DIR)
        try:
            core_relative = pack_dir.relative_to(core_pack_root)
        except ValueError:
            return False
        return bool(core_relative.parts) and core_relative.parts[0] == normalized_pack_id
    if normalized_pack_id not in TRUSTED_BUILTIN_PACK_IDS:
        return False
    try:
        ecosystem_root = Path(ECOSYSTEM_DIR).resolve()
    except OSError:
        ecosystem_root = Path(ECOSYSTEM_DIR)
    try:
        relative = pack_dir.relative_to(ecosystem_root)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] == normalized_pack_id


def _call_register_function(
    register_path: str,
    *,
    pack_location: PackLocation,
    interface_registry: InterfaceRegistry,
) -> List[str]:
    module_path, _, fn_name = register_path.rpartition(".")
    candidate_paths = [pack_location.pack_dir.parent]
    if register_path.startswith("ecosystem."):
        candidate_paths.append(pack_location.pack_dir.parent.parent)
    added_paths: List[str] = []
    for candidate_path in candidate_paths:
        added_path = str(candidate_path)
        if added_path not in sys.path:
            sys.path.insert(0, added_path)
            added_paths.append(added_path)
    try:
        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)
        if not callable(fn):
            raise TypeError(f"{register_path} is not callable")
        value = fn(interface_registry)
    finally:
        for added_path in added_paths:
            try:
                sys.path.remove(added_path)
            except ValueError:
                pass
    if isinstance(value, dict):
        registered = value.get("registered")
        if isinstance(registered, list):
            return [str(item) for item in registered]
    return []


def _diagnostic(level: str, code: str, message: str, **meta: Any) -> Dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        **meta,
    }
