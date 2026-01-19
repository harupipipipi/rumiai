# backend_core/ecosystem/initializer.py
"""
エコシステム初期化

アプリケーション起動時にエコシステムを初期化する。
マウント、レジストリ、アクティブエコシステムの初期化を行う。
"""

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from .mounts import MountManager, get_mount_manager, get_mount_path, DEFAULT_MOUNTS
from .registry import Registry, get_registry, reload_registry
from .active_ecosystem import (
    ActiveEcosystemManager,
    get_active_ecosystem_manager,
    DEFAULT_CONFIG
)


class EcosystemInitializer:
    """
    エコシステム初期化クラス
    
    アプリケーション起動時に一度だけ呼び出す。
    """
    
    # seed時に除外するディレクトリ
    SEED_EXCLUDE_DIRS = {'__pycache__', 'userdata', '.git', '.venv', 'node_modules'}
    
    def __init__(
        self,
        user_data_dir: str = "user_data",
        ecosystem_dir: str = "ecosystem"
    ):
        """
        Args:
            user_data_dir: ユーザーデータディレクトリ
            ecosystem_dir: エコシステムディレクトリ
        """
        self.user_data_dir = Path(user_data_dir)
        self.ecosystem_dir = Path(ecosystem_dir)
        
        self.mount_manager: Optional[MountManager] = None
        self.registry: Optional[Registry] = None
        self.active_ecosystem: Optional[ActiveEcosystemManager] = None
    
    def initialize(self) -> Dict[str, Any]:
        """
        エコシステムを初期化
        
        Returns:
            初期化結果の辞書
        """
        result = {
            "success": True,
            "mounts_initialized": False,
            "directories_created": [],
            "registry_loaded": False,
            "packs_loaded": 0,
            "components_loaded": 0,
            "active_ecosystem_loaded": False,
            "seeded": [],
            "chats_migrated": False,
            "errors": []
        }
        
        try:
            # 1. ディレクトリ構造の作成
            self._create_directories(result)
            
            # 2. マウント設定の初期化
            self._initialize_mounts(result)
            
            # 3. レジストリの初期化
            self._initialize_registry(result)
            
            # 4. アクティブエコシステムの初期化
            self._initialize_active_ecosystem(result)
            
            # 5. assetsのseed展開（Pack assetsからコピー）
            self._seed_assets(result)
            
            # 6. chatsの移行
            self._migrate_chats(result)
            
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"初期化エラー: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return result
    
    def _create_directories(self, result: Dict[str, Any]):
        """必要なディレクトリを作成"""
        directories = [
            self.user_data_dir,
            self.user_data_dir / "chats",
            self.user_data_dir / "settings",
            self.user_data_dir / "cache",
            self.user_data_dir / "shared",
            self.ecosystem_dir,
        ]
        
        for dir_path in directories:
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                result["directories_created"].append(str(dir_path))
    
    def _initialize_mounts(self, result: Dict[str, Any]):
        """マウント設定を初期化"""
        mounts_file = self.user_data_dir / "mounts.json"
        
        # MountManagerを取得（グローバルインスタンスを使用）
        self.mount_manager = get_mount_manager()
        
        # mounts.jsonが存在しない場合は作成
        if not mounts_file.exists():
            mounts_data = {
                "version": "1.0",
                "mounts": {
                    # 公式は汎用マウントのみ定義
                    # 具体的なマウントはコンポーネントが自己登録する
                    "data.user": "./user_data",
                    "data.cache": "./user_data/cache",
                }
            }
            
            with open(mounts_file, 'w', encoding='utf-8') as f:
                json.dump(mounts_data, f, ensure_ascii=False, indent=2)
            
            result["directories_created"].append(str(mounts_file))
        
        result["mounts_initialized"] = True
    
    def _initialize_registry(self, result: Dict[str, Any]):
        """レジストリを初期化"""
        if not self.ecosystem_dir.exists():
            result["errors"].append(f"エコシステムディレクトリが存在しません: {self.ecosystem_dir}")
            return
        
        # レジストリを取得（グローバルインスタンスを使用）
        self.registry = get_registry()
        
        # 統計情報を収集
        result["registry_loaded"] = True
        result["packs_loaded"] = len(self.registry.packs)
        result["components_loaded"] = len(self.registry.get_all_components())
    
    def _initialize_active_ecosystem(self, result: Dict[str, Any]):
        """アクティブエコシステムを初期化"""
        active_file = self.user_data_dir / "active_ecosystem.json"
        
        # active_ecosystem.jsonが存在しない場合は作成
        if not active_file.exists():
            default_data = {
                # 公式は内容を定義しない - 最初のPackが自己設定する
                "active_pack_identity": None,
                "overrides": {},
                "disabled_components": [],
                "disabled_addons": [],
                "metadata": {}
            }
            
            with open(active_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            
            result["directories_created"].append(str(active_file))
        
        # ActiveEcosystemManagerを取得
        self.active_ecosystem = get_active_ecosystem_manager()
        result["active_ecosystem_loaded"] = True
    
    def _seed_assets(self, result: Dict[str, Any]):
        """
        アセットのseed展開（公式は実行しない）
        
        公式は具体的なアセット構造を知らない。
        各コンポーネントがsetup.pyで自身のseedを行う。
        """
        # 公式は何もしない - コンポーネントの責務
        pass
    
    def _is_assets_empty(self, path: Path) -> bool:
        """
        assetsディレクトリが実質的に空かどうか判定
        
        除外対象以外のサブディレクトリが存在しなければ「空」とみなす
        """
        if not path.exists():
            return True
        
        for item in path.iterdir():
            # 除外対象でなく、かつディレクトリなら空ではない
            if item.is_dir() and item.name not in self.SEED_EXCLUDE_DIRS:
                return False
        
        return True
    
    def _copy_plugin_dirs(self, src: Path, dst: Path) -> int:
        """
        プラグインディレクトリ（サブディレクトリのみ）をコピー
        
        Args:
            src: コピー元ディレクトリ
            dst: コピー先ディレクトリ
        
        Returns:
            コピーしたディレクトリ数
        """
        copied_count = 0
        
        for item in src.iterdir():
            # ディレクトリのみ、かつ除外対象でないもの
            if item.is_dir() and item.name not in self.SEED_EXCLUDE_DIRS:
                dst_item = dst / item.name
                if not dst_item.exists():
                    try:
                        shutil.copytree(item, dst_item)
                        copied_count += 1
                        print(f"  [Seed] コピー: {item.name}")
                    except Exception as e:
                        print(f"  [Seed] コピー失敗: {item.name} - {e}")
        
        return copied_count
    
    def _migrate_chats(self, result: Dict[str, Any]):
        """
        チャットデータの移行（公式は実行しない）
        
        公式は「チャット」という概念を知らない。
        chatsコンポーネントがsetup.pyで自身の移行を行う。
        """
        # 公式は何もしない - コンポーネントの責務
        pass
    
    def _is_chats_empty(self, path: Path) -> bool:
        """
        chatsディレクトリが空かどうか判定
        
        UUIDディレクトリが1つでも存在すれば「空ではない」
        """
        if not path.exists():
            return True
        
        for item in path.iterdir():
            if item.is_dir():
                try:
                    uuid.UUID(item.name)
                    return False  # 有効なチャットディレクトリが存在
                except ValueError:
                    pass
        
        return True
    
    def validate(self) -> Dict[str, Any]:
        """
        エコシステムの整合性を検証
        
        Returns:
            検証結果
        """
        result = {
            "valid": True,
            "warnings": [],
            "errors": []
        }
        
        if not self.registry:
            result["valid"] = False
            result["errors"].append("レジストリが初期化されていません")
            return result
        
        if not self.active_ecosystem:
            result["valid"] = False
            result["errors"].append("アクティブエコシステムが初期化されていません")
            return result
        
        # アクティブなPackが存在するか確認
        active_identity = self.active_ecosystem.active_pack_identity
        pack = self.registry.get_pack_by_identity(active_identity)
        
        if not pack:
            result["valid"] = False
            result["errors"].append(f"アクティブなPack '{active_identity}' が見つかりません")
            return result
        
        # オーバーライドされたコンポーネントが存在するか確認
        overrides = self.active_ecosystem.get_all_overrides()
        for comp_type, comp_id in overrides.items():
            component = self.registry.get_component(pack.pack_id, comp_type, comp_id)
            if not component:
                result["warnings"].append(
                    f"オーバーライド '{comp_type}:{comp_id}' のコンポーネントが見つかりません"
                )
        
        # 必須依存関係の確認
        for component in self.registry.get_all_components():
            connectivity = self.registry.resolve_connectivity(component)
            for missing in connectivity.get('missing_requires', []):
                result["warnings"].append(
                    f"コンポーネント '{component.full_id}' の必須依存 '{missing}' が見つかりません"
                )
        
        return result


def initialize_ecosystem(
    user_data_dir: str = "user_data",
    ecosystem_dir: str = "ecosystem"
) -> Dict[str, Any]:
    """
    エコシステムを初期化（ショートカット関数）
    
    Args:
        user_data_dir: ユーザーデータディレクトリ
        ecosystem_dir: エコシステムディレクトリ
    
    Returns:
        初期化結果
    """
    initializer = EcosystemInitializer(user_data_dir, ecosystem_dir)
    return initializer.initialize()


def validate_ecosystem() -> Dict[str, Any]:
    """
    エコシステムを検証（ショートカット関数）
    
    Returns:
        検証結果
    """
    initializer = EcosystemInitializer()
    initializer.registry = get_registry()
    initializer.active_ecosystem = get_active_ecosystem_manager()
    return initializer.validate()
