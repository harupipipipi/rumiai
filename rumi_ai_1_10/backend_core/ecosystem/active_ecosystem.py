# backend_core/ecosystem/active_ecosystem.py
"""
アクティブエコシステム管理

現在使用中のPackとコンポーネントのオーバーライド設定を管理する。
"""

import json
import threading
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field, asdict

from .mounts import get_mount_path


@dataclass
class ActiveEcosystemConfig:
    """アクティブエコシステム設定"""
    active_pack_identity: str
    overrides: Dict[str, str] = field(default_factory=dict)
    disabled_components: List[str] = field(default_factory=list)
    disabled_addons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActiveEcosystemConfig':
        return cls(
            active_pack_identity=data.get('active_pack_identity', 'github:haru/default-pack'),
            overrides=data.get('overrides', {}),
            disabled_components=data.get('disabled_components', []),
            disabled_addons=data.get('disabled_addons', []),
            metadata=data.get('metadata', {})
        )


# デフォルト設定
DEFAULT_CONFIG = ActiveEcosystemConfig(
    active_pack_identity=None,  # 公式は特定のPackを指定しない
    overrides={}                # 公式はオーバーライドを定義しない
)


class ActiveEcosystemManager:
    """
    アクティブエコシステム管理クラス
    
    user_data/active_ecosystem.json を読み書きし、
    現在使用中のPack/Componentを管理する。
    """
    
    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: 設定ファイルのパス（省略時はuser_data/active_ecosystem.json）
        """
        if config_path:
            self.config_path = Path(config_path)
        else:
            settings_dir = get_mount_path("data.settings", ensure_exists=True)
            self.config_path = settings_dir.parent / "active_ecosystem.json"
        
        self._config: Optional[ActiveEcosystemConfig] = None
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
                    self._config = ActiveEcosystemConfig.from_dict(data)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[ActiveEcosystem] 設定読み込みエラー: {e}")
                    self._config = self._create_default_config()
            else:
                self._config = self._create_default_config()
                self._save_config_internal()
    
    def _create_default_config(self) -> ActiveEcosystemConfig:
        """デフォルト設定の新しいインスタンスを作成（公式は内容を定義しない）"""
        return ActiveEcosystemConfig(
            active_pack_identity=None,
            overrides={},
            disabled_components=[],
            disabled_addons=[],
            metadata={}
        )
    
    def _save_config_internal(self):
        """設定を保存（ロック内で呼び出す）"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config.to_dict(), f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[ActiveEcosystem] 設定保存エラー: {e}")
    
    def _save_config(self):
        """設定を保存"""
        with self._lock:
            self._save_config_internal()
    
    @property
    def config(self) -> ActiveEcosystemConfig:
        """現在の設定を取得"""
        with self._lock:
            return self._config
    
    @property
    def active_pack_identity(self) -> str:
        """アクティブなPack Identityを取得"""
        with self._lock:
            return self._config.active_pack_identity
    
    @active_pack_identity.setter
    def active_pack_identity(self, value: str):
        """アクティブなPack Identityを設定"""
        with self._lock:
            self._config.active_pack_identity = value
            self._save_config_internal()
    
    def get_override(self, component_type: str) -> Optional[str]:
        """
        コンポーネントタイプのオーバーライドを取得
        
        Args:
            component_type: コンポーネントタイプ
        
        Returns:
            オーバーライドされたコンポーネントID、または None
        """
        with self._lock:
            return self._config.overrides.get(component_type)
    
    def set_override(self, component_type: str, component_id: str):
        """
        コンポーネントタイプのオーバーライドを設定
        
        Args:
            component_type: コンポーネントタイプ
            component_id: 使用するコンポーネントID
        """
        with self._lock:
            self._config.overrides[component_type] = component_id
            self._save_config_internal()
    
    def remove_override(self, component_type: str) -> bool:
        """
        オーバーライドを削除
        
        Args:
            component_type: コンポーネントタイプ
        
        Returns:
            削除成功の可否
        """
        with self._lock:
            if component_type in self._config.overrides:
                del self._config.overrides[component_type]
                self._save_config_internal()
                return True
            return False
    
    def get_all_overrides(self) -> Dict[str, str]:
        """すべてのオーバーライドを取得"""
        with self._lock:
            return dict(self._config.overrides)
    
    def is_component_disabled(self, component_full_id: str) -> bool:
        """
        コンポーネントが無効化されているか確認
        
        Args:
            component_full_id: "pack_id:type:id" 形式
        
        Returns:
            無効化されている場合 True
        """
        with self._lock:
            return component_full_id in self._config.disabled_components
    
    def disable_component(self, component_full_id: str):
        """コンポーネントを無効化"""
        with self._lock:
            if component_full_id not in self._config.disabled_components:
                self._config.disabled_components.append(component_full_id)
                self._save_config_internal()
    
    def enable_component(self, component_full_id: str):
        """コンポーネントを有効化"""
        with self._lock:
            if component_full_id in self._config.disabled_components:
                self._config.disabled_components.remove(component_full_id)
                self._save_config_internal()
    
    def is_addon_disabled(self, addon_id: str) -> bool:
        """アドオンが無効化されているか確認"""
        with self._lock:
            return addon_id in self._config.disabled_addons
    
    def disable_addon(self, addon_id: str):
        """アドオンを無効化"""
        with self._lock:
            if addon_id not in self._config.disabled_addons:
                self._config.disabled_addons.append(addon_id)
                self._save_config_internal()
    
    def enable_addon(self, addon_id: str):
        """アドオンを有効化"""
        with self._lock:
            if addon_id in self._config.disabled_addons:
                self._config.disabled_addons.remove(addon_id)
                self._save_config_internal()
    
    def set_metadata(self, key: str, value: Any):
        """メタデータを設定"""
        with self._lock:
            self._config.metadata[key] = value
            self._save_config_internal()
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """メタデータを取得"""
        with self._lock:
            return self._config.metadata.get(key, default)
    
    def reset_to_defaults(self):
        """デフォルト設定にリセット"""
        with self._lock:
            self._config = self._create_default_config()
            self._save_config_internal()
    
    def reload(self):
        """設定を再読み込み"""
        self._load_config()


# グローバルインスタンス
_global_manager: Optional[ActiveEcosystemManager] = None
_init_lock = threading.Lock()


def get_active_ecosystem_manager() -> ActiveEcosystemManager:
    """グローバルなActiveEcosystemManagerを取得"""
    global _global_manager
    
    if _global_manager is None:
        with _init_lock:
            if _global_manager is None:
                _global_manager = ActiveEcosystemManager()
    
    return _global_manager


def get_active_pack_identity() -> str:
    """アクティブなPack Identityを取得（ショートカット）"""
    return get_active_ecosystem_manager().active_pack_identity


def get_component_override(component_type: str) -> Optional[str]:
    """コンポーネントオーバーライドを取得（ショートカット）"""
    return get_active_ecosystem_manager().get_override(component_type)
