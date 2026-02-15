# tests/test_ecosystem_phase5.py
"""
Phase 5 既存ローダー移行のテスト
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def reset_ecosystem_state():
    """各テスト前後でエコシステムのグローバル状態をリセット"""
    from backend_core.ecosystem import compat
    
    # 元の状態を保存
    original_state = compat._ecosystem_initialized
    
    # テスト前にリセット
    compat._ecosystem_initialized = False
    
    yield
    
    # テスト後に元の状態に復元
    compat._ecosystem_initialized = original_state


class TestCompatibilityLayer:
    """互換性レイヤーのテスト"""
    
    def test_ecosystem_not_initialized(self):
        """エコシステム未初期化時のフォールバック"""
        from backend_core.ecosystem import compat
        
        # 初期化フラグをリセット
        compat._ecosystem_initialized = False
        
        assert compat.get_chats_dir() == Path('chats')
        assert compat.get_settings_dir() == Path('user_data/settings')
        assert compat.get_tools_dir() == Path('tool')
        assert compat.get_prompts_dir() == Path('prompt')
        assert compat.get_supporters_dir() == Path('supporter')
        assert compat.get_ai_clients_dir() == Path('ai_client')
    
    def test_mark_initialized(self):
        """初期化マーク"""
        from backend_core.ecosystem import compat
        
        compat._ecosystem_initialized = False
        assert not compat.is_ecosystem_initialized()
        
        compat.mark_ecosystem_initialized()
        assert compat.is_ecosystem_initialized()
        
        # リセット
        compat._ecosystem_initialized = False
    
    def test_get_component_path_fallback(self):
        """コンポーネントパスのフォールバック"""
        from backend_core.ecosystem import compat
        
        compat._ecosystem_initialized = False
        
        assert compat.get_component_path('tool_pack') == Path('tool')
        assert compat.get_component_path('prompt_pack') == Path('prompt')
        assert compat.get_component_path('unknown_type') is None


class TestChatManagerMigration:
    """ChatManager移行のテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_default_path_without_ecosystem(self, temp_dir):
        """エコシステムなしでのデフォルトパス"""
        from backend_core.ecosystem import compat
        compat._ecosystem_initialized = False
        
        # chat_managerをインポート（パスはchatsになるはず）
        from chat_manager import ChatManager
        
        manager = ChatManager(chats_dir=str(temp_dir / 'chats'))
        assert manager.chats_dir == temp_dir / 'chats'
    
    def test_explicit_path_override(self, temp_dir):
        """明示的なパス指定"""
        from chat_manager import ChatManager
        
        custom_path = temp_dir / 'custom_chats'
        manager = ChatManager(chats_dir=str(custom_path))
        
        assert manager.chats_dir == custom_path


class TestToolLoaderMigration:
    """ToolLoader移行のテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_explicit_path_override(self, temp_dir):
        """明示的なパス指定"""
        from tool.tool_loader import ToolLoader
        
        custom_path = temp_dir / 'custom_tools'
        custom_path.mkdir()
        
        loader = ToolLoader(tools_dir=custom_path)
        assert loader.tools_dir == custom_path


class TestPromptLoaderMigration:
    """PromptLoader移行のテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_explicit_path_override(self, temp_dir):
        """明示的なパス指定"""
        from prompt.prompt_loader import PromptLoader
        
        custom_path = temp_dir / 'custom_prompts'
        custom_path.mkdir()
        
        loader = PromptLoader(prompt_dir=custom_path)
        assert loader.prompt_dir == custom_path


class TestSupporterLoaderMigration:
    """SupporterLoader移行のテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_explicit_path_override(self, temp_dir):
        """明示的なパス指定"""
        from supporter.supporter_loader import SupporterLoader
        
        custom_path = temp_dir / 'custom_supporters'
        
        loader = SupporterLoader(supporter_dir=str(custom_path))
        assert loader.supporter_dir == custom_path


class TestSettingsManagerMigration:
    """SettingsManager移行のテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_explicit_path_override(self, temp_dir):
        """明示的なパス指定"""
        from settings_manager import SettingsManager
        
        custom_path = temp_dir / 'custom_user_data'
        
        manager = SettingsManager(user_data_dir=str(custom_path))
        assert manager.user_data_dir == custom_path


