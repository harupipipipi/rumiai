"""
Pack/Component/Addon のレジストリ

エコシステム内のすべてのPack、Component、Addonを
読み込み、解決、管理する中央レジストリ。

パス刷新: ecosystem/ 直下を走査（ecosystem/packs/ 互換あり）、ecosystem.json 直下優先

W19-F: VULN-M05 — JSON ファイルサイズ上限チェック追加
"""

import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from .uuid_utils import generate_pack_uuid, generate_component_uuid
from .json_patch import apply_patch, JsonPatchError
from .spec.schema.validator import (
    validate_ecosystem,
    validate_component_manifest,
    validate_addon,
    SchemaValidationError
)


# paths.py を参照（core_runtime パッケージとして import できない場合のフォールバック付き）
try:
    from core_runtime.paths import ECOSYSTEM_DIR as _ECOSYSTEM_DIR, find_ecosystem_json as _find_ecosystem_json_paths
except ImportError:
    from pathlib import Path as _FallbackPath
    _ECOSYSTEM_DIR = str(_FallbackPath(__file__).resolve().parent.parent.parent / "ecosystem")
    _find_ecosystem_json_paths = None

logger = logging.getLogger(__name__)

RUMI_MAX_JSON_FILE_BYTES: int = int(
    os.environ.get("RUMI_MAX_JSON_FILE_BYTES", 2097152)
)


def _check_json_file_size(filepath, max_bytes=None) -> bool:
    """Return *True* (= caller should skip) when *filepath* exceeds the limit."""
    if max_bytes is None:
        max_bytes = RUMI_MAX_JSON_FILE_BYTES
    try:
        file_size = os.path.getsize(filepath)
    except OSError as exc:
        logger.warning(
            "[Registry] Cannot stat JSON file, skipping: %s (%s)", filepath, exc
        )
        return True
    if file_size > max_bytes:
        logger.warning(
            "[Registry] JSON file size %d bytes exceeds limit %d bytes, skipping: %s",
            file_size,
            max_bytes,
            filepath,
        )
        return True
    return False

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
    permissions_required: Dict[str, Any] = field(default_factory=dict)
    
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
    subdir: Path = None  # ecosystem.jsonが見つかったサブディレクトリ
    components: Dict[str, ComponentInfo] = field(default_factory=dict)
    addons: List[Dict[str, Any]] = field(default_factory=list)
    routes: List[Dict[str, Any]] = field(default_factory=list)


