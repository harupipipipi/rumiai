# tests/test_ecosystem_phase6.py
"""
Phase 6 Addonシステムのテスト
"""

import json
import shutil
import tempfile
import copy
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend_core.ecosystem.addon_manager import (
    AddonManager,
    AddonInfo,
    AddonApplicationResult,
    get_addon_manager,
    reload_addon_manager
)
from backend_core.ecosystem.registry import Registry, ComponentInfo, PackInfo
from backend_core.ecosystem.uuid_utils import generate_pack_uuid, generate_component_uuid


@pytest.fixture(autouse=True)
def reset_global_states():
    """各テスト前後でグローバル状態をリセット"""
    import backend_core.ecosystem.addon_manager as am
    import backend_core.ecosystem.registry as reg
    
    # 元の状態を保存
    original_addon_manager = am._global_addon_manager
    original_registry = reg._global_registry
    
    # テスト前にリセット
    am._global_addon_manager = None
    reg._global_registry = None
    
    yield
    
    # テスト後に元の状態に復元
    am._global_addon_manager = original_addon_manager
    reg._global_registry = original_registry


class TestAddonLoading:
    """アドオン読み込みのテスト"""
    
    @pytest.fixture
    def temp_pack(self):
        """テスト用Pack"""
        temp_dir = tempfile.mkdtemp()
        pack_dir = Path(temp_dir) / "test_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        # ecosystem.json
        ecosystem_data = {
            "pack_id": "test_pack",
            "pack_identity": "local:test-pack",
            "version": "1.0.0",
            "vocabulary": {"types": ["test_type"]}
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # Component
        comp_dir = pack_dir / "components" / "test_comp"
        comp_dir.mkdir(parents=True)
        
        comp_data = {
            "type": "test_type",
            "id": "test_v1",
            "version": "1.0.0",
            "addon_policy": {
                "allowed_manifest_paths": ["/extensions", "/connectivity/accepts"]
            },
            "extensions": {}
        }
        with open(comp_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_data, f)
        
        # Addon
        addons_dir = pack_dir / "addons"
        addons_dir.mkdir()
        
        addon_data = {
            "addon_id": "test_addon",
            "version": "1.0.0",
            "priority": 100,
            "enabled": True,
            "targets": [
                {
                    "pack_identity": "local:test-pack",
                    "component": {"type": "test_type", "id": "test_v1"},
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "add", "path": "/extensions/added_by_addon", "value": True}
                            ]
                        }
                    ]
                }
            ]
        }
        with open(addons_dir / "test.addon.json", 'w', encoding='utf-8') as f:
            json.dump(addon_data, f)
        
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_load_addon(self, temp_pack):
        """アドオンを読み込める"""
        registry = Registry(str(temp_pack))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        
        assert len(manager.addons) == 1
        assert "test_pack:test_addon" in manager.addons
    
    def test_addon_info(self, temp_pack):
        """AddonInfoが正しく設定される"""
        registry = Registry(str(temp_pack))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        addon = manager.get_addon("test_pack:test_addon")
        
        assert addon is not None
        assert addon.addon_id == "test_addon"
        assert addon.version == "1.0.0"
        assert addon.priority == 100
        assert addon.enabled is True


