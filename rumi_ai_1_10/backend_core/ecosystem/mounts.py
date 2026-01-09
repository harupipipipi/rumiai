# backend_core/ecosystem/mounts.py
"""
マウント管理システム

データ保存先の抽象化レイヤーを提供する。
user_data/mounts.json でマウントポイントを設定可能。
"""

import os
import json
import threading
from pathlib import Path
from typing import Dict, Optional, Any


# デフォルトのマウント設定
DEFAULT_MOUNTS = {
    "data.chats": "./user_data/chats",
    "data.settings": "./user_data/settings",
    "data.cache": "./user_data/cache",
    "data.shared": "./user_data/shared",
    # assets用マウント（runtime/asset分離）
    "data.tools.assets": "./user_data/default_tool/assets",
    "data.prompts.assets": "./user_data/default_prompt/assets",
    "data.ai_clients.assets": "./user_data/default_ai_client/assets",
    "data.supporters.assets": "./user_data/default_supporter/assets",
}

# グローバルインスタンス（遅延初期化）
_global_mount_manager: Optional['MountManager'] = None
_init_lock = threading.Lock()


class MountManager:
    """
    マウントポイント管理クラス
    
    マウントポイントとは、論理的なデータ保存先（例: "data.chats"）を
    実際のファイルシステムパスにマッピングする仕組み。
    
    Example:
        manager = MountManager()
        chats_path = manager.get_path("data.chats")
        # -> Path("./user_data/chats")
        
        # カスタムパスに変更
        manager.set_mount("data.chats", "/mnt/nas/chats")
    """
    
    def __init__(
        self,
        config_path: str = "user_data/mounts.json",
        base_dir: str = None
    ):
        """
        Args:
            config_path: マウント設定ファイルのパス
            base_dir: 相対パスの基準ディレクトリ（省略時はカレントディレクトリ）
        """
        self.config_path = Path(config_path)
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self._mounts: Dict[str, str] = {}
        self._lock = threading.Lock()
        
        # 設定を読み込み
        self._load_config()
    
    def _load_config(self):
        """設定ファイルを読み込む"""
        with self._lock:
            if self.config_path.exists():
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._mounts = data.get("mounts", {})
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[MountManager] 設定ファイル読み込みエラー: {e}")
                    self._mounts = {}
            
            # デフォルト値で補完
            for key, default_path in DEFAULT_MOUNTS.items():
                if key not in self._mounts:
                    self._mounts[key] = default_path
    
    def _save_config(self):
        """設定ファイルを保存"""
        with self._lock:
            # 親ディレクトリを作成
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "version": "1.0",
                "mounts": self._mounts
            }
            
            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except IOError as e:
                print(f"[MountManager] 設定ファイル保存エラー: {e}")
    
    def get_path(self, mount_point: str, ensure_exists: bool = True) -> Path:
        """
        マウントポイントの実際のパスを取得
        
        Args:
            mount_point: マウントポイント名（例: "data.chats"）
            ensure_exists: Trueの場合、ディレクトリが存在しなければ作成
        
        Returns:
            実際のファイルシステムパス
        
        Raises:
            KeyError: 未定義のマウントポイントの場合
        """
        with self._lock:
            if mount_point not in self._mounts:
                raise KeyError(f"未定義のマウントポイント: {mount_point}")
            
            raw_path = self._mounts[mount_point]
        
        # 相対パスの場合はbase_dirを基準に解決
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.base_dir / path
        
        path = path.resolve()
        
        # ディレクトリを作成
        if ensure_exists:
            path.mkdir(parents=True, exist_ok=True)
        
        return path
    
    def set_mount(self, mount_point: str, path: str, save: bool = True):
        """
        マウントポイントを設定
        
        Args:
            mount_point: マウントポイント名
            path: 実際のパス
            save: 設定ファイルに保存するかどうか
        """
        with self._lock:
            self._mounts[mount_point] = path
        
        if save:
            self._save_config()
    
    def get_all_mounts(self) -> Dict[str, str]:
        """すべてのマウント設定を取得"""
        with self._lock:
            return dict(self._mounts)
    
    def has_mount(self, mount_point: str) -> bool:
        """マウントポイントが定義されているか確認"""
        with self._lock:
            return mount_point in self._mounts
    
    def remove_mount(self, mount_point: str, save: bool = True) -> bool:
        """
        マウントポイントを削除
        
        Args:
            mount_point: マウントポイント名
            save: 設定ファイルに保存するかどうか
        
        Returns:
            削除成功の可否
        """
        with self._lock:
            if mount_point in self._mounts:
                del self._mounts[mount_point]
                if save:
                    self._save_config()
                return True
        return False
    
    def reset_to_defaults(self, save: bool = True):
        """デフォルト設定にリセット"""
        with self._lock:
            self._mounts = dict(DEFAULT_MOUNTS)
        
        if save:
            self._save_config()
    
    def validate_paths(self) -> Dict[str, Dict[str, Any]]:
        """
        すべてのマウントパスを検証
        
        Returns:
            検証結果の辞書
        """
        results = {}
        
        with self._lock:
            mounts = dict(self._mounts)
        
        for mount_point, raw_path in mounts.items():
            path = Path(raw_path)
            if not path.is_absolute():
                path = self.base_dir / path
            
            results[mount_point] = {
                "raw_path": raw_path,
                "resolved_path": str(path.resolve()),
                "exists": path.exists(),
                "is_directory": path.is_dir() if path.exists() else None,
                "writable": os.access(path, os.W_OK) if path.exists() else None
            }
        
        return results


def get_mount_manager() -> MountManager:
    """
    グローバルなMountManagerインスタンスを取得
    
    Returns:
        MountManagerインスタンス
    """
    global _global_mount_manager
    
    if _global_mount_manager is None:
        with _init_lock:
            if _global_mount_manager is None:
                _global_mount_manager = MountManager()
    
    return _global_mount_manager


def get_mount_path(mount_point: str, ensure_exists: bool = True) -> Path:
    """
    マウントポイントの実際のパスを取得（ショートカット関数）
    
    Args:
        mount_point: マウントポイント名
        ensure_exists: ディレクトリが存在しなければ作成
    
    Returns:
        実際のファイルシステムパス
    """
    return get_mount_manager().get_path(mount_point, ensure_exists)


def initialize_mounts(config_path: str = None, base_dir: str = None):
    """
    マウントシステムを初期化
    
    アプリケーション起動時に一度だけ呼び出す。
    
    Args:
        config_path: マウント設定ファイルのパス
        base_dir: 相対パスの基準ディレクトリ
    """
    global _global_mount_manager
    
    with _init_lock:
        kwargs = {}
        if config_path:
            kwargs['config_path'] = config_path
        if base_dir:
            kwargs['base_dir'] = base_dir
        
        _global_mount_manager = MountManager(**kwargs)
