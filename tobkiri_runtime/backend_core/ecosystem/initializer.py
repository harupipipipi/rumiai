"""
エコシステム初期化

アプリケーション起動時にエコシステムを初期化する。
マウント、レジストリ、アクティブエコシステムの初期化を行う。
"""

import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from .mounts import MountManager, get_mount_manager
from .registry import Registry, get_registry
from .active_ecosystem import (
    ActiveEcosystemManager,
    get_active_ecosystem_manager,
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
        """Reject legacy Registry activation without creating compatibility state.

        Runtime activation is owned by the Authority Kernel and an immutable
        captured v4 dispatch session.  This compatibility entry point must not
        manufacture mounts, scan installed Packs, or create an implicit active
        Pack configuration.
        """
        return {
            "success": False,
            "mounts_initialized": False,
            "directories_created": [],
            "registry_loaded": False,
            "packs_loaded": 0,
            "components_loaded": 0,
            "active_ecosystem_loaded": False,
            "v4_dispatch_required": True,
            "errors": [
                "Legacy ecosystem initialization is disabled; "
                "use an Authority-resolved Profile and captured v4 dispatch session"
            ],
        }
    
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
                    "data.chats": "./user_data/chats",
                    "data.settings": "./user_data/settings",
                    "data.cache": "./user_data/cache",
                    "data.shared": "./user_data/shared",
                }
            }
            
            with open(mounts_file, 'w', encoding='utf-8') as f:
                json.dump(mounts_data, f, ensure_ascii=False, indent=2)
            
            result["directories_created"].append(str(mounts_file))
        
        result["mounts_initialized"] = True
    
    def _initialize_registry(self, result: Dict[str, Any]):
        """Keep the removed runtime Registry path fail closed."""
        del result
        self.registry = None
    
    def _initialize_active_ecosystem(self, result: Dict[str, Any]):
        """アクティブエコシステムを初期化"""
        active_file = self.user_data_dir / "active_ecosystem.json"
        
        # active_ecosystem.jsonが存在しない場合は作成
        if not active_file.exists():
            default_data: Dict[str, Any] = {
                "active_pack_identity": None,
                "overrides": {},
                "disabled_components": [],
                "disabled_addons": [],
                "metadata": {}
            }
            
            with open(active_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            
            result["directories_created"].append(str(active_file))
        
        # Initializers can target an arbitrary user_data directory during tests,
        # setup, or embedded runtimes, so bind the manager to this active file
        # instead of reusing the process-global default.
        self.active_ecosystem = ActiveEcosystemManager(config_path=str(active_file))
        result["active_ecosystem_loaded"] = True
    
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
    
    def validate(self) -> Dict[str, Any]:
        """Report that the removed runtime Registry cannot validate Packs."""
        return {
            "valid": False,
            "warnings": [],
            "errors": [
                "Legacy ecosystem validation is disabled; use the v4 catalog "
                "and Authority-resolved Profile"
            ],
        }


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