class TestAddonApplication:
    """アドオン適用のテスト"""
    
    @pytest.fixture
    def pack_with_addon(self):
        """アドオン付きPack"""
        temp_dir = tempfile.mkdtemp()
        pack_dir = Path(temp_dir) / "addon_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        pack_uuid = str(generate_pack_uuid("local:addon-pack"))
        
        ecosystem_data = {
            "pack_id": "addon_pack",
            "pack_identity": "local:addon-pack",
            "version": "1.0.0",
            "pack_uuid": pack_uuid,
            "vocabulary": {"types": ["target_type"]}
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # Component
        comp_dir = pack_dir / "components" / "target"
        comp_dir.mkdir(parents=True)
        
        comp_data = {
            "type": "target_type",
            "id": "target_v1",
            "version": "1.0.0",
            "addon_policy": {
                "allowed_manifest_paths": ["/extensions", "/connectivity"]
            },
            "connectivity": {
                "accepts": ["type_a"],
                "provides": []
            },
            "extensions": {
                "original": True
            }
        }
        with open(comp_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_data, f)
        
        # Addon 1: 低優先度
        addons_dir = pack_dir / "addons"
        addons_dir.mkdir()
        
        addon1 = {
            "addon_id": "addon_low",
            "version": "1.0.0",
            "priority": 50,
            "enabled": True,
            "targets": [
                {
                    "pack_identity": "local:addon-pack",
                    "component": {"type": "target_type"},
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "add", "path": "/extensions/from_low", "value": "low"}
                            ]
                        }
                    ]
                }
            ]
        }
        with open(addons_dir / "low.addon.json", 'w', encoding='utf-8') as f:
            json.dump(addon1, f)
        
        # Addon 2: 高優先度
        addon2 = {
            "addon_id": "addon_high",
            "version": "1.0.0",
            "priority": 150,
            "enabled": True,
            "targets": [
                {
                    "pack_identity": "local:addon-pack",
                    "component": {"type": "target_type", "id": "target_v1"},
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "add", "path": "/extensions/from_high", "value": "high"},
                                {"op": "add", "path": "/connectivity/accepts/-", "value": "type_b"}
                            ]
                        }
                    ]
                }
            ]
        }
        with open(addons_dir / "high.addon.json", 'w', encoding='utf-8') as f:
            json.dump(addon2, f)
        
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_addon_priority_order(self, pack_with_addon):
        """アドオンが優先度順に適用される"""
        registry = Registry(str(pack_with_addon))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        pack = registry.get_pack("addon_pack")
        component = registry.get_component("addon_pack", "target_type", "target_v1")
        
        addons = manager.get_addons_for_component(component, pack)
        
        assert len(addons) == 2
        assert addons[0].addon_id == "addon_low"  # priority 50
        assert addons[1].addon_id == "addon_high"  # priority 150
    
    def test_addon_application(self, pack_with_addon):
        """アドオンが正しく適用される"""
        registry = Registry(str(pack_with_addon))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        pack = registry.get_pack("addon_pack")
        component = registry.get_component("addon_pack", "target_type", "target_v1")
        
        patched, results = manager.apply_addons_to_manifest(component, pack)
        
        # 元のデータが保持されている
        assert patched['extensions']['original'] is True
        
        # アドオンによる追加
        assert patched['extensions']['from_low'] == "low"
        assert patched['extensions']['from_high'] == "high"
        assert "type_b" in patched['connectivity']['accepts']
    
    def test_path_restriction(self, pack_with_addon):
        """許可されていないパスへの変更は拒否される"""
        temp_dir = pack_with_addon
        addons_dir = temp_dir / "addon_pack" / "backend" / "addons"
        
        # 禁止パスへのパッチを追加
        forbidden_addon = {
            "addon_id": "forbidden",
            "version": "1.0.0",
            "priority": 200,
            "enabled": True,
            "targets": [
                {
                    "pack_identity": "local:addon-pack",
                    "component": {"type": "target_type"},
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "replace", "path": "/type", "value": "hacked"},
                                {"op": "add", "path": "/extensions/allowed", "value": True}
                            ]
                        }
                    ]
                }
            ]
        }
        with open(addons_dir / "forbidden.addon.json", 'w', encoding='utf-8') as f:
            json.dump(forbidden_addon, f)
        
        registry = Registry(str(temp_dir))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        pack = registry.get_pack("addon_pack")
        component = registry.get_component("addon_pack", "target_type", "target_v1")
        
        patched, results = manager.apply_addons_to_manifest(component, pack)
        
        # typeは変更されていない
        assert patched['type'] == "target_type"
        
        # 許可されたパスは変更されている
        assert patched['extensions']['allowed'] is True


class TestAddonDenyAll:
    """deny_allポリシーのテスト"""
    
    @pytest.fixture
    def deny_all_pack(self):
        """deny_all設定のPack"""
        temp_dir = tempfile.mkdtemp()
        pack_dir = Path(temp_dir) / "deny_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        ecosystem_data = {
            "pack_id": "deny_pack",
            "pack_identity": "local:deny-pack",
            "version": "1.0.0",
            "vocabulary": {"types": ["locked_type"]}
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # deny_all のComponent
        comp_dir = pack_dir / "components" / "locked"
        comp_dir.mkdir(parents=True)
        
        comp_data = {
            "type": "locked_type",
            "id": "locked_v1",
            "version": "1.0.0",
            "addon_policy": {
                "deny_all": True
            },
            "extensions": {}
        }
        with open(comp_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_data, f)
        
        # Addon
        addons_dir = pack_dir / "addons"
        addons_dir.mkdir()
        
        addon_data = {
            "addon_id": "blocked_addon",
            "version": "1.0.0",
            "targets": [
                {
                    "pack_identity": "local:deny-pack",
                    "component": {"type": "locked_type"},
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "add", "path": "/extensions/should_not_exist", "value": True}
                            ]
                        }
                    ]
                }
            ]
        }
        with open(addons_dir / "blocked.addon.json", 'w', encoding='utf-8') as f:
            json.dump(addon_data, f)
        
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_deny_all_blocks_addons(self, deny_all_pack):
        """deny_allがアドオンをブロックする"""
        registry = Registry(str(deny_all_pack))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        pack = registry.get_pack("deny_pack")
        component = registry.get_component("deny_pack", "locked_type", "locked_v1")
        
        patched, results = manager.apply_addons_to_manifest(component, pack)
        
        # アドオンによる変更がない
        assert 'should_not_exist' not in patched.get('extensions', {})
        
        # 結果にエラーが含まれる
        assert len(results) == 1
        assert not results[0].success
        assert "deny_all" in results[0].errors[0]