class Registry:
    """
    エコシステムレジストリ
    
    Pack/Component/Addonの読み込み、解決、管理を行う。
    """
    
    def __init__(self, ecosystem_dir: str = _ECOSYSTEM_DIR):
        """
        Args:
            ecosystem_dir: エコシステムディレクトリのパス
        """
        self.ecosystem_dir = Path(ecosystem_dir)
        self.packs: Dict[str, PackInfo] = {}
        self._component_index: Dict[str, ComponentInfo] = {}  # uuid -> ComponentInfo
        self._type_index: Dict[str, List[ComponentInfo]] = {}  # type -> [ComponentInfo]
        self._patched_manifest_cache: Dict[str, Dict[str, Any]] = {}
        self._pack_routes: Dict[str, List[Dict[str, Any]]] = {}  # pack_id -> routes
    
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
        
        # ecosystem/* を走査（特殊ディレクトリは除外）
        _excluded = {".git", "__pycache__", "node_modules", ".venv", "packs", "flows"}
        
        candidates = []
        if self.ecosystem_dir.exists():
            candidates.extend(
                d for d in sorted(self.ecosystem_dir.iterdir())
                if d.is_dir() and d.name not in _excluded and not d.name.startswith(".")
            )
        
        # ecosystem/packs/* 互換ルートも走査
        legacy_root = self.ecosystem_dir / "packs"
        if legacy_root.is_dir():
            for d in sorted(legacy_root.iterdir()):
                if d.is_dir() and d.name not in _excluded and not d.name.startswith("."):
                    if d.name not in {c.name for c in candidates}:
                        candidates.append(d)
        
        for pack_dir in candidates:
            if pack_dir.is_dir():
                try:
                    pack_info = self._load_pack(pack_dir)
                    if pack_info:
                        if pack_info.pack_id in self.packs:
                            logger.warning(
                                "[Registry] Duplicate pack_id '%s' detected. "
                                "Keeping first loaded from '%s', ignoring '%s'.",
                                pack_info.pack_id,
                                self.packs[pack_info.pack_id].path,
                                pack_info.path,
                            )
                        else:
                            self.packs[pack_info.pack_id] = pack_info
                            print(f"  ✓ Pack読み込み成功: {pack_info.pack_id}")
                except Exception as e:
                    print(f"  ✗ Pack読み込みエラー ({pack_dir.name}): {e}")
        
        print(f"=== 読み込み完了: {len(self.packs)}個のPack ===\n")
        
        # load_order を自動解決してログ出力
        if self.packs:
            auto_order = resolve_load_order(self.packs)
            print(f"  Auto-resolved load_order: {auto_order}")

        # #20: connectivity requires 未充足チェック
        for _pack_info in self.packs.values():
            for _component in _pack_info.components.values():
                _conn = self.resolve_connectivity(_component)
                for _missing in _conn.get('missing_requires', []):
                    logger.warning(
                        "[Registry] Component '%s' has unsatisfied requirement: '%s'",
                        _component.full_id,
                        _missing,
                    )

        
        return self.packs
    
    def _find_ecosystem_json(self, pack_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
        """
        ecosystem.jsonを探す（直下優先）
        
        探索順序:
        1. pack_dir/ecosystem.json（直下優先）
        2. pack_dir/[任意サブディレクトリ]/ecosystem.json
        """
        # paths.py の共有実装を使う（利用可能な場合）
        if _find_ecosystem_json_paths is not None:
            return _find_ecosystem_json_paths(pack_dir)
        
        # フォールバック: 直下優先
        direct_file = pack_dir / "ecosystem.json"
        if direct_file.exists():
            return direct_file, pack_dir
        
        _excluded_sub = {"__pycache__", "node_modules", ".git", ".venv", "packs", "flows"}
        for subdir in sorted(pack_dir.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            if subdir.name in _excluded_sub:
                continue
            candidate = subdir / "ecosystem.json"
            if candidate.exists():
                return candidate, subdir
        
        return None, None
    
    def _load_pack(self, pack_dir: Path) -> Optional[PackInfo]:
        """
        単一のPackを読み込む
        
        Pack構造:
            pack_dir/[subdir]/ecosystem.json
            pack_dir/[subdir]/components/
            pack_dir/[subdir]/addons/
        
        [subdir] は任意の名前（backend, frontend, ui, src, lib など）。
        ecosystem.jsonを含む最初のサブディレクトリを使用する。
        直下に ecosystem.json がある場合はそれを優先する。
        
        Args:
            pack_dir: Packディレクトリのパス
        
        Returns:
            PackInfo または None
        """
        # ecosystem.jsonを探す
        ecosystem_file, pack_subdir = self._find_ecosystem_json(pack_dir)
        
        if ecosystem_file is None:
            print(f"    ecosystem.jsonが見つかりません: {pack_dir}")
            return None
        
        # ecosystem.jsonを読み込み
        if _check_json_file_size(ecosystem_file):
            return None
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
            path=pack_dir,
            subdir=pack_subdir
        )
        
        # Componentを読み込む
        components_dir = pack_subdir / "components"
        if components_dir.exists():
            self._load_components(pack_info, components_dir)
        
        # Addonを読み込む
        addons_dir = pack_subdir / "addons"
        if addons_dir.exists():
            self._load_addons(pack_info, addons_dir)
        
        # Routesを読み込む
        routes_file = pack_subdir / "routes.json"
        if routes_file.exists():
            self._load_routes(pack_info, routes_file)
        
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
                    if _check_json_file_size(manifest_file):
                        continue
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
                        pack_id=pack_info.pack_id,
                        permissions_required=manifest.get('permissions_required', {})
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
                if _check_json_file_size(addon_file):
                    continue
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
    

    def _load_routes(self, pack_info: PackInfo, routes_file: Path):
        """
        Packのルート定義を読み込む
        
        routes.json の形式:
        {
            "routes": [
                {"method": "POST", "path": "/api/packs/{pack_id}/execute", "flow_id": "example_flow", ...}
            ]
        }
        """
        try:
            if _check_json_file_size(routes_file):
                return
            with open(routes_file, 'r', encoding='utf-8') as f:
                routes_data = json.load(f)
            
            if not isinstance(routes_data, dict) or "routes" not in routes_data:
                print(f"      警告: routes.json の形式が不正です: {routes_file}")
                return
            
            raw_routes = routes_data.get("routes", [])
            if not isinstance(raw_routes, list):
                return
            
            valid_routes = []
            pack_prefix = f"/api/packs/{pack_info.pack_id}/"
            
            for route in raw_routes:
                if not isinstance(route, dict):
                    continue
                
                method = route.get("method", "").upper()
                path = route.get("path", "")
                flow_id = route.get("flow_id", "")
                
                if not method or not path or not flow_id:
                    print(f"      警告: ルート定義が不完全です: {route}")
                    continue
                
                if method not in ("GET", "POST", "PUT", "DELETE"):
                    print(f"      警告: 未サポートのHTTPメソッド: {method}")
                    continue
                
                # パスが /api/packs/{pack_id}/ で始まることを強制
                if not path.startswith(pack_prefix):
                    print(f"      警告: パスは {pack_prefix} で始まる必要があります: {path}")
                    continue
                
                valid_routes.append({
                    "method": method,
                    "path": path,
                    "flow_id": flow_id,
                    "pack_id": pack_info.pack_id,
                    "description": route.get("description", ""),
                    "timeout": min(max(route.get("timeout", 300), 1), 600),
                })
            
            pack_info.routes = valid_routes
            self._pack_routes[pack_info.pack_id] = valid_routes
            
            if valid_routes:
                print(f"      ✓ Routes: {len(valid_routes)}個のエンドポイント")
        
        except json.JSONDecodeError as e:
            print(f"      ✗ routes.json パースエラー ({routes_file}): {e}")
        except Exception as e:
            print(f"      ✗ routes.json 読み込みエラー ({routes_file}): {e}")
    
    def get_all_routes(self) -> Dict[str, List[Dict[str, Any]]]:
        """全Packのルート定義を取得"""
        return dict(self._pack_routes)
    
    def get_pack_routes(self, pack_id: str) -> List[Dict[str, Any]]:
        """特定Packのルート定義を取得"""
        return self._pack_routes.get(pack_id, [])

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
    
    def resolve_component_for_type(
        self,
        component_type: str,
        active_ecosystem_manager=None,
    ) -> Optional["ComponentInfo"]:
        """
        コンポーネントタイプに対して最適なコンポーネントを解決する。
        ActiveEcosystemManager の overrides/disabled を参照。
        """
        aem = active_ecosystem_manager
        if aem is None:
            try:
                from .active_ecosystem import get_active_ecosystem_manager
                aem = get_active_ecosystem_manager()
            except Exception:
                pass
        components = self.get_components_by_type(component_type)
        if not components:
            return None
        if aem:
            try:
                override_id = aem.get_override(component_type) if hasattr(aem, 'get_override') else None
            except Exception:
                override_id = None
            if override_id:
                for comp in components:
                    if comp.id == override_id:
                        if not (hasattr(aem, 'is_component_disabled') and aem.is_component_disabled(comp.full_id)):
                            return comp
                        break
        for comp in components:
            if aem and hasattr(aem, 'is_component_disabled') and aem.is_component_disabled(comp.full_id):
                continue
            return comp
        return None

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


        # ActiveEcosystem の disabled チェック
        _aem = None
        try:
            from .active_ecosystem import get_active_ecosystem_manager
            _aem = get_active_ecosystem_manager()
            if _aem.is_component_disabled(component.full_id):
                return manifest
        except Exception:
            pass
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

            # disabled_addons チェック
            if _aem:
                try:
                    _addon_full_id = f"{pack.pack_id}:{addon.get('addon_id', '')}"
                    if _aem.is_addon_disabled(_addon_full_id):
                        continue
                except Exception:
                    pass
            
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
        
        # 旧アドオンシステムは削除済み。素のマニフェストを使用する。
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
    def get_load_order(self, explicit_order: Optional[List[str]] = None) -> List[str]:
        """
        Pack のロード順序を取得する。

        Args:
            explicit_order: 手動指定のロード順序（ecosystem.jsonのload_order等）。
                            指定された場合はそれを優先。

        Returns:
            ロード順序のpack_idリスト
        """
        if explicit_order:
            # 手動指定を優先。存在しないpack_idは除外。
            valid = [pid for pid in explicit_order if pid in self.packs]
            # 手動リストに含まれないpackは末尾に追加
            remaining = [pid for pid in self.packs if pid not in set(valid)]
            return valid + remaining

        # 自動解決
        return resolve_load_order(self.packs)



# グローバルインスタンス（遅延初期化）
_global_registry: Optional[Registry] = None



def resolve_load_order(packs: Dict[str, "PackInfo"]) -> List[str]:
    """
    Pack間の依存関係からload_orderを自動解決する（Kahnのアルゴリズム）。

    依存関係ソース:
    - ecosystem.dependencies (リストまたは辞書)
    - ecosystem.connectivity.requires (pack-level)
    - 各componentの connectivity.requires → 該当typeを提供するpackを探索

    循環依存を検出した場合はエラーログを出して循環部分をスキップ。

    Args:
        packs: pack_id -> PackInfo のマップ

    Returns:
        トポロジカルソート済みのpack_idリスト
    """
    all_pack_ids = set(packs.keys())
    if not all_pack_ids:
        return []

    in_degree: Dict[str, int] = {pid: 0 for pid in all_pack_ids}
    dependents: Dict[str, List[str]] = {pid: [] for pid in all_pack_ids}

    # type -> pack_id のマップを構築（provides 解決用）
    type_to_packs: Dict[str, set] = {}
    for pack_id, pack_info in packs.items():
        for comp in pack_info.components.values():
            comp_provides = comp.manifest.get("connectivity", {}).get("provides", [])
            if isinstance(comp_provides, list):
                for ptype in comp_provides:
                    if ptype not in type_to_packs:
                        type_to_packs[ptype] = set()
                    type_to_packs[ptype].add(pack_id)

    for pack_id, pack_info in packs.items():
        eco = pack_info.ecosystem
        deps: set = set()

        # 1. ecosystem.dependencies
        raw_deps = eco.get("dependencies", [])
        if isinstance(raw_deps, list):
            deps.update(raw_deps)
        elif isinstance(raw_deps, dict):
            deps.update(raw_deps.keys())

        # 2. ecosystem.connectivity.requires
        eco_conn = eco.get("connectivity", {})
        if isinstance(eco_conn, dict):
            eco_requires = eco_conn.get("requires", [])
            if isinstance(eco_requires, list):
                deps.update(eco_requires)

        # 3. component connectivity.requires → type提供packを探す
        for comp in pack_info.components.values():
            comp_requires = comp.manifest.get("connectivity", {}).get("requires", [])
            if isinstance(comp_requires, list):
                for req_type in comp_requires:
                    provider_packs = type_to_packs.get(req_type, set())
                    for provider_id in provider_packs:
                        if provider_id != pack_id:
                            deps.add(provider_id)

        # エッジ追加（存在するpackのみ、自己参照除外）
        for dep_id in deps:
            if dep_id in all_pack_ids and dep_id != pack_id:
                dependents[dep_id].append(pack_id)
                in_degree[pack_id] += 1

    # Kahnのアルゴリズム
    queue = deque(pid for pid in sorted(all_pack_ids) if in_degree[pid] == 0)
    result: List[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in sorted(dependents[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 循環依存チェック
    if len(result) < len(all_pack_ids):
        cyclic = sorted(pid for pid in all_pack_ids if pid not in set(result))
        print(
            f"[Registry] ERROR: Circular dependency detected among packs: {cyclic}\n"
            f"[Registry] Loading cyclic packs in alphabetical order at end of load_order."
        )
        result.extend(cyclic)  # L2: append cyclic packs so they still get loaded

    return result


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
