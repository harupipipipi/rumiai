"""
test_phase_b2b.py — Phase B-2b: kernel ハンドラ schema テスト

_KERNEL_HANDLER_MANIFESTS の全エントリに input_schema / output_schema が
正しく追加されていることを検証する。
"""

import pytest
import sys
import os

# テスト対象のモジュールを import できるようにパスを調整
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core_runtime.kernel import _KERNEL_HANDLER_MANIFESTS


class TestPhaseB2bSchemaCompleteness:
    """全マニフェストに input_schema / output_schema が存在することを検証"""

    def test_all_manifests_have_input_schema(self):
        """全エントリに input_schema が存在すること"""
        missing = []
        for handler_key, manifest in _KERNEL_HANDLER_MANIFESTS.items():
            if "input_schema" not in manifest:
                missing.append(handler_key)
        assert missing == [], f"Missing input_schema for: {missing}"

    def test_all_manifests_have_output_schema(self):
        """全エントリに output_schema が存在すること"""
        missing = []
        for handler_key, manifest in _KERNEL_HANDLER_MANIFESTS.items():
            if "output_schema" not in manifest:
                missing.append(handler_key)
        assert missing == [], f"Missing output_schema for: {missing}"


class TestPhaseB2bSchemaValidity:
    """全 schema が有効な JSON Schema 形式であることを検証"""

    def test_input_schema_is_valid_json_schema(self):
        """全 input_schema が 'type' キーを持つ有効な JSON Schema 形式であること"""
        invalid = []
        for handler_key, manifest in _KERNEL_HANDLER_MANIFESTS.items():
            schema = manifest.get("input_schema")
            if schema is None:
                invalid.append((handler_key, "missing"))
                continue
            if not isinstance(schema, dict):
                invalid.append((handler_key, f"not a dict: {type(schema)}"))
                continue
            if "type" not in schema:
                invalid.append((handler_key, "missing 'type' key"))
        assert invalid == [], f"Invalid input_schema: {invalid}"

    def test_output_schema_is_valid_json_schema(self):
        """全 output_schema が 'type' キーを持つ有効な JSON Schema 形式であること"""
        invalid = []
        for handler_key, manifest in _KERNEL_HANDLER_MANIFESTS.items():
            schema = manifest.get("output_schema")
            if schema is None:
                invalid.append((handler_key, "missing"))
                continue
            if not isinstance(schema, dict):
                invalid.append((handler_key, f"not a dict: {type(schema)}"))
                continue
            if "type" not in schema:
                invalid.append((handler_key, "missing 'type' key"))
        assert invalid == [], f"Invalid output_schema: {invalid}"


class TestPhaseB2bSpecificSchemas:
    """個別ハンドラの schema が正しいことを検証"""

    def test_noop_handler_empty_input(self):
        """kernel:noop の input_schema.properties が空であること"""
        manifest = _KERNEL_HANDLER_MANIFESTS["kernel:noop"]
        schema = manifest["input_schema"]
        assert schema["type"] == "object"
        assert schema.get("properties", {}) == {}, \
            f"noop input_schema.properties should be empty, got: {schema.get('properties')}"

    def test_mounts_init_has_mounts_file_property(self):
        """kernel:mounts.init の input_schema に mounts_file プロパティがあること"""
        manifest = _KERNEL_HANDLER_MANIFESTS["kernel:mounts.init"]
        schema = manifest["input_schema"]
        assert "properties" in schema, "input_schema missing 'properties'"
        assert "mounts_file" in schema["properties"], \
            f"mounts_file not in properties: {list(schema['properties'].keys())}"

    def test_ctx_set_has_required_key(self):
        """kernel:ctx.set の input_schema の required に 'key' が含まれること"""
        manifest = _KERNEL_HANDLER_MANIFESTS["kernel:ctx.set"]
        schema = manifest["input_schema"]
        assert "required" in schema, "input_schema missing 'required'"
        assert "key" in schema["required"], \
            f"'key' not in required: {schema['required']}"

    def test_network_grant_has_pack_id_required(self):
        """kernel:network.grant の input_schema の required に 'pack_id' が含まれること"""
        manifest = _KERNEL_HANDLER_MANIFESTS["kernel:network.grant"]
        schema = manifest["input_schema"]
        assert "required" in schema, "input_schema missing 'required'"
        assert "pack_id" in schema["required"], \
            f"'pack_id' not in required: {schema['required']}"
