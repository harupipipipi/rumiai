# tests/test_ecosystem_phase2.py
"""
Phase 2 スキーマ定義のテスト
"""

import json
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend_core.ecosystem.spec.schema.validator import (
    validate_ecosystem,
    validate_component_manifest,
    validate_addon,
    validate_json_patch_operations,
    SchemaValidationError,
    get_schema,
    list_available_schemas
)


class TestEcosystemSchema:
    """ecosystem.schema.jsonのテスト"""
    
    def test_valid_minimal(self):
        """最小限の有効なecosystem定義"""
        data = {
            "pack_id": "default",
            "pack_identity": "github:haru/default-pack",
            "version": "1.0.0",
            "vocabulary": {
                "types": ["chats", "tool_pack"]
            }
        }
        errors = validate_ecosystem(data, raise_on_error=False)
        assert errors == []
    
    def test_valid_full(self):
        """完全なecosystem定義"""
        data = {
            "pack_id": "default",
            "pack_identity": "github:haru/default-pack",
            "version": "1.0.0",
            "pack_uuid": "a3e9f8c2-7b4d-5e1a-9c6f-2d8b4a7e3f1c",
            "display_name": "Default Pack",
            "description": "The default ecosystem pack",
            "author": {
                "name": "Haru",
                "email": "haru@example.com"
            },
            "license": "MIT",
            "vocabulary": {
                "types": ["chats", "tool_pack", "prompt_pack"]
            },
            "metadata": {
                "custom_field": "value"
            }
        }
        errors = validate_ecosystem(data, raise_on_error=False)
        assert errors == []
    
    def test_missing_required_fields(self):
        """必須フィールドが欠けている場合"""
        data = {
            "pack_id": "default"
        }
        errors = validate_ecosystem(data, raise_on_error=False)
        assert len(errors) > 0
    
    def test_invalid_pack_id_pattern(self):
        """pack_idが無効なパターン"""
        data = {
            "pack_id": "Invalid-Pack",
            "pack_identity": "github:haru/default-pack",
            "version": "1.0.0",
            "vocabulary": {"types": ["chats"]}
        }
        errors = validate_ecosystem(data, raise_on_error=False)
        assert len(errors) > 0
    
    def test_invalid_version_format(self):
        """バージョン形式が無効"""
        data = {
            "pack_id": "default",
            "pack_identity": "github:haru/default-pack",
            "version": "1.0",
            "vocabulary": {"types": ["chats"]}
        }
        errors = validate_ecosystem(data, raise_on_error=False)
        assert len(errors) > 0
    
    def test_raises_on_error(self):
        """raise_on_error=Trueで例外が発生"""
        data = {"pack_id": "default"}
        with pytest.raises(SchemaValidationError):
            validate_ecosystem(data, raise_on_error=True)


class TestComponentManifestSchema:
    """component_manifest.schema.jsonのテスト"""
    
    def test_valid_minimal(self):
        """最小限の有効なComponent manifest"""
        data = {
            "type": "chats",
            "id": "chats_v1",
            "version": "1.0.0"
        }
        errors = validate_component_manifest(data, raise_on_error=False)
        assert errors == []
    
    def test_valid_full(self):
        """完全なComponent manifest"""
        data = {
            "type": "chats",
            "id": "chats_v1",
            "version": "1.0.0",
            "display_name": "Chat Manager",
            "description": "Manages chat histories",
            "entry": {
                "backend": "python:chat_manager.py",
                "frontend": None
            },
            "connectivity": {
                "accepts": ["tool_pack", "prompt_pack"],
                "provides": ["agent_runtime"],
                "requires": []
            },
            "storage": {
                "uses_mounts": ["data.chats"],
                "layout": "component_defined"
            },
            "addon_policy": {
                "allowed_manifest_paths": ["/connectivity/accepts", "/extensions"],
                "editable_files": [
                    {
                        "path_glob": "**/*.json",
                        "allowed_json_pointer_prefixes": ["/extensions"]
                    }
                ]
            },
            "extensions": {}
        }
        errors = validate_component_manifest(data, raise_on_error=False)
        assert errors == []
    
    def test_invalid_type_pattern(self):
        """typeが無効なパターン"""
        data = {
            "type": "Chats",
            "id": "chats_v1",
            "version": "1.0.0"
        }
        errors = validate_component_manifest(data, raise_on_error=False)
        assert len(errors) > 0