class TestRelationshipManagerMigration:
    """RelationshipManager移行のテスト"""
    
    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
    
    def test_explicit_path_override(self, temp_dir):
        """明示的なパス指定"""
        from relationship_manager import RelationshipManager
        
        custom_path = temp_dir / 'custom_chats'
        custom_path.mkdir()
        
        manager = RelationshipManager(chats_dir=str(custom_path))
        assert manager.chats_dir == custom_path


class TestEcosystemIntegration:
    """エコシステム統合テスト"""
    
    @pytest.fixture
    def full_ecosystem(self):
        """完全なエコシステム環境"""
        temp_dir = tempfile.mkdtemp()
        
        # user_data構造
        user_data = Path(temp_dir) / 'user_data'
        user_data.mkdir()
        (user_data / 'chats').mkdir()
        (user_data / 'settings').mkdir()
        (user_data / 'cache').mkdir()
        (user_data / 'shared').mkdir()
        
        # mounts.json
        mounts_data = {
            "version": "1.0",
            "mounts": {
                "data.chats": str(user_data / 'chats'),
                "data.settings": str(user_data / 'settings'),
                "data.cache": str(user_data / 'cache'),
                "data.shared": str(user_data / 'shared')
            }
        }
        with open(user_data / 'mounts.json', 'w') as f:
            json.dump(mounts_data, f)
        
        # ecosystem構造
        ecosystem = Path(temp_dir) / 'ecosystem'
        pack_dir = ecosystem / 'default' / 'backend'
        pack_dir.mkdir(parents=True)
        
        # ecosystem.json
        ecosystem_data = {
            "pack_id": "default",
            "pack_identity": "github:haru/default-pack",
            "version": "1.0.0",
            "vocabulary": {
                "types": ["chats", "tool_pack", "prompt_pack"]
            }
        }
        with open(pack_dir / 'ecosystem.json', 'w') as f:
            json.dump(ecosystem_data, f)
        
        # コンポーネント
        for comp_type, comp_id in [('chats', 'chats_v1'), ('tool', 'tool_v1')]:
            comp_dir = pack_dir / 'components' / comp_type
            comp_dir.mkdir(parents=True)
            
            type_name = 'tool_pack' if comp_type == 'tool' else comp_type
            manifest = {
                "type": type_name,
                "id": comp_id,
                "version": "1.0.0"
            }
            with open(comp_dir / 'manifest.json', 'w') as f:
                json.dump(manifest, f)
        
        # active_ecosystem.json
        active_data = {
            "active_pack_identity": "github:haru/default-pack",
            "overrides": {
                "chats": "chats_v1",
                "tool_pack": "tool_v1"
            }
        }
        with open(user_data / 'active_ecosystem.json', 'w') as f:
            json.dump(active_data, f)
        
        yield {
            'temp': temp_dir,
            'user_data': user_data,
            'ecosystem': ecosystem
        }
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_full_initialization(self, full_ecosystem):
        """完全な初期化フロー"""
        from backend_core.ecosystem.mounts import MountManager
        from backend_core.ecosystem.registry import Registry
        from backend_core.ecosystem.active_ecosystem import ActiveEcosystemManager
        from backend_core.ecosystem import compat
        
        # マウント初期化
        mounts = MountManager(
            config_path=str(full_ecosystem['user_data'] / 'mounts.json'),
            base_dir=full_ecosystem['temp']
        )
        
        # レジストリ初期化
        registry = Registry(str(full_ecosystem['ecosystem']))
        registry.load_all_packs()
        
        # アクティブエコシステム初期化
        active = ActiveEcosystemManager(
            config_path=str(full_ecosystem['user_data'] / 'active_ecosystem.json')
        )
        
        # 検証
        assert len(registry.packs) == 1
        assert active.active_pack_identity == "github:haru/default-pack"
        assert active.get_override('chats') == 'chats_v1'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
