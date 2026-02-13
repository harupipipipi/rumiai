# backend_core/ecosystem/addon_manager.py
"""
アドオン管理システム

アドオンの読み込み、検証、適用を行う。
"""

import json
import copy
import fnmatch
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from .json_patch import apply_patch, validate_patch, JsonPatchError, JsonPatchForbiddenError
from .spec.schema.validator import validate_addon, validate_json_patch_operations, SchemaValidationError
from .registry import ComponentInfo, PackInfo


@dataclass
class AddonInfo:
    """アドオン情報"""
    addon_id: str
    version: str
    priority: int
    enabled: bool
    data: Dict[str, Any]
    file_path: Path
    pack_id: str
    
    @property
    def full_id(self) -> str:
        return f"{self.pack_id}:{self.addon_id}"


@dataclass
class AddonApplicationResult:
    """アドオン適用結果"""
    success: bool
    addon_id: str
    target_component: str
    patches_applied: int = 0
    patches_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class AddonManager:
    """
    アドオン管理クラス
    
    アドオンの読み込み、検証、適用を管理する。
    """
    
    def __init__(self):
        """AddonManagerを初期化"""
        self.addons: Dict[str, AddonInfo] = {}
        self._applied_cache: Dict[str, Dict[str, Any]] = {}
    
    def load_addons_from_pack(self, pack: PackInfo) -> List[AddonInfo]:
        """
        Packからアドオンを読み込む
        
        Args:
            pack: PackInfo
        
        Returns:
            読み込まれたAddonInfoのリスト
        """
        loaded = []
        addons_dir = pack.path / "backend" / "addons"
        
        if not addons_dir.exists():
            return loaded
        
        for addon_file in addons_dir.glob("*.addon.json"):
            try:
                addon_info = self._load_addon_file(addon_file, pack.pack_id)
                if addon_info:
                    self.addons[addon_info.full_id] = addon_info
                    loaded.append(addon_info)
            except Exception as e:
                print(f"[AddonManager] アドオン読み込みエラー ({addon_file.name}): {e}")
        
        return loaded
    
    def _load_addon_file(self, file_path: Path, pack_id: str) -> Optional[AddonInfo]:
        """
        アドオンファイルを読み込む
        
        Args:
            file_path: アドオンファイルのパス
            pack_id: 親PackのID
        
        Returns:
            AddonInfo または None
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        errors = validate_addon(data, raise_on_error=False)
        if errors:
            print(f"[AddonManager] スキーマエラー ({file_path.name}): {errors[:3]}")
            return None
        
        return AddonInfo(
            addon_id=data['addon_id'],
            version=data['version'],
            priority=data.get('priority', 100),
            enabled=data.get('enabled', True),
            data=data,
            file_path=file_path,
            pack_id=pack_id
        )
    
    def get_addons_for_component(
        self,
        component: ComponentInfo,
        pack: PackInfo,
        active_ecosystem_manager=None,
    ) -> List[AddonInfo]:
        """
        コンポーネントに適用可能なアドオンを取得
        
        Args:
            component: 対象コンポーネント
            pack: コンポーネントが属するPack
        
        Returns:
            適用可能なAddonInfoのリスト（優先度順）
        """
        # ActiveEcosystemManager 取得
        _aem_gac = active_ecosystem_manager
        if _aem_gac is None:
            try:
                from .active_ecosystem import get_active_ecosystem_manager
                _aem_gac = get_active_ecosystem_manager()
            except Exception:
                pass

        # コンポーネントが disabled なら空を返す
        if _aem_gac and hasattr(_aem_gac, 'is_component_disabled'):
            if _aem_gac.is_component_disabled(component.full_id):
                return []

        applicable = []
        
        for addon in self.addons.values():
            if not addon.enabled:
                continue

            # ActiveEcosystem の disabled_addons チェック
            if _aem_gac and hasattr(_aem_gac, 'is_addon_disabled'):
                if _aem_gac.is_addon_disabled(addon.full_id):
                    continue
            
            for target in addon.data.get('targets', []):
                if self._target_matches(target, component, pack):
                    applicable.append(addon)
                    break
        
        applicable.sort(key=lambda a: a.priority)
        return applicable
    
    def _target_matches(
        self,
        target: Dict[str, Any],
        component: ComponentInfo,
        pack: PackInfo
    ) -> bool:
        """ターゲットがコンポーネントにマッチするか判定"""
        target_pack_identity = target.get('pack_identity')
        target_pack_uuid = target.get('pack_uuid')
        
        if target_pack_identity and target_pack_identity != pack.pack_identity:
            return False
        if target_pack_uuid and target_pack_uuid != pack.uuid:
            return False
        
        if not target_pack_identity and not target_pack_uuid:
            return False
        
        target_component = target.get('component', {})
        
        target_comp_uuid = target_component.get('component_uuid')
        if target_comp_uuid:
            return target_comp_uuid == component.uuid
        
        target_type = target_component.get('type')
        target_id = target_component.get('id')
        
        if target_type and target_type != component.type:
            return False
        if target_id and target_id != component.id:
            return False
        
        return bool(target_type or target_id)
    
    def apply_addons_to_manifest(
        self,
        component: ComponentInfo,
        pack: PackInfo,
        addons: List[AddonInfo] = None
    ) -> Tuple[Dict[str, Any], List[AddonApplicationResult]]:
        """
        コンポーネントのマニフェストにアドオンを適用
        
        Args:
            component: 対象コンポーネント
            pack: コンポーネントが属するPack
            addons: 適用するアドオン（省略時は自動取得）
        
        Returns:
            (パッチ適用後のマニフェスト, 適用結果のリスト)
        """
        if addons is None:
            addons = self.get_addons_for_component(component, pack)
        
        manifest = copy.deepcopy(component.manifest)
        results = []
        
        addon_policy = manifest.get('addon_policy', {})
        
        if addon_policy.get('deny_all', False):
            for addon in addons:
                results.append(AddonApplicationResult(
                    success=False,
                    addon_id=addon.full_id,
                    target_component=component.full_id,
                    errors=["コンポーネントはアドオンを拒否しています (deny_all=true)"]
                ))
            return manifest, results
        
        allowed_paths = addon_policy.get('allowed_manifest_paths', [])
        
        for addon in addons:
            result = self._apply_single_addon(
                manifest=manifest,
                addon=addon,
                component=component,
                pack=pack,
                allowed_paths=allowed_paths
            )
            results.append(result)
        
        return manifest, results
    
    def _apply_single_addon(
        self,
        manifest: Dict[str, Any],
        addon: AddonInfo,
        component: ComponentInfo,
        pack: PackInfo,
        allowed_paths: List[str]
    ) -> AddonApplicationResult:
        """
        単一のアドオンを適用
        
        Args:
            manifest: 適用先マニフェスト（変更される）
            addon: 適用するアドオン
            component: 対象コンポーネント
            pack: コンポーネントが属するPack
            allowed_paths: 許可されたパス
        
        Returns:
            適用結果
        """
        result = AddonApplicationResult(
            success=True,
            addon_id=addon.full_id,
            target_component=component.full_id
        )
        
        for target in addon.data.get('targets', []):
            if not self._target_matches(target, component, pack):
                continue
            
            for apply_op in target.get('apply', []):
                kind = apply_op.get('kind')
                
                if kind == 'manifest_json_patch':
                    self._apply_manifest_patch(
                        manifest=manifest,
                        patch_ops=apply_op.get('patch', []),
                        allowed_paths=allowed_paths,
                        result=result
                    )
                elif kind == 'file_json_patch':
                    result.warnings.append(
                        f"file_json_patch はこのメソッドでは適用されません: {apply_op.get('file')}"
                    )
        
        return result
    
    def _apply_manifest_patch(
        self,
        manifest: Dict[str, Any],
        patch_ops: List[Dict[str, Any]],
        allowed_paths: List[str],
        result: AddonApplicationResult
    ):
        """
        マニフェストにパッチを適用
        
        Args:
            manifest: 適用先マニフェスト（変更される）
            patch_ops: パッチ操作のリスト
            allowed_paths: 許可されたパス
            result: 適用結果（更新される）
        """
        for op in patch_ops:
            path = op.get('path', '')
            op_type = op.get('op')
            
            if op_type in ('move', 'copy'):
                result.errors.append(f"禁止された操作: {op_type}")
                result.patches_skipped += 1
                continue
            
            if allowed_paths:
                path_allowed = any(path.startswith(ap) for ap in allowed_paths)
                if not path_allowed:
                    result.warnings.append(f"パス '{path}' は許可されていません")
                    result.patches_skipped += 1
                    continue
            
            try:
                apply_patch(manifest, [op], in_place=True)
                result.patches_applied += 1
            except JsonPatchError as e:
                result.errors.append(f"パッチ適用エラー ({path}): {e}")
                result.patches_skipped += 1
    
    def apply_file_patches(
        self,
        component: ComponentInfo,
        pack: PackInfo,
        addons: List[AddonInfo] = None
    ) -> List[Tuple[str, Dict[str, Any], AddonApplicationResult]]:
        """
        ファイルパッチを適用
        
        Args:
            component: 対象コンポーネント
            pack: コンポーネントが属するPack
            addons: 適用するアドオン（省略時は自動取得）
        
        Returns:
            [(ファイルパス, パッチ適用後の内容, 結果), ...]
        """
        if addons is None:
            addons = self.get_addons_for_component(component, pack)
        
        addon_policy = component.manifest.get('addon_policy', {})
        if addon_policy.get('deny_all', False):
            return []
        
        editable_files = addon_policy.get('editable_files', [])
        
        file_patches: Dict[str, Tuple[Dict[str, Any], List[Tuple[str, Dict]]]] = {}
        results = []
        
        for addon in addons:
            for target in addon.data.get('targets', []):
                if not self._target_matches(target, component, pack):
                    continue
                
                for apply_op in target.get('apply', []):
                    if apply_op.get('kind') != 'file_json_patch':
                        continue
                    
                    file_path = apply_op.get('file')
                    patch_ops = apply_op.get('patch', [])
                    create_if_missing = apply_op.get('create_if_missing', False)
                    
                    if not file_path:
                        continue
                    
                    allowed_prefixes = self._get_allowed_prefixes_for_file(
                        file_path, editable_files
                    )
                    
                    if allowed_prefixes is None:
                        results.append((
                            file_path,
                            None,
                            AddonApplicationResult(
                                success=False,
                                addon_id=addon.full_id,
                                target_component=component.full_id,
                                errors=[f"ファイル '{file_path}' は編集可能リストにありません"]
                            )
                        ))
                        continue
                    
                    full_path = component.path / file_path
                    
                    if file_path not in file_patches:
                        if full_path.exists():
                            with open(full_path, 'r', encoding='utf-8') as f:
                                content = json.load(f)
                        elif create_if_missing:
                            content = {}
                        else:
                            results.append((
                                file_path,
                                None,
                                AddonApplicationResult(
                                    success=False,
                                    addon_id=addon.full_id,
                                    target_component=component.full_id,
                                    errors=[f"ファイル '{file_path}' が存在しません"]
                                )
                            ))
                            continue
                        
                        file_patches[file_path] = (content, [])
                    
                    content, patches = file_patches[file_path]
                    
                    for op in patch_ops:
                        path = op.get('path', '')
                        
                        if allowed_prefixes:
                            path_allowed = any(path.startswith(ap) for ap in allowed_prefixes)
                            if not path_allowed:
                                continue
                        
                        patches.append((addon.full_id, op))
        
        for file_path, (content, patches) in file_patches.items():
            result = AddonApplicationResult(
                success=True,
                addon_id="multiple",
                target_component=component.full_id
            )
            
            patched_content = copy.deepcopy(content)
            
            for addon_id, op in patches:
                try:
                    apply_patch(patched_content, [op], in_place=True)
                    result.patches_applied += 1
                except JsonPatchError as e:
                    result.errors.append(f"[{addon_id}] パッチエラー: {e}")
                    result.patches_skipped += 1
            
            if result.errors:
                result.success = False
            
            results.append((file_path, patched_content, result))
        
        return results
    
    def _get_allowed_prefixes_for_file(
        self,
        file_path: str,
        editable_files: List[Dict[str, Any]]
    ) -> Optional[List[str]]:
        """
        ファイルに対して許可されたJSON Pointerプレフィックスを取得
        
        Args:
            file_path: ファイルパス
            editable_files: editable_files設定
        
        Returns:
            許可されたプレフィックスのリスト、またはNone（ファイルが許可されていない場合）
        """
        for rule in editable_files:
            pattern = rule.get('path_glob', '')
            if fnmatch.fnmatch(file_path, pattern):
                return rule.get('allowed_json_pointer_prefixes', [])
        
        return None
    
    def get_addon(self, full_id: str) -> Optional[AddonInfo]:
        """アドオンを取得"""
        return self.addons.get(full_id)
    
    def get_all_addons(self) -> List[AddonInfo]:
        """すべてのアドオンを取得"""
        return list(self.addons.values())
    
    def enable_addon(self, full_id: str) -> bool:
        """アドオンを有効化"""
        addon = self.addons.get(full_id)
        if addon:
            addon.enabled = True
            return True
        return False
    
    def disable_addon(self, full_id: str) -> bool:
        """アドオンを無効化"""
        addon = self.addons.get(full_id)
        if addon:
            addon.enabled = False
            return True
        return False
    
    def clear_cache(self):
        """適用キャッシュをクリア"""
        self._applied_cache.clear()
    
    def validate_addon_data(self, data: Dict[str, Any]) -> List[str]:
        """
        アドオンデータを検証
        
        Args:
            data: アドオンデータ
        
        Returns:
            エラーメッセージのリスト
        """
        errors = validate_addon(data, raise_on_error=False)
        
        for i, target in enumerate(data.get('targets', [])):
            for j, apply_op in enumerate(target.get('apply', [])):
                patch = apply_op.get('patch', [])
                patch_errors = validate_patch(patch)
                for err in patch_errors:
                    errors.append(f"targets[{i}].apply[{j}].patch: {err}")
        
        return errors


_global_addon_manager: Optional[AddonManager] = None
_addon_lock = threading.Lock()


def get_addon_manager() -> AddonManager:
    """グローバルなAddonManagerを取得"""
    global _global_addon_manager
    if _global_addon_manager is None:
        with _addon_lock:
            if _global_addon_manager is None:
                _global_addon_manager = AddonManager()
    return _global_addon_manager


def reload_addon_manager() -> AddonManager:
    """AddonManagerを再作成"""
    global _global_addon_manager
    with _addon_lock:
        _global_addon_manager = AddonManager()
    return _global_addon_manager