class TestFilePatch:
    """ファイルパッチのテスト"""
    
    @pytest.fixture
    def pack_with_file(self):
        """ファイルパッチ対象のPack"""
        temp_dir = tempfile.mkdtemp()
        pack_dir = Path(temp_dir) / "file_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        ecosystem_data = {
            "pack_id": "file_pack",
            "pack_identity": "local:file-pack",
            "version": "1.0.0",
            "vocabulary": {"types": ["file_type"]}
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # Component
        comp_dir = pack_dir / "components" / "with_file"
        comp_dir.mkdir(parents=True)
        
        comp_data = {
            "type": "file_type",
            "id": "file_v1",
            "version": "1.0.0",
            "addon_policy": {
                "allowed_manifest_paths": ["/extensions"],
                "editable_files": [
                    {
                        "path_glob": "config/*.json",
                        "allowed_json_pointer_prefixes": ["/settings", "/custom"]
                    }
                ]
            },
            "extensions": {}
        }
        with open(comp_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_data, f)
        
        # 対象ファイル
        config_dir = comp_dir / "config"
        config_dir.mkdir()
        
        config_data = {
            "settings": {
                "enabled": True
            },
            "readonly": {
                "value": 1
            }
        }
        with open(config_dir / "app.json", 'w', encoding='utf-8') as f:
            json.dump(config_data, f)
        
        # Addon
        addons_dir = pack_dir / "addons"
        addons_dir.mkdir()
        
        addon_data = {
            "addon_id": "file_patcher",
            "version": "1.0.0",
            "targets": [
                {
                    "pack_identity": "local:file-pack",
                    "component": {"type": "file_type"},
                    "apply": [
                        {
                            "kind": "file_json_patch",
                            "file": "config/app.json",
                            "patch": [
                                {"op": "add", "path": "/settings/new_option", "value": "added"},
                                {"op": "add", "path": "/readonly/hacked", "value": "should_fail"}
                            ]
                        }
                    ]
                }
            ]
        }
        with open(addons_dir / "file.addon.json", 'w', encoding='utf-8') as f:
            json.dump(addon_data, f)
        
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_file_patch_with_restriction(self, pack_with_file):
        """ファイルパッチがパス制限を尊重する"""
        registry = Registry(str(pack_with_file))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        pack = registry.get_pack("file_pack")
        component = registry.get_component("file_pack", "file_type", "file_v1")
        
        results = manager.apply_file_patches(component, pack)
        
        assert len(results) == 1
        file_path, patched_content, result = results[0]
        
        # 許可されたパスは変更されている
        assert patched_content['settings']['new_option'] == "added"
        
        # 許可されていないパスは変更されていない
        assert 'hacked' not in patched_content.get('readonly', {})


class TestAddonValidation:
    """アドオン検証のテスト"""
    
    def test_valid_addon(self):
        """有効なアドオンデータ"""
        manager = AddonManager()
        
        valid_data = {
            "addon_id": "valid",
            "version": "1.0.0",
            "targets": [
                {
                    "pack_identity": "local:test",
                    "apply": [
                        {"kind": "manifest_json_patch", "patch": []}
                    ]
                }
            ]
        }
        
        errors = manager.validate_addon_data(valid_data)
        assert errors == []
    
    def test_forbidden_operation(self):
        """禁止操作の検出"""
        manager = AddonManager()
        
        invalid_data = {
            "addon_id": "invalid",
            "version": "1.0.0",
            "targets": [
                {
                    "pack_identity": "local:test",
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "move", "from": "/a", "path": "/b"}
                            ]
                        }
                    ]
                }
            ]
        }
        
        errors = manager.validate_addon_data(invalid_data)
        assert len(errors) > 0
        assert any("move" in str(e).lower() or "禁止" in str(e) for e in errors)


