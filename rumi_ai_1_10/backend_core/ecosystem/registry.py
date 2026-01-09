# backend_core/ecosystem/registry.py
"""
Pack/Component/Addon のレジストリ

エコシステム内のすべてのPack、Component、Addonを
読み込み、解決、管理する中央レジストリ。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from .uuid_utils import generate_pack_uuid, generate_component_uuid, generate_addon_uuid
from .json_patch import apply_patch, JsonPatchError
from .spec.schema.validator import (
    validate_ecosystem,
    validate_component_manifest,
    validate_addon,
    SchemaValidationError
)


@dataclass
class ComponentInfo:
    """コンポーネント情報"""
    type: str
    id: str
    version: str
    uuid: str
    manifest: Dict[str, Any]
    path: Path
    pack_id: str
    
    @property
    def full_id(self) -> str:
        return f"{self.pack_id}:{self.type}:{self.id}"


@dataclass
class PackInfo:
    """Pack情報"""
    pack_id: str
    pack_identity: str
    version: str
    uuid: str
    ecosystem: Dict[str, Any]
    path: Path
    components: Dict[str, ComponentInfo] = field(default_factory=dict)
    addons: List[Dict[str, Any]] = field(default_factory=list)


class Registry:
    """
    エコシステムレジストリ
    
    Pack/Component/Addonの読み込み、解決、管理を行う。
    """
    
    def __init__(self, ecosystem_dir: str = "ecosystem"):
        """
        Args:
            ecosystem_dir: エコシステムディレクトリのパス
        """
        self.ecosystem_dir = Path(ecosystem_dir)
        self.packs: Dict[str, PackInfo] = {}
        self._component_index: Dict[str, ComponentInfo] = {}  # uuid -> ComponentInfo
        self._type_index: Dict[str, List[ComponentInfo]] = {}  # type -> [ComponentInfo]
        self._patched_manifest_cache: Dict[str, Dict[str, Any]] = {}
    
    def load_all_packs(self) -> Dict[str, PackInfo]:
        """
        すべてのPackを読み込む
        
        Returns:
            読み込まれたPackの辞書
        """
        if not self.ecosystem_dir.exists():
            print(f"[Registry] エコシステムディレクトリが存在しません: {self.ecosystem_dir}")
            return {}
        
        print(f"\n=== Registry: Packの読み込みを開始 ===")
        
        for pack_dir in self.ecosystem_dir.iterdir():
            if pack_dir.is_dir() and not pack_dir.name.startswith('.'):
                try:
                    pack_info = self._load_pack(pack_dir)
                    if pack_info:
                        self.packs[pack_info.pack_id] = pack_info
                        print(f"  ✓ Pack読み込み成功: {pack_info.pack_id}")
                except Exception as e:
                    print(f"  ✗ Pack読み込みエラー ({pack_dir.name}): {e}")
        
        # アドオンをAddonManagerに読み込む
        try:
            from .addon_manager import get_addon_manager
            addon_manager = get_addon_manager()
            
            for pack in self.packs.values():
                addon_manager.load_addons_from_pack(pack)
        except ImportError:
            # Phase 5以前ではAddonManagerが存在しない可能性がある
            pass
        
        print(f"=== 読み込み完了: {len(self.packs)}個のPack ===\n")
        return self.packs
    
    def _load_pack(self, pack_dir: Path) -> Optional[PackInfo]:
        """
        単一のPackを読み込む
        
        Args:
            pack_dir: Packディレクトリのパス
        
        Returns:
            PackInfo または None
        """
        # ecosystem.jsonを探す
        ecosystem_file = pack_dir / "backend" / "ecosystem.json"
        
        if not ecosystem_file.exists():
            print(f"    ecosystem.jsonが見つかりません: {ecosystem_file}")
            return None
        
        # ecosystem.jsonを読み込み
        with open(ecosystem_file, 'r', encoding='utf-8') as f:
            ecosystem_data = json.load(f)
        
        # スキーマ検証
        try:
            validate_ecosystem(ecosystem_data)
        except SchemaValidationError as e:
            print(f"    スキーマ検証エラー: {e}")
            return None
        
        # UUIDを生成（または既存の値を使用）
        pack_identity = ecosystem_data['pack_identity']
        pack_uuid = ecosystem_data.get('pack_uuid') or str(generate_pack_uuid(pack_identity))
        
        pack_info = PackInfo(
            pack_id=ecosystem_data['pack_id'],
            pack_identity=pack_identity,
            version=ecosystem_data['version'],
            uuid=pack_uuid,
            ecosystem=ecosystem_data,
            path=pack_dir
        )
        
        # Componentを読み込む
        components_dir = pack_dir / "backend" / "components"
        if components_dir.exists():
            self._load_components(pack_info, components_dir)
        
        # Addonを読み込む
        addons_dir = pack_dir / "backend" / "addons"
        if addons_dir.exists():
            self._load_addons(pack_info, addons_dir)
        
        return pack_info
    
    def _load_components(self, pack_info: PackInfo, components_dir: Path):
        """
        Packのすべてのコンポーネントを読み込む
        """
        vocabulary_types = pack_info.ecosystem.get('vocabulary', {}).get('types', [])
        
        for component_dir in components_dir.iterdir():
            if component_dir.is_dir() and not component_dir.name.startswith('.'):
                manifest_file = component_dir / "manifest.json"
                
                if not manifest_file.exists():
                    print(f"      manifest.jsonが見つかりません: {component_dir}")
                    continue
                
                try:
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    
                    # スキーマ検証（vocabularyチェックなし - 後で行う）
                    validate_component_manifest(manifest)
                    
                    # vocabularyチェック
                    component_type = manifest['type']
                    if vocabulary_types and component_type not in vocabulary_types:
                        print(f"      警告: タイプ '{component_type}' はvocabularyに定義されていません")
                    
                    # UUIDを生成
                    component_uuid = manifest.get('component_uuid') or str(
                        generate_component_uuid(
                            pack_info.uuid,
                            manifest['type'],
                            manifest['id']
                        )
                    )
                    
                    component_info = ComponentInfo(
                        type=manifest['type'],
                        id=manifest['id'],
                        version=manifest['version'],
                        uuid=component_uuid,
                        manifest=manifest,
                        path=component_dir,
                        pack_id=pack_info.pack_id
                    )
                    
                    # インデックスに追加
                    key = f"{manifest['type']}:{manifest['id']}"
                    pack_info.components[key] = component_info
                    self._component_index[component_uuid] = component_info
                    
                    if component_type not in self._type_index:
                        self._type_index[component_type] = []
                    self._type_index[component_type].append(component_info)
                    
                    print(f"      ✓ Component: {manifest['type']}:{manifest['id']}")
                    
                except SchemaValidationError as e:
                    print(f"      ✗ Component検証エラー ({component_dir.name}): {e}")
                except Exception as e:
                    print(f"      ✗ Component読み込みエラー ({component_dir.name}): {e}")
    
    def _load_addons(self, pack_info: PackInfo, addons_dir: Path):
        """
        Packのすべてのアドオンを読み込む
        """
        for addon_file in addons_dir.glob("*.addon.json"):
            try:
                with open(addon_file, 'r', encoding='utf-8') as f:
                    addon_data = json.load(f)
                
                # スキーマ検証
                validate_addon(addon_data)
                
                pack_info.addons.append(addon_data)
                print(f"      ✓ Addon: {addon_data['addon_id']}")
                
            except SchemaValidationError as e:
                print(f"      ✗ Addon検証エラー ({addon_file.name}): {e}")
            except Exception as e:
                print(f"      ✗ Addon読み込みエラー ({addon_file.name}): {e}")
    
    def get_pack(self, pack_id: str) -> Optional[PackInfo]:
        """Pack IDでPackを取得"""
        return self.packs.get(pack_id)
    
    def get_pack_by_identity(self, pack_identity: str) -> Optional[PackInfo]:
        """Pack IdentityでPackを取得"""
        for pack in self.packs.values():
            if pack.pack_identity == pack_identity:
                return pack
        return None
    
    def get_pack_by_uuid(self, pack_uuid: str) -> Optional[PackInfo]:
        """Pack UUIDでPackを取得"""
        for pack in self.packs.values():
            if pack.uuid == pack_uuid:
                return pack
        return None
    
    def get_component(
        self,
        pack_id: str,
        component_type: str,
        component_id: str
    ) -> Optional[ComponentInfo]:
        """
        コンポーネントを取得
        
        Args:
            pack_id: Pack ID
            component_type: コンポーネントタイプ
            component_id: コンポーネントID
        
        Returns:
            ComponentInfo または None
        """
        pack = self.packs.get(pack_id)
        if not pack:
            return None
        
        key = f"{component_type}:{component_id}"
        return pack.components.get(key)
    
    def get_component_by_uuid(self, component_uuid: str) -> Optional[ComponentInfo]:
        """コンポーネントUUIDでコンポーネントを取得"""
        return self._component_index.get(component_uuid)
    
    def get_components_by_type(self, component_type: str) -> List[ComponentInfo]:
        """タイプでコンポーネントを取得"""
        return self._type_index.get(component_type, [])
    
    def resolve_connectivity(
        self,
        component: ComponentInfo
    ) -> Dict[str, List[ComponentInfo]]:
        """
        コンポーネントの接続性を解決
        
        Args:
            component: 対象コンポーネント
        
        Returns:
            {
                'accepts': [受け入れ可能なコンポーネント],
                'provides': [提供するインターフェース名],
                'requires': [必須の依存コンポーネント],
                'missing_requires': [見つからない必須依存]
            }
        """
        connectivity = component.manifest.get('connectivity', {})
        
        result = {
            'accepts': [],
            'provides': connectivity.get('provides', []),
            'requires': [],
            'missing_requires': []
        }
        
        # acceptsを解決
        for type_name in connectivity.get('accepts', []):
            components = self.get_components_by_type(type_name)
            result['accepts'].extend(components)
        
        # requiresを解決
        for type_name in connectivity.get('requires', []):
            components = self.get_components_by_type(type_name)
            if components:
                result['requires'].extend(components)
            else:
                result['missing_requires'].append(type_name)
        
        return result
    
    def apply_addons(self, component: ComponentInfo) -> Dict[str, Any]:
        """
        コンポーネントにアドオンを適用
        
        Args:
            component: 対象コンポーネント
        
        Returns:
            アドオン適用後のマニフェスト
        """
        manifest = dict(component.manifest)
        pack = self.packs.get(component.pack_id)
        
        if not pack:
            return manifest
        
        # 優先度でソート
        sorted_addons = sorted(
            pack.addons,
            key=lambda a: a.get('priority', 100)
        )
        
        for addon in sorted_addons:
            if not addon.get('enabled', True):
                continue
            
            for target in addon.get('targets', []):
                if self._matches_target(component, pack, target):
                    manifest = self._apply_addon_target(manifest, target, component)
        
        return manifest
    
    def _matches_target(
        self,
        component: ComponentInfo,
        pack: PackInfo,
        target: Dict[str, Any]
    ) -> bool:
        """アドオンのターゲットがコンポーネントにマッチするか"""
        # Pack マッチング
        target_pack_identity = target.get('pack_identity')
        target_pack_uuid = target.get('pack_uuid')
        
        if target_pack_identity and target_pack_identity != pack.pack_identity:
            return False
        if target_pack_uuid and target_pack_uuid != pack.uuid:
            return False
        
        # Component マッチング
        target_component = target.get('component', {})
        
        target_comp_uuid = target_component.get('component_uuid')
        if target_comp_uuid and target_comp_uuid != component.uuid:
            return False
        
        target_type = target_component.get('type')
        if target_type and target_type != component.type:
            return False
        
        target_id = target_component.get('id')
        if target_id and target_id != component.id:
            return False
        
        return True
    
    def _apply_addon_target(
        self,
        manifest: Dict[str, Any],
        target: Dict[str, Any],
        component: ComponentInfo
    ) -> Dict[str, Any]:
        """アドオンのターゲットをマニフェストに適用"""
        addon_policy = component.manifest.get('addon_policy', {})
        
        if addon_policy.get('deny_all', False):
            return manifest
        
        allowed_paths = addon_policy.get('allowed_manifest_paths', [])
        
        for apply_op in target.get('apply', []):
            kind = apply_op.get('kind')
            
            if kind == 'manifest_json_patch':
                patch = apply_op.get('patch', [])
                
                # パス制限チェック
                if allowed_paths:
                    filtered_patch = []
                    for op in patch:
                        path = op.get('path', '')
                        if any(path.startswith(ap) for ap in allowed_paths):
                            filtered_patch.append(op)
                    patch = filtered_patch
                
                if patch:
                    try:
                        manifest = apply_patch(manifest, patch)
                    except JsonPatchError as e:
                        print(f"      警告: パッチ適用エラー: {e}")
        
        return manifest
    
    def get_patched_manifest(
        self,
        component: ComponentInfo,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        アドオン適用済みのマニフェストを取得
        
        Args:
            component: 対象コンポーネント
            use_cache: キャッシュを使用するか
        
        Returns:
            アドオン適用後のマニフェスト
        """
        cache_key = component.uuid
        
        if use_cache and cache_key in self._patched_manifest_cache:
            return self._patched_manifest_cache[cache_key]
        
        pack = self.packs.get(component.pack_id)
        if not pack:
            return component.manifest
        
        try:
            from .addon_manager import get_addon_manager
            addon_manager = get_addon_manager()
            patched, results = addon_manager.apply_addons_to_manifest(component, pack)
        except ImportError:
            # AddonManagerが存在しない場合は元のマニフェストを返す
            patched = component.manifest
        
        if use_cache:
            self._patched_manifest_cache[cache_key] = patched
        
        return patched
    
    def clear_patched_manifest_cache(self):
        """パッチ適用済みマニフェストのキャッシュをクリア"""
        self._patched_manifest_cache.clear()
    
    def get_all_components(self) -> List[ComponentInfo]:
        """すべてのコンポーネントを取得"""
        return list(self._component_index.values())
    
    def get_vocabulary(self, pack_id: str) -> List[str]:
        """Packのvocabulary typesを取得"""
        pack = self.packs.get(pack_id)
        if pack:
            return pack.ecosystem.get('vocabulary', {}).get('types', [])
        return []


# グローバルインスタンス（遅延初期化）
_global_registry: Optional[Registry] = None


def get_registry() -> Registry:
    """グローバルレジストリを取得"""
    global _global_registry
    if _global_registry is None:
        _global_registry = Registry()
        _global_registry.load_all_packs()
    return _global_registry


def reload_registry() -> Registry:
    """レジストリを再読み込み"""
    global _global_registry
    _global_registry = Registry()
    _global_registry.load_all_packs()
    return _global_registry
