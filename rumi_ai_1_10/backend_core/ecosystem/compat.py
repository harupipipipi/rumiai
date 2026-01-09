# backend_core/ecosystem/compat.py
"""
後方互換性レイヤー

既存のコードがエコシステムの有無に関わらず動作するようにする。
また、runtime/asset分離APIを提供する。
"""

from pathlib import Path
from typing import Optional, Dict, Any
import threading
import sys

# エコシステムが初期化されているかどうか
_ecosystem_initialized = False
_init_lock = threading.Lock()


def is_ecosystem_initialized() -> bool:
    """エコシステムが初期化されているか確認"""
    global _ecosystem_initialized
    return _ecosystem_initialized


def mark_ecosystem_initialized():
    """エコシステムを初期化済みとしてマーク"""
    global _ecosystem_initialized
    with _init_lock:
        _ecosystem_initialized = True
        _add_runtime_dirs_to_path()


def _add_runtime_dirs_to_path():
    """
    各コンポーネントのruntime_dirをsys.pathに追加
    
    これにより、エコシステム初期化後は以下のimportが可能になる：
    - from tool_loader import ToolLoader
    - from tool.tool_loader import ToolLoader（パッケージ形式）
    - from ai_client.ai_client_loader import AIClientLoader（パッケージ形式）
    """
    try:
        from .registry import get_registry
        registry = get_registry()
        
        # 追加するコンポーネントタイプとエイリアス名
        component_types = [
            ('tool_pack', 'tool'),
            ('prompt_pack', 'prompt'),
            ('supporter_pack', 'supporter'),
            ('ai_client_provider', 'ai_client'),
        ]
        
        # 1. 各コンポーネントディレクトリを追加（from tool_loader import ... 形式用）
        for comp_type, alias in component_types:
            components = registry.get_components_by_type(comp_type)
            if components:
                runtime_dir = str(components[0].path)
                if runtime_dir not in sys.path:
                    sys.path.insert(0, runtime_dir)
                    print(f"[compat] sys.path に追加: {runtime_dir}")
        
        # 2. components ディレクトリ自体を追加（from tool.tool_loader import ... 形式用）
        # 最初のコンポーネントのパスから components ディレクトリを取得
        if registry.packs:
            pack = list(registry.packs.values())[0]
            components_dir = pack.path / "backend" / "components"
            if components_dir.exists():
                components_dir_str = str(components_dir)
                if components_dir_str not in sys.path:
                    sys.path.insert(0, components_dir_str)
                    print(f"[compat] sys.path に追加 (components): {components_dir_str}")
        
    except Exception as e:
        print(f"[compat] runtime_dir の sys.path 追加に失敗: {e}")


def get_chats_dir() -> Path:
    """
    チャットディレクトリを取得
    
    エコシステム初期化済みならマウント経由、
    そうでなければ従来のパスを返す。
    """
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.chats')
        except Exception:
            pass
    
    # フォールバック
    return Path('chats')


def get_settings_dir() -> Path:
    """設定ディレクトリを取得"""
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.settings')
        except Exception:
            pass
    
    return Path('user_data/settings')


def get_cache_dir() -> Path:
    """キャッシュディレクトリを取得"""
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.cache')
        except Exception:
            pass
    
    return Path('user_data/cache')


def get_shared_dir() -> Path:
    """共有ディレクトリを取得"""
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.shared')
        except Exception:
            pass
    
    return Path('user_data/shared')


def get_user_data_dir() -> Path:
    """ユーザーデータディレクトリを取得"""
    return Path('user_data')


def get_component_path(component_type: str, component_id: str = None) -> Optional[Path]:
    """
    コンポーネントのパスを取得
    
    Args:
        component_type: コンポーネントタイプ（tool_pack, prompt_pack等）
        component_id: コンポーネントID（省略時はアクティブなものを使用）
    
    Returns:
        コンポーネントディレクトリのパス、または None
    """
    if not _ecosystem_initialized:
        # フォールバック: 従来のパス
        type_to_dir = {
            'tool_pack': 'tool',
            'prompt_pack': 'prompt',
            'supporter_pack': 'supporter',
            'ai_client_provider': 'ai_client',
            'chats': 'chats'
        }
        dir_name = type_to_dir.get(component_type)
        if dir_name:
            return Path(dir_name)
        return None
    
    try:
        from .registry import get_registry
        from .active_ecosystem import get_active_ecosystem_manager
        
        registry = get_registry()
        manager = get_active_ecosystem_manager()
        
        # アクティブなPackを取得
        pack = registry.get_pack_by_identity(manager.active_pack_identity)
        if not pack:
            return None
        
        # component_idが指定されていない場合はオーバーライドを使用
        if component_id is None:
            component_id = manager.get_override(component_type)
        
        if component_id is None:
            # オーバーライドがない場合、最初に見つかったものを使用
            components = registry.get_components_by_type(component_type)
            if components:
                return components[0].path
            return None
        
        # 指定されたコンポーネントを取得
        component = registry.get_component(pack.pack_id, component_type, component_id)
        if component:
            return component.path
        
        return None
        
    except Exception as e:
        print(f"[compat] コンポーネントパス取得エラー: {e}")
        return None


