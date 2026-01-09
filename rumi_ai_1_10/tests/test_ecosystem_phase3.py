# tests/test_ecosystem_phase3.py
"""
Phase 3 Default Pack構造のテスト
"""

import json
import shutil
import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend_core.ecosystem.registry import Registry, PackInfo, ComponentInfo
from backend_core.ecosystem.uuid_utils import generate_pack_uuid, generate_component_uuid


@pytest.fixture(autouse=True)
def reset_registry_state():
    """各テスト前後でレジストリのグローバル状態をリセット"""
    import backend_core.ecosystem.registry as reg
    
    # 元の状態を保存
    original_registry = reg._global_registry
    
    # テスト前にリセット
    reg._global_registry = None
    
    yield
    
    # テスト後に元の状態に復元
    reg._global_registry = original_registry


class TestDefaultPackStructure:
    """Default Pack構造のテスト"""
    
    @pytest.fixture
    def ecosystem_dir(self):
        """テスト用エコシステムディレクトリ"""
        # 実際のecosystem/defaultを使用
        return Path("ecosystem")
    
    def test_ecosystem_json_exists(self, ecosystem_dir):
        """ecosystem.jsonが存在する"""
        ecosystem_file = ecosystem_dir / "default" / "backend" / "ecosystem.json"
        assert ecosystem_file.exists(), f"ecosystem.jsonが見つかりません: {ecosystem_file}"
    
    def test_ecosystem_json_valid(self, ecosystem_dir):
        """ecosystem.jsonが有効なJSON"""
        ecosystem_file = ecosystem_dir / "default" / "backend" / "ecosystem.json"
        with open(ecosystem_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data['pack_id'] == 'default'
        assert 'pack_identity' in data
        assert 'version' in data
        assert 'vocabulary' in data
        assert 'types' in data['vocabulary']
    
    def test_component_manifests_exist(self, ecosystem_dir):
        """すべてのコンポーネントのmanifest.jsonが存在する"""
        components_dir = ecosystem_dir / "default" / "backend" / "components"
        expected_components = ['chats', 'tool', 'prompt', 'supporter', 'ai_client']
        
        for component_name in expected_components:
            manifest_file = components_dir / component_name / "manifest.json"
            assert manifest_file.exists(), f"manifest.jsonが見つかりません: {manifest_file}"
    
    def test_component_manifests_valid(self, ecosystem_dir):
        """すべてのコンポーネントのmanifest.jsonが有効"""
        components_dir = ecosystem_dir / "default" / "backend" / "components"
        
        for component_dir in components_dir.iterdir():
            if component_dir.is_dir():
                manifest_file = component_dir / "manifest.json"
                if manifest_file.exists():
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    assert 'type' in data, f"{component_dir.name}: typeがありません"
                    assert 'id' in data, f"{component_dir.name}: idがありません"
                    assert 'version' in data, f"{component_dir.name}: versionがありません"


class TestRegistry:
    """Registryのテスト"""
    
    @pytest.fixture
    def temp_ecosystem(self):
        """一時的なエコシステムディレクトリを作成"""
        temp_dir = tempfile.mkdtemp()
        ecosystem_dir = Path(temp_dir) / "ecosystem"
        
        # テスト用Pack構造を作成
        pack_dir = ecosystem_dir / "test_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        # ecosystem.json
        ecosystem_data = {
            "pack_id": "test_pack",
            "pack_identity": "local:test-pack",
            "version": "1.0.0",
            "vocabulary": {
                "types": ["test_component"]
            }
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # Component
        component_dir = pack_dir / "components" / "test_comp"
        component_dir.mkdir(parents=True)
        
        component_data = {
            "type": "test_component",
            "id": "test_v1",
            "version": "1.0.0",
            "connectivity": {
                "accepts": [],
                "provides": ["test_api"]
            }
        }
        with open(component_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(component_data, f)
        
        yield ecosystem_dir
        
        # クリーンアップ
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_load_pack(self, temp_ecosystem):
        """Packを読み込める"""
        registry = Registry(str(temp_ecosystem))
        packs = registry.load_all_packs()
        
        assert len(packs) == 1
        assert "test_pack" in packs
        
        pack = packs["test_pack"]
        assert pack.pack_id == "test_pack"
        assert pack.pack_identity == "local:test-pack"
    
    def test_component_loaded(self, temp_ecosystem):
        """コンポーネントが読み込まれる"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        component = registry.get_component("test_pack", "test_component", "test_v1")
        assert component is not None
        assert component.type == "test_component"
        assert component.id == "test_v1"
    
    def test_uuid_generation(self, temp_ecosystem):
        """UUIDが正しく生成される"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        pack = registry.get_pack("test_pack")
        expected_pack_uuid = str(generate_pack_uuid("local:test-pack"))
        assert pack.uuid == expected_pack_uuid
        
        component = registry.get_component("test_pack", "test_component", "test_v1")
        expected_comp_uuid = str(generate_component_uuid(
            pack.uuid, "test_component", "test_v1"
        ))
        assert component.uuid == expected_comp_uuid
    
    def test_get_components_by_type(self, temp_ecosystem):
        """タイプでコンポーネントを取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        components = registry.get_components_by_type("test_component")
        assert len(components) == 1
        assert components[0].id == "test_v1"
    
    def test_get_component_by_uuid(self, temp_ecosystem):
        """UUIDでコンポーネントを取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        component = registry.get_component("test_pack", "test_component", "test_v1")
        
        found = registry.get_component_by_uuid(component.uuid)
        assert found is not None
        assert found.id == component.id
    
    def test_get_pack_by_identity(self, temp_ecosystem):
        """Pack IdentityでPackを取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        pack = registry.get_pack_by_identity("local:test-pack")
        assert pack is not None
        assert pack.pack_id == "test_pack"
    
    def test_get_pack_by_uuid(self, temp_ecosystem):
        """Pack UUIDでPackを取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        pack = registry.get_pack("test_pack")
        
        found = registry.get_pack_by_uuid(pack.uuid)
        assert found is not None
        assert found.pack_id == pack.pack_id
    
    def test_get_all_components(self, temp_ecosystem):
        """すべてのコンポーネントを取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        components = registry.get_all_components()
        assert len(components) == 1
    
    def test_get_vocabulary(self, temp_ecosystem):
        """vocabularyを取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        vocab = registry.get_vocabulary("test_pack")
        assert "test_component" in vocab
    
    def test_nonexistent_pack(self, temp_ecosystem):
        """存在しないPackの取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        pack = registry.get_pack("nonexistent")
        assert pack is None
    
    def test_nonexistent_component(self, temp_ecosystem):
        """存在しないコンポーネントの取得"""
        registry = Registry(str(temp_ecosystem))
        registry.load_all_packs()
        
        component = registry.get_component("test_pack", "nonexistent", "v1")
        assert component is None


class TestRegistryConnectivity:
    """Registry接続性解決のテスト"""
    
    @pytest.fixture
    def connected_ecosystem(self):
        """接続性を持つエコシステム"""
        temp_dir = tempfile.mkdtemp()
        ecosystem_dir = Path(temp_dir) / "ecosystem"
        pack_dir = ecosystem_dir / "conn_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        # ecosystem.json
        ecosystem_data = {
            "pack_id": "conn_pack",
            "pack_identity": "local:conn-pack",
            "version": "1.0.0",
            "vocabulary": {
                "types": ["main_comp", "dep_comp"]
            }
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # メインコンポーネント
        main_dir = pack_dir / "components" / "main"
        main_dir.mkdir(parents=True)
        
        main_data = {
            "type": "main_comp",
            "id": "main_v1",
            "version": "1.0.0",
            "connectivity": {
                "accepts": ["dep_comp"],
                "provides": ["main_api"],
                "requires": ["dep_comp"]
            }
        }
        with open(main_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(main_data, f)
        
        # 依存コンポーネント
        dep_dir = pack_dir / "components" / "dep"
        dep_dir.mkdir(parents=True)
        
        dep_data = {
            "type": "dep_comp",
            "id": "dep_v1",
            "version": "1.0.0",
            "connectivity": {
                "accepts": [],
                "provides": ["dep_api"],
                "requires": []
            }
        }
        with open(dep_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(dep_data, f)
        
        yield ecosystem_dir
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_resolve_connectivity(self, connected_ecosystem):
        """接続性を解決できる"""
        registry = Registry(str(connected_ecosystem))
        registry.load_all_packs()
        
        main_comp = registry.get_component("conn_pack", "main_comp", "main_v1")
        connectivity = registry.resolve_connectivity(main_comp)
        
        assert len(connectivity['accepts']) == 1
        assert connectivity['accepts'][0].type == "dep_comp"
        assert "main_api" in connectivity['provides']
        assert len(connectivity['requires']) == 1
        assert connectivity['missing_requires'] == []
    
    def test_missing_requires(self, connected_ecosystem):
        """見つからない必須依存を検出"""
        temp_dir = connected_ecosystem.parent
        pack_dir = connected_ecosystem / "conn_pack" / "backend"
        
        # 存在しない依存を持つコンポーネントを追加
        orphan_dir = pack_dir / "components" / "orphan"
        orphan_dir.mkdir(parents=True)
        
        orphan_data = {
            "type": "main_comp",
            "id": "orphan_v1",
            "version": "1.0.0",
            "connectivity": {
                "accepts": [],
                "provides": [],
                "requires": ["nonexistent_type"]
            }
        }
        with open(orphan_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(orphan_data, f)
        
        registry = Registry(str(connected_ecosystem))
        registry.load_all_packs()
        
        orphan_comp = registry.get_component("conn_pack", "main_comp", "orphan_v1")
        connectivity = registry.resolve_connectivity(orphan_comp)
        
        assert "nonexistent_type" in connectivity['missing_requires']


class TestRegistryMultiplePacks:
    """複数Packのテスト"""
    
    @pytest.fixture
    def multi_pack_ecosystem(self):
        """複数Packを持つエコシステム"""
        temp_dir = tempfile.mkdtemp()
        ecosystem_dir = Path(temp_dir) / "ecosystem"
        
        # Pack A
        pack_a_dir = ecosystem_dir / "pack_a" / "backend"
        pack_a_dir.mkdir(parents=True)
        
        ecosystem_a = {
            "pack_id": "pack_a",
            "pack_identity": "local:pack-a",
            "version": "1.0.0",
            "vocabulary": {"types": ["type_a"]}
        }
        with open(pack_a_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_a, f)
        
        comp_a_dir = pack_a_dir / "components" / "comp_a"
        comp_a_dir.mkdir(parents=True)
        
        comp_a = {
            "type": "type_a",
            "id": "comp_a_v1",
            "version": "1.0.0"
        }
        with open(comp_a_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_a, f)
        
        # Pack B
        pack_b_dir = ecosystem_dir / "pack_b" / "backend"
        pack_b_dir.mkdir(parents=True)
        
        ecosystem_b = {
            "pack_id": "pack_b",
            "pack_identity": "local:pack-b",
            "version": "2.0.0",
            "vocabulary": {"types": ["type_b"]}
        }
        with open(pack_b_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_b, f)
        
        comp_b_dir = pack_b_dir / "components" / "comp_b"
        comp_b_dir.mkdir(parents=True)
        
        comp_b = {
            "type": "type_b",
            "id": "comp_b_v1",
            "version": "2.0.0"
        }
        with open(comp_b_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_b, f)
        
        yield ecosystem_dir
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_load_multiple_packs(self, multi_pack_ecosystem):
        """複数Packを読み込める"""
        registry = Registry(str(multi_pack_ecosystem))
        packs = registry.load_all_packs()
        
        assert len(packs) == 2
        assert "pack_a" in packs
        assert "pack_b" in packs
    
    def test_components_from_different_packs(self, multi_pack_ecosystem):
        """異なるPackからコンポーネントを取得"""
        registry = Registry(str(multi_pack_ecosystem))
        registry.load_all_packs()
        
        comp_a = registry.get_component("pack_a", "type_a", "comp_a_v1")
        comp_b = registry.get_component("pack_b", "type_b", "comp_b_v1")
        
        assert comp_a is not None
        assert comp_b is not None
        assert comp_a.pack_id == "pack_a"
        assert comp_b.pack_id == "pack_b"
    
    def test_all_components_across_packs(self, multi_pack_ecosystem):
        """全Packからすべてのコンポーネントを取得"""
        registry = Registry(str(multi_pack_ecosystem))
        registry.load_all_packs()
        
        all_components = registry.get_all_components()
        assert len(all_components) == 2


class TestRegistryEmptyEcosystem:
    """空のエコシステムのテスト"""
    
    def test_empty_ecosystem_dir(self):
        """空のエコシステムディレクトリ"""
        temp_dir = tempfile.mkdtemp()
        ecosystem_dir = Path(temp_dir) / "ecosystem"
        ecosystem_dir.mkdir()
        
        try:
            registry = Registry(str(ecosystem_dir))
            packs = registry.load_all_packs()
            
            assert len(packs) == 0
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_nonexistent_ecosystem_dir(self):
        """存在しないエコシステムディレクトリ"""
        registry = Registry("/nonexistent/path")
        packs = registry.load_all_packs()
        
        assert len(packs) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