class TestAddonEnableDisable:
    """アドオン有効化/無効化のテスト"""
    
    @pytest.fixture
    def pack_with_toggleable_addon(self):
        """有効/無効切替可能なアドオン付きPack"""
        temp_dir = tempfile.mkdtemp()
        pack_dir = Path(temp_dir) / "toggle_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        ecosystem_data = {
            "pack_id": "toggle_pack",
            "pack_identity": "local:toggle-pack",
            "version": "1.0.0",
            "vocabulary": {"types": ["toggle_type"]}
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # Component
        comp_dir = pack_dir / "components" / "toggle"
        comp_dir.mkdir(parents=True)
        
        comp_data = {
            "type": "toggle_type",
            "id": "toggle_v1",
            "version": "1.0.0",
            "addon_policy": {
                "allowed_manifest_paths": ["/extensions"]
            },
            "extensions": {}
        }
        with open(comp_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_data, f)
        
        # Addon
        addons_dir = pack_dir / "addons"
        addons_dir.mkdir()
        
        addon_data = {
            "addon_id": "toggleable",
            "version": "1.0.0",
            "enabled": True,
            "targets": [
                {
                    "pack_identity": "local:toggle-pack",
                    "component": {"type": "toggle_type"},
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "add", "path": "/extensions/toggled", "value": True}
                            ]
                        }
                    ]
                }
            ]
        }
        with open(addons_dir / "toggleable.addon.json", 'w', encoding='utf-8') as f:
            json.dump(addon_data, f)
        
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_disable_addon(self, pack_with_toggleable_addon):
        """アドオンを無効化できる"""
        registry = Registry(str(pack_with_toggleable_addon))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        pack = registry.get_pack("toggle_pack")
        component = registry.get_component("toggle_pack", "toggle_type", "toggle_v1")
        
        # 有効な状態でアドオンが適用される
        patched1, _ = manager.apply_addons_to_manifest(component, pack)
        assert patched1['extensions'].get('toggled') is True
        
        # 無効化
        manager.disable_addon("toggle_pack:toggleable")
        
        # 無効化後はアドオンが適用されない
        patched2, _ = manager.apply_addons_to_manifest(component, pack)
        assert patched2['extensions'].get('toggled') is None
    
    def test_enable_addon(self, pack_with_toggleable_addon):
        """アドオンを有効化できる"""
        registry = Registry(str(pack_with_toggleable_addon))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        
        # 無効化してから有効化
        manager.disable_addon("toggle_pack:toggleable")
        manager.enable_addon("toggle_pack:toggleable")
        
        addon = manager.get_addon("toggle_pack:toggleable")
        assert addon.enabled is True


class TestGetAllAddons:
    """全アドオン取得のテスト"""
    
    @pytest.fixture
    def pack_with_multiple_addons(self):
        """複数アドオン付きPack"""
        temp_dir = tempfile.mkdtemp()
        pack_dir = Path(temp_dir) / "multi_pack" / "backend"
        pack_dir.mkdir(parents=True)
        
        ecosystem_data = {
            "pack_id": "multi_pack",
            "pack_identity": "local:multi-pack",
            "version": "1.0.0",
            "vocabulary": {"types": ["multi_type"]}
        }
        with open(pack_dir / "ecosystem.json", 'w', encoding='utf-8') as f:
            json.dump(ecosystem_data, f)
        
        # Component
        comp_dir = pack_dir / "components" / "multi"
        comp_dir.mkdir(parents=True)
        
        comp_data = {
            "type": "multi_type",
            "id": "multi_v1",
            "version": "1.0.0"
        }
        with open(comp_dir / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(comp_data, f)
        
        # 複数のAddon
        addons_dir = pack_dir / "addons"
        addons_dir.mkdir()
        
        for i in range(3):
            addon_data = {
                "addon_id": f"addon_{i}",
                "version": "1.0.0",
                "targets": [
                    {
                        "pack_identity": "local:multi-pack",
                        "apply": [{"kind": "manifest_json_patch", "patch": []}]
                    }
                ]
            }
            with open(addons_dir / f"addon_{i}.addon.json", 'w', encoding='utf-8') as f:
                json.dump(addon_data, f)
        
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_get_all_addons(self, pack_with_multiple_addons):
        """全アドオンを取得できる"""
        registry = Registry(str(pack_with_multiple_addons))
        registry.load_all_packs()
        
        manager = get_addon_manager()
        all_addons = manager.get_all_addons()
        
        assert len(all_addons) == 3
        addon_ids = [a.addon_id for a in all_addons]
        assert "addon_0" in addon_ids
        assert "addon_1" in addon_ids
        assert "addon_2" in addon_ids


class TestCacheManagement:
    """キャッシュ管理のテスト"""
    
    def test_clear_cache(self):
        """キャッシュをクリアできる"""
        manager = AddonManager()
        
        # キャッシュに何かを追加
        manager._applied_cache["test_key"] = {"test": "data"}
        assert len(manager._applied_cache) == 1
        
        # クリア
        manager.clear_cache()
        assert len(manager._applied_cache) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
