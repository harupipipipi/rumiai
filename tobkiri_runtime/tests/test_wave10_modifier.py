"""
test_wave10_modifier.py - Wave 10-B: flow_modifier YAML safety hardening tests
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from core_runtime.flow_modifier import FlowModifierLoader


# ======================================================================
# File size limit
# ======================================================================

class TestFileSize:
    """File size limit checks."""

    def test_file_exceeding_size_limit_is_rejected(self, tmp_path):
        big_file = tmp_path / "big.modifier.yaml"
        big_file.write_text("x" * (2 * 1024 * 1024))

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(big_file)

        assert not result.success
        assert any("too large" in e for e in result.errors)

    def test_file_within_size_limit_is_accepted(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            modifier_id: "test_mod"
            target_flow_id: "main_flow"
            phase: "init"
            priority: 100
            action: "append"
            step:
              id: "injected_step"
              type: "handler"
        """)
        f = tmp_path / "ok.modifier.yaml"
        f.write_text(yaml_content)

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert result.success
        assert result.modifier_id == "test_mod"

    def test_custom_size_limit_via_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_MAX_MODIFIER_FILE_BYTES", "100")
        yaml_content = textwrap.dedent("""\
            modifier_id: "test_mod"
            target_flow_id: "main_flow"
            phase: "init"
            priority: 100
            action: "append"
            step:
              id: "injected_step"
              type: "handler"
        """)
        f = tmp_path / "medium.modifier.yaml"
        f.write_text(yaml_content)
        assert f.stat().st_size > 100

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert not result.success
        assert any("too large" in e for e in result.errors)


# ======================================================================
# YAML complexity (depth / node count)
# ======================================================================

class TestYamlComplexity:
    """Parsed YAML data structure size checks."""

    def test_excessive_depth_is_rejected(self, tmp_path):
        nested = "value"
        for i in range(25):
            nested = {f"level_{i}": nested}
        f = tmp_path / "deep.modifier.yaml"
        f.write_text(yaml.dump(nested))

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert not result.success
        assert any("depth exceeds" in e for e in result.errors)

    def test_excessive_nodes_is_rejected(self, tmp_path):
        many_keys = {f"key_{i}": f"val_{i}" for i in range(10001)}
        f = tmp_path / "wide.modifier.yaml"
        f.write_text(yaml.dump(many_keys))

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert not result.success
        assert any("node count exceeds" in e for e in result.errors)

    def test_normal_complexity_passes(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            modifier_id: "test_mod"
            target_flow_id: "main_flow"
            phase: "init"
            priority: 100
            action: "append"
            step:
              id: "injected_step"
              type: "handler"
              input:
                a: 1
                b: 2
        """)
        f = tmp_path / "normal.modifier.yaml"
        f.write_text(yaml_content)

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert result.success

    def test_check_yaml_complexity_direct(self):
        # Normal case
        ok, err = FlowModifierLoader._check_yaml_complexity(
            {"a": 1}, max_depth=5, max_nodes=100,
        )
        assert ok
        assert err is None

        # Depth exceeded
        nested = "x"
        for _ in range(10):
            nested = {"k": nested}
        ok, err = FlowModifierLoader._check_yaml_complexity(
            nested, max_depth=5, max_nodes=10000,
        )
        assert not ok
        assert "depth" in err

        # Node count exceeded
        wide = {f"k{i}": i for i in range(20)}
        ok, err = FlowModifierLoader._check_yaml_complexity(
            wide, max_depth=100, max_nodes=10,
        )
        assert not ok
        assert "node count" in err


# ======================================================================
# YAML 1.1 implicit type conversion (modifier_id / target_flow_id)
# ======================================================================

class TestImplicitTypeConversion:
    """Guard against YAML 1.1 implicit type conversion for IDs."""

    @staticmethod
    def _write_yaml(tmp_path: Path, data: dict) -> Path:
        f = tmp_path / "typed.modifier.yaml"
        f.write_text(yaml.dump(data, default_flow_style=False))
        return f

    def test_bool_modifier_id_converted_with_warning(self, tmp_path):
        data = {
            "modifier_id": True,
            "target_flow_id": "main_flow",
            "phase": "init",
            "priority": 100,
            "action": "append",
            "step": {"id": "s1", "type": "handler"},
        }
        f = self._write_yaml(tmp_path, data)

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert result.success
        assert result.modifier_id == "True"
        assert any("modifier_id" in w and "bool" in w for w in result.warnings)

    def test_int_target_flow_id_converted_with_warning(self, tmp_path):
        data = {
            "modifier_id": "valid_mod",
            "target_flow_id": 42,
            "phase": "init",
            "priority": 100,
            "action": "append",
            "step": {"id": "s1", "type": "handler"},
        }
        f = self._write_yaml(tmp_path, data)

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert result.success
        assert result.modifier_def.target_flow_id == "42"
        assert any("target_flow_id" in w and "int" in w for w in result.warnings)

    def test_string_ids_no_warning(self, tmp_path):
        data = {
            "modifier_id": "normal_mod",
            "target_flow_id": "normal_flow",
            "phase": "init",
            "priority": 100,
            "action": "append",
            "step": {"id": "s1", "type": "handler"},
        }
        f = self._write_yaml(tmp_path, data)

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert result.success
        assert len(result.warnings) == 0

    def test_false_modifier_id_converted(self, tmp_path):
        data = {
            "modifier_id": False,
            "target_flow_id": "main_flow",
            "phase": "init",
            "priority": 100,
            "action": "append",
            "step": {"id": "s1", "type": "handler"},
        }
        f = self._write_yaml(tmp_path, data)

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert result.success
        assert result.modifier_id == "False"
        assert any("modifier_id" in w for w in result.warnings)


# ======================================================================
# Normal files are not affected
# ======================================================================

class TestNormalFileNotAffected:
    """Ensure existing valid modifiers still load correctly."""

    def test_full_featured_modifier_loads_correctly(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            modifier_id: "wave9_mod"
            target_flow_id: "target_flow"
            phase: "process"
            priority: 50
            action: "inject_before"
            target_step_id: "step_a"
            step:
              id: "new_step"
              type: "handler"
              input:
                key: "value"
            requires:
              interfaces:
                - "some_interface"
              capabilities:
                - "some_cap"
            conflicts_with:
              - "other_mod"
            compatible_with:
              - "friend_mod"
        """)
        f = tmp_path / "full.modifier.yaml"
        f.write_text(yaml_content)

        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)

        assert result.success
        assert result.modifier_id == "wave9_mod"
        mdef = result.modifier_def
        assert mdef.target_flow_id == "target_flow"
        assert mdef.conflicts_with == ["other_mod"]
        assert mdef.compatible_with == ["friend_mod"]
        assert mdef.priority == 50
        assert mdef.action == "inject_before"
        assert len(result.warnings) == 0
        assert len(result.errors) == 0