class TestAddonSchema:
    """addon.schema.jsonのテスト"""
    
    def test_valid_minimal(self):
        """最小限の有効なAddon定義"""
        data = {
            "addon_id": "my_addon",
            "version": "1.0.0",
            "targets": [
                {
                    "pack_identity": "github:haru/default-pack",
                    "component": {
                        "type": "chats",
                        "id": "chats_v1"
                    },
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "add", "path": "/extensions/my_field", "value": "test"}
                            ]
                        }
                    ]
                }
            ]
        }
        errors = validate_addon(data, raise_on_error=False)
        assert errors == []
    
    def test_valid_file_patch(self):
        """ファイルパッチのAddon"""
        data = {
            "addon_id": "add_benchmark",
            "version": "1.0.0",
            "targets": [
                {
                    "pack_identity": "github:haru/default-pack",
                    "component": {
                        "type": "ai_client_provider",
                        "id": "gemini"
                    },
                    "apply": [
                        {
                            "kind": "file_json_patch",
                            "file": "ai_profile/gemini-2.5-flash.json",
                            "patch": [
                                {"op": "add", "path": "/benchmarks", "value": {"mmlu": 0.78}}
                            ]
                        }
                    ]
                }
            ]
        }
        errors = validate_addon(data, raise_on_error=False)
        assert errors == []
    
    def test_with_uuid_targeting(self):
        """UUIDでターゲット指定"""
        data = {
            "addon_id": "uuid_target",
            "version": "1.0.0",
            "targets": [
                {
                    "pack_uuid": "a3e9f8c2-7b4d-5e1a-9c6f-2d8b4a7e3f1c",
                    "component": {
                        "component_uuid": "b4f0a9d3-8c5e-6f2b-0d7a-3e9c5b8a6d4e"
                    },
                    "apply": [
                        {
                            "kind": "manifest_json_patch",
                            "patch": [
                                {"op": "add", "path": "/extensions/test", "value": 1}
                            ]
                        }
                    ]
                }
            ]
        }
        errors = validate_addon(data, raise_on_error=False)
        assert errors == []


class TestJsonPatchValidation:
    """JSON Patch操作の検証テスト"""
    
    def test_valid_operations(self):
        """有効な操作"""
        ops = [
            {"op": "add", "path": "/foo", "value": "bar"},
            {"op": "remove", "path": "/baz"},
            {"op": "replace", "path": "/qux", "value": 123},
            {"op": "test", "path": "/check", "value": True}
        ]
        errors = validate_json_patch_operations(ops)
        assert errors == []
    
    def test_forbidden_move(self):
        """move操作は禁止"""
        ops = [{"op": "move", "from": "/a", "path": "/b"}]
        errors = validate_json_patch_operations(ops)
        assert any("禁止" in e for e in errors)
    
    def test_forbidden_copy(self):
        """copy操作は禁止"""
        ops = [{"op": "copy", "from": "/a", "path": "/b"}]
        errors = validate_json_patch_operations(ops)
        assert any("禁止" in e for e in errors)
    
    def test_missing_value_for_add(self):
        """addにvalueがない"""
        ops = [{"op": "add", "path": "/foo"}]
        errors = validate_json_patch_operations(ops)
        assert len(errors) > 0


class TestSchemaUtilities:
    """ユーティリティ関数のテスト"""
    
    def test_get_schema(self):
        """スキーマ取得"""
        schema = get_schema("ecosystem")
        assert "$schema" in schema
        assert "properties" in schema
    
    def test_list_available_schemas(self):
        """利用可能なスキーマ一覧"""
        schemas = list_available_schemas()
        assert "ecosystem" in schemas
        assert "component_manifest" in schemas
        assert "addon" in schemas


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