# ============================================
# Runtime / Assets 分離API（選択肢1実装）
# ============================================

def get_tools_runtime_dir() -> Path:
    """
    ツールのruntimeディレクトリ（ローダーコード）を取得
    
    Returns:
        ecosystem/.../components/tool/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .registry import get_registry
            registry = get_registry()
            components = registry.get_components_by_type('tool_pack')
            if components:
                return components[0].path
        except Exception:
            pass
    return Path('tool')


def get_tools_assets_dir() -> Path:
    """
    ツールのassetsディレクトリ（プラグイン実体）を取得
    
    Returns:
        user_data/default_tool/assets/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.tools.assets')
        except Exception:
            pass
    return Path('tool')


def get_prompts_runtime_dir() -> Path:
    """
    プロンプトのruntimeディレクトリ（ローダーコード）を取得
    
    Returns:
        ecosystem/.../components/prompt/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .registry import get_registry
            registry = get_registry()
            components = registry.get_components_by_type('prompt_pack')
            if components:
                return components[0].path
        except Exception:
            pass
    return Path('prompt')


def get_prompts_assets_dir() -> Path:
    """
    プロンプトのassetsディレクトリ（プラグイン実体）を取得
    
    Returns:
        user_data/default_prompt/assets/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.prompts.assets')
        except Exception:
            pass
    return Path('prompt')


def get_supporters_runtime_dir() -> Path:
    """
    サポーターのruntimeディレクトリ（ローダーコード）を取得
    
    Returns:
        ecosystem/.../components/supporter/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .registry import get_registry
            registry = get_registry()
            components = registry.get_components_by_type('supporter_pack')
            if components:
                return components[0].path
        except Exception:
            pass
    return Path('supporter')


def get_supporters_assets_dir() -> Path:
    """
    サポーターのassetsディレクトリ（プラグイン実体）を取得
    
    Returns:
        user_data/default_supporter/assets/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.supporters.assets')
        except Exception:
            pass
    return Path('supporter')


def get_ai_clients_runtime_dir() -> Path:
    """
    AIクライアントのruntimeディレクトリ（ローダーコード）を取得
    
    Returns:
        ecosystem/.../components/ai_client/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .registry import get_registry
            registry = get_registry()
            components = registry.get_components_by_type('ai_client_provider')
            if components:
                return components[0].path
        except Exception:
            pass
    return Path('ai_client')


def get_ai_clients_assets_dir() -> Path:
    """
    AIクライアントのassetsディレクトリ（プラグイン実体）を取得
    
    Returns:
        user_data/default_ai_client/assets/ または フォールバック
    """
    if _ecosystem_initialized:
        try:
            from .mounts import get_mount_path
            return get_mount_path('data.ai_clients.assets')
        except Exception:
            pass
    return Path('ai_client')


# ============================================
# 後方互換関数（assets_dirを返す）
# ============================================

def get_tools_dir() -> Path:
    """
    ツールディレクトリを取得（後方互換）
    
    Note: assets_dir を返す（runtime/asset分離後の標準動作）
    """
    return get_tools_assets_dir()


def get_prompts_dir() -> Path:
    """
    プロンプトディレクトリを取得（後方互換）
    
    Note: assets_dir を返す（runtime/asset分離後の標準動作）
    """
    return get_prompts_assets_dir()


def get_supporters_dir() -> Path:
    """
    サポーターディレクトリを取得（後方互換）
    
    Note: assets_dir を返す（runtime/asset分離後の標準動作）
    """
    return get_supporters_assets_dir()


def get_ai_clients_dir() -> Path:
    """
    AIクライアントディレクトリを取得（後方互換）
    
    Note: assets_dir を返す（runtime/asset分離後の標準動作）
    """
    return get_ai_clients_assets_dir()
