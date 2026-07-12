"""
Addon manager for ecosystem components.
"""

from __future__ import annotations

import copy
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .json_patch import JsonPatchError, apply_patch, validate_patch

if TYPE_CHECKING:
    from .registry import ComponentInfo, PackInfo


@dataclass
class AddonInfo:
    key: str
    pack_id: str
    addon_id: str
    version: str
    priority: int = 100
    enabled: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    path: Optional[Path] = None


@dataclass
class AddonApplicationResult:
    addon_key: str
    success: bool
    errors: List[str] = field(default_factory=list)


class AddonManager:
    def __init__(self) -> None:
        self.addons: Dict[str, AddonInfo] = {}
        self._applied_cache: Dict[str, Any] = {}
        self._loaded_from_registry_id: Optional[int] = None

    def _ensure_loaded(self) -> None:
        from .registry import get_registry

        registry = get_registry()
        registry_id = id(registry)
        if self._loaded_from_registry_id == registry_id and self.addons:
            return
        self.load_from_registry(registry)

    def load_from_registry(self, registry=None) -> None:
        if registry is None:
            from .registry import get_registry

            registry = get_registry()
        self.addons = {}
        for pack in registry.packs.values():
            addons_dir = Path(pack.subdir or pack.path) / "addons"
            for data in pack.addons:
                addon_id = data.get("addon_id")
                if not addon_id:
                    continue
                key = f"{pack.pack_id}:{addon_id}"
                addon_path = next(iter(sorted(addons_dir.glob(f"*{addon_id}*.addon.json"))), None) if addons_dir.is_dir() else None
                self.addons[key] = AddonInfo(
                    key=key,
                    pack_id=pack.pack_id,
                    addon_id=addon_id,
                    version=data.get("version", "1.0.0"),
                    priority=int(data.get("priority", 100)),
                    enabled=bool(data.get("enabled", True)),
                    data=data,
                    path=addon_path,
                )
        self._loaded_from_registry_id = id(registry)
        self.clear_cache()

    def get_addon(self, addon_key: str) -> Optional[AddonInfo]:
        self._ensure_loaded()
        return self.addons.get(addon_key)

    def get_all_addons(self) -> List[AddonInfo]:
        self._ensure_loaded()
        return sorted(self.addons.values(), key=lambda addon: (addon.pack_id, addon.priority, addon.addon_id))

    def get_addons_for_component(self, component: ComponentInfo, pack: PackInfo) -> List[AddonInfo]:
        self._ensure_loaded()
        matched: List[AddonInfo] = []
        for addon in self.addons.values():
            if addon.pack_id != pack.pack_id or not addon.enabled:
                continue
            for target in addon.data.get("targets", []):
                if not self._target_matches(target, component, pack):
                    continue
                matched.append(addon)
                break
        return sorted(matched, key=lambda addon: (addon.priority, addon.addon_id))

    def validate_addon_data(self, data: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not data.get("addon_id"):
            errors.append("addon_id is required")
        if not data.get("version"):
            errors.append("version is required")
        targets = data.get("targets")
        if not isinstance(targets, list) or not targets:
            errors.append("targets must be a non-empty list")
            return errors
        for idx, target in enumerate(targets):
            apply_items = target.get("apply")
            if not isinstance(apply_items, list) or not apply_items:
                errors.append(f"targets[{idx}].apply must be a non-empty list")
                continue
            for apply_idx, apply_item in enumerate(apply_items):
                kind = apply_item.get("kind")
                if kind not in {"manifest_json_patch", "file_json_patch"}:
                    errors.append(f"targets[{idx}].apply[{apply_idx}] has unsupported kind")
                    continue
                patch_errors = validate_patch(apply_item.get("patch", []))
                errors.extend(patch_errors)
        return errors

    def apply_addons_to_manifest(
        self,
        component: ComponentInfo,
        pack: PackInfo,
    ) -> Tuple[Dict[str, Any], List[AddonApplicationResult]]:
        manifest = copy.deepcopy(component.manifest)
        results: List[AddonApplicationResult] = []
        policy = component.manifest.get("addon_policy", {}) or {}
        addons = self.get_addons_for_component(component, pack)
        if policy.get("deny_all"):
            for addon in addons:
                results.append(
                    AddonApplicationResult(
                        addon_key=addon.key,
                        success=False,
                        errors=["deny_all policy blocks addon application"],
                    )
                )
            return manifest, results

        allowed_paths = list(policy.get("allowed_manifest_paths") or [])
        for addon in addons:
            errors: List[str] = []
            for target in addon.data.get("targets", []):
                if not self._target_matches(target, component, pack):
                    continue
                for apply_item in target.get("apply", []):
                    if apply_item.get("kind") != "manifest_json_patch":
                        continue
                    allowed_patch: List[Dict[str, Any]] = []
                    for op in apply_item.get("patch", []):
                        path = op.get("path", "")
                        if self._path_allowed(path, allowed_paths):
                            allowed_patch.append(op)
                        else:
                            errors.append(f"Manifest path not allowed: {path}")
                    if allowed_patch:
                        try:
                            manifest = apply_patch(manifest, allowed_patch)
                        except JsonPatchError as exc:
                            errors.append(str(exc))
            results.append(AddonApplicationResult(addon_key=addon.key, success=not errors, errors=errors))
        return manifest, results

    def apply_file_patches(
        self,
        component: ComponentInfo,
        pack: PackInfo,
    ) -> List[Tuple[Path, Dict[str, Any], AddonApplicationResult]]:
        self._ensure_loaded()
        results: List[Tuple[Path, Dict[str, Any], AddonApplicationResult]] = []
        editable_files = component.manifest.get("addon_policy", {}).get("editable_files", []) or []
        for addon in self.get_addons_for_component(component, pack):
            for target in addon.data.get("targets", []):
                if not self._target_matches(target, component, pack):
                    continue
                for apply_item in target.get("apply", []):
                    if apply_item.get("kind") != "file_json_patch":
                        continue
                    file_rel = apply_item.get("file", "")
                    file_path = Path(component.path) / file_rel
                    if not file_path.is_file():
                        results.append((file_path, {}, AddonApplicationResult(addon.key, False, ["Target file not found"])))
                        continue
                    matched_rule = self._match_editable_rule(file_rel, editable_files)
                    if matched_rule is None:
                        results.append((file_path, {}, AddonApplicationResult(addon.key, False, ["File is not editable by policy"])))
                        continue
                    content = json.loads(file_path.read_text(encoding="utf-8"))
                    errors: List[str] = []
                    allowed_prefixes = matched_rule.get("allowed_json_pointer_prefixes", []) or []
                    allowed_patch: List[Dict[str, Any]] = []
                    for op in apply_item.get("patch", []):
                        path = op.get("path", "")
                        if self._path_allowed(path, allowed_prefixes):
                            allowed_patch.append(op)
                        else:
                            errors.append(f"File path not allowed: {path}")
                    patched = copy.deepcopy(content)
                    if allowed_patch:
                        try:
                            patched = apply_patch(content, allowed_patch)
                        except JsonPatchError as exc:
                            errors.append(str(exc))
                    results.append((file_path, patched, AddonApplicationResult(addon.key, not errors, errors)))
        return results

    def enable_addon(self, addon_key: str) -> None:
        addon = self.get_addon(addon_key)
        if addon:
            addon.enabled = True
            self.clear_cache()

    def disable_addon(self, addon_key: str) -> None:
        addon = self.get_addon(addon_key)
        if addon:
            addon.enabled = False
            self.clear_cache()

    def clear_cache(self) -> None:
        self._applied_cache.clear()

    @staticmethod
    def _target_matches(target: Dict[str, Any], component: ComponentInfo, pack: PackInfo) -> bool:
        pack_identity = target.get("pack_identity")
        if pack_identity and pack_identity != pack.pack_identity:
            return False
        target_component = target.get("component", {}) or {}
        target_type = target_component.get("type")
        target_id = target_component.get("id")
        if target_type and target_type != component.type:
            return False
        if target_id and target_id != component.id:
            return False
        return True

    @staticmethod
    def _path_allowed(path: str, allowed_prefixes: List[str]) -> bool:
        if not allowed_prefixes:
            return False
        return any(path == prefix or path.startswith(prefix + "/") for prefix in allowed_prefixes)

    @staticmethod
    def _match_editable_rule(file_rel: str, editable_files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for rule in editable_files:
            glob_pattern = rule.get("path_glob")
            if glob_pattern and fnmatch.fnmatch(file_rel, glob_pattern):
                return rule
        return None


_global_addon_manager: Optional[AddonManager] = None


def get_addon_manager() -> AddonManager:
    global _global_addon_manager
    if _global_addon_manager is None:
        _global_addon_manager = AddonManager()
    _global_addon_manager._ensure_loaded()
    return _global_addon_manager


def reload_addon_manager() -> AddonManager:
    global _global_addon_manager
    _global_addon_manager = AddonManager()
    _global_addon_manager._ensure_loaded()
    return _global_addon_manager
