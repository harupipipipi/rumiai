"""
test_flow_modifier_regression.py - flow_modifier.py regression tests (Wave 12 T-044)

Regression prevention for:
  - Wave 9: Conflict detection edge cases NOT covered by test_wave9.py
  - Wave 10: YAML safety edge cases NOT covered by test_wave10_modifier.py
  - Wave 11: Wildcard control edge cases NOT covered by test_wave11_wildcard.py
  - Combined scenarios: conflicts + depends_on + wildcard
  - Edge cases: empty lists, None, wrong types, large modifier sets

Avoids duplication with:
  - test_wave9.py (basic conflict detection, conflicts_with parsing, prefix warning)
  - test_wave10_modifier.py (file size, YAML complexity, implicit type conversion)
  - test_wave11_wildcard.py (basic wildcard skip/allow, _is_wildcard_modifier_allowed)
"""
from __future__ import annotations

import copy
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core_runtime.flow_loader import FlowDefinition, FlowStep
from core_runtime.flow_modifier import (
    FlowModifierApplier,
    FlowModifierDef,
    FlowModifierLoader,
    ModifierApplyResult,
    ModifierRequires,
)


# ======================================================================
# Helpers
# ======================================================================

def _step(sid: str, phase: str = "main", priority: int = 100,
          depends_on=None) -> FlowStep:
    """Create a minimal FlowStep."""
    return FlowStep(
        id=sid, phase=phase, priority=priority,
        type="handler", when=None, input=None, output=None,
        raw={"id": sid, "type": "handler"},
        depends_on=depends_on,
    )


def _flow(flow_id: str = "regression.flow",
          phases=None, steps=None) -> FlowDefinition:
    """Create a minimal FlowDefinition."""
    phases = phases or ["main"]
    steps = steps or [
        _step("s1"), _step("s2"), _step("s3"),
    ]
    return FlowDefinition(
        flow_id=flow_id, inputs={}, outputs={},
        phases=phases, defaults={"fail_soft": True},
        steps=steps, source_type="pack", source_pack_id="test",
    )


def _mod(mid: str, action: str = "inject_after",
         target_step_id: str = "s1", phase: str = "main",
         priority: int = 100,
         conflicts_with=None, compatible_with=None,
         target_flow_id: str = "regression.flow") -> FlowModifierDef:
    """Create a minimal FlowModifierDef."""
    step = None
    if action != "remove":
        step = {"id": f"injected_{mid}", "type": "handler"}
    return FlowModifierDef(
        modifier_id=mid, target_flow_id=target_flow_id,
        phase=phase, priority=priority, action=action,
        target_step_id=target_step_id, step=step,
        requires=ModifierRequires(),
        conflicts_with=conflicts_with,
        compatible_with=compatible_with,
    )


# ======================================================================
# Regression: Conflict detection edge cases (Wave 9)
# (Different from test_wave9.py which tests basic cases)
# ======================================================================

class TestConflictDetectionRegression:
    """Edge cases for modifier conflict detection not in test_wave9.py."""

    def test_three_modifiers_same_target(self):
        """Three modifiers on same target -> conflict warning."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m1", "inject_after", "s1"),
            _mod("m2", "inject_before", "s1"),
            _mod("m3", "replace", "s1"),
        ]
        with patch("core_runtime.flow_modifier.logger") as mock_logger:
            applier.apply_modifiers(flow, modifiers)
            conflict_calls = [
                c for c in mock_logger.warning.call_args_list
                if "CONFLICT" in str(c)
            ]
            assert len(conflict_calls) >= 1

    def test_conflicts_with_bidirectional(self):
        """Both modifiers declare conflicts_with each other -> two warnings."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m1", "inject_after", "s1", conflicts_with=["m2"]),
            _mod("m2", "inject_after", "s2", conflicts_with=["m1"]),
        ]
        with patch("core_runtime.flow_modifier.logger") as mock_logger:
            applier.apply_modifiers(flow, modifiers)
            declared_calls = [
                c for c in mock_logger.warning.call_args_list
                if "declared" in str(c).lower()
            ]
            assert len(declared_calls) >= 2

    def test_compatible_with_self_no_warning(self):
        """compatible_with referencing self -> no warning."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m1", "inject_after", "s1", compatible_with=["m1"]),
        ]
        with patch("core_runtime.flow_modifier.logger") as mock_logger:
            applier.apply_modifiers(flow, modifiers)
            compat_calls = [
                c for c in mock_logger.warning.call_args_list
                if "compatibility" in str(c).lower()
            ]
            assert len(compat_calls) == 0

    def test_conflicts_with_empty_list(self):
        """conflicts_with=[] -> no declared conflicts."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m1", "inject_after", "s1", conflicts_with=[]),
        ]
        with patch("core_runtime.flow_modifier.logger") as mock_logger:
            applier.apply_modifiers(flow, modifiers)
            declared_calls = [
                c for c in mock_logger.warning.call_args_list
                if "declared" in str(c).lower()
            ]
            assert len(declared_calls) == 0

    def test_append_does_not_trigger_target_conflict(self):
        """append actions have no target_step_id -> no same-target conflict."""
        applier = FlowModifierApplier()
        flow = _flow()
        m1 = _mod("m1", "append", target_step_id=None, phase="main")
        m2 = _mod("m2", "append", target_step_id=None, phase="main")
        modifiers = [m1, m2]
        with patch("core_runtime.flow_modifier.logger") as mock_logger:
            applier.apply_modifiers(flow, modifiers)
            conflict_calls = [
                c for c in mock_logger.warning.call_args_list
                if "CONFLICT" in str(c) and "severe" in str(c).lower()
            ]
            assert len(conflict_calls) == 0


# ======================================================================
# Regression: Modifier application correctness
# ======================================================================

class TestModifierApplicationRegression:
    """Regression tests for modifier application correctness."""

    def test_inject_before_preserves_order(self):
        """Multiple inject_before on same target preserve priority order."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m_low", "inject_before", "s2", priority=200),
            _mod("m_high", "inject_before", "s2", priority=50),
        ]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        ids = [s.id for s in new_flow.steps]
        idx_high = ids.index("injected_m_high")
        idx_low = ids.index("injected_m_low")
        idx_s2 = ids.index("s2")
        # Both before s2; m_high (priority=50) before m_low (priority=200)
        assert idx_high < idx_low < idx_s2

    def test_inject_after_preserves_order(self):
        """Multiple inject_after on same target preserve priority order."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m_first", "inject_after", "s1", priority=10),
            _mod("m_second", "inject_after", "s1", priority=20),
        ]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        ids = [s.id for s in new_flow.steps]
        idx_s1 = ids.index("s1")
        idx_first = ids.index("injected_m_first")
        idx_second = ids.index("injected_m_second")
        assert idx_s1 < idx_first < idx_second

    def test_remove_then_inject_before_same_target(self):
        """remove + inject_before on same target: remove runs first (other_modifiers)."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m_remove", "remove", "s2"),
            _mod("m_inject", "inject_before", "s2"),
        ]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        ids = [s.id for s in new_flow.steps]
        # s2 was removed first, so inject_before can't find target
        assert "s2" not in ids
        # m_inject should be skipped (target not found)
        inject_result = [r for r in results if r.modifier_id == "m_inject"][0]
        assert inject_result.skipped_reason is not None

    def test_replace_changes_step_id(self):
        """replace swaps step content."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [_mod("m_rep", "replace", "s1")]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        ids = [s.id for s in new_flow.steps]
        assert "s1" not in ids
        assert "injected_m_rep" in ids

    def test_phase_not_found_skips(self):
        """Modifier targeting non-existent phase is skipped."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [_mod("m_bad", "inject_after", "s1", phase="nonexistent")]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        assert results[0].skipped_reason is not None
        assert "phase" in results[0].skipped_reason

    def test_target_step_not_found_skips(self):
        """inject_after targeting non-existent step is skipped."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [_mod("m_missing", "inject_after", "nonexistent_step")]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        assert results[0].skipped_reason is not None
        assert "not_found" in results[0].skipped_reason

    def test_requires_not_satisfied_skips(self):
        """Modifier with unmet requires is skipped."""
        applier = FlowModifierApplier()
        flow = _flow()
        m = _mod("m_req", "inject_after", "s1")
        m.requires = ModifierRequires(interfaces=["nonexistent.iface"])
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, [m])

        assert results[0].skipped_reason is not None
        assert "requires" in results[0].skipped_reason


# ======================================================================
# Regression: YAML safety edge cases (Wave 10)
# (Different from test_wave10_modifier.py)
# ======================================================================

class TestYAMLSafetyRegression:
    """YAML safety regression tests not covered by test_wave10_modifier.py."""

    def test_modifier_id_none_rejected(self, tmp_path):
        """modifier_id: null (YAML None) -> error."""
        content = textwrap.dedent("""\
            modifier_id: null
            target_flow_id: "flow"
            phase: "main"
            action: "append"
            step:
              id: "s1"
              type: "handler"
        """)
        f = tmp_path / "null_id.modifier.yaml"
        f.write_text(content)
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert not result.success

    def test_target_flow_id_none_rejected(self, tmp_path):
        """target_flow_id: null -> error."""
        content = textwrap.dedent("""\
            modifier_id: "valid"
            target_flow_id: null
            phase: "main"
            action: "append"
            step:
              id: "s1"
              type: "handler"
        """)
        f = tmp_path / "null_target.modifier.yaml"
        f.write_text(content)
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert not result.success

    def test_step_missing_id_rejected(self, tmp_path):
        """step without id -> error."""
        content = textwrap.dedent("""\
            modifier_id: "mod1"
            target_flow_id: "flow"
            phase: "main"
            action: "append"
            step:
              type: "handler"
        """)
        f = tmp_path / "no_step_id.modifier.yaml"
        f.write_text(content)
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert not result.success
        assert any("step.id" in e for e in result.errors)

    def test_step_missing_type_rejected(self, tmp_path):
        """step without type -> error."""
        content = textwrap.dedent("""\
            modifier_id: "mod1"
            target_flow_id: "flow"
            phase: "main"
            action: "append"
            step:
              id: "s1"
        """)
        f = tmp_path / "no_step_type.modifier.yaml"
        f.write_text(content)
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert not result.success
        assert any("step.type" in e for e in result.errors)

    def test_invalid_action_rejected(self, tmp_path):
        """Unsupported action -> error."""
        content = textwrap.dedent("""\
            modifier_id: "mod1"
            target_flow_id: "flow"
            phase: "main"
            action: "invalid_action"
            step:
              id: "s1"
              type: "handler"
        """)
        f = tmp_path / "bad_action.modifier.yaml"
        f.write_text(content)
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert not result.success
        assert any("action" in e.lower() for e in result.errors)

    def test_non_dict_yaml_rejected(self, tmp_path):
        """YAML that parses to list -> error."""
        f = tmp_path / "list.modifier.yaml"
        f.write_text("- item1\n- item2\n")
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert not result.success

    def test_file_not_found(self, tmp_path):
        """Nonexistent file -> error."""
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(tmp_path / "missing.modifier.yaml")
        assert not result.success
        assert any("not found" in e.lower() for e in result.errors)

    def test_invalid_priority_uses_default(self, tmp_path):
        """Non-numeric priority -> warning + default 100."""
        content = textwrap.dedent("""\
            modifier_id: "mod1"
            target_flow_id: "flow"
            phase: "main"
            priority: "high"
            action: "append"
            step:
              id: "s1"
              type: "handler"
        """)
        f = tmp_path / "bad_priority.modifier.yaml"
        f.write_text(content)
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert result.success
        assert result.modifier_def.priority == 100
        assert len(result.warnings) >= 1

    def test_check_yaml_complexity_nested_list(self):
        """Deeply nested lists exceed depth limit."""
        data = "leaf"
        for _ in range(25):
            data = [data]
        ok, err = FlowModifierLoader._check_yaml_complexity(data, max_depth=20, max_nodes=10000)
        assert not ok
        assert "depth" in err


# ======================================================================
# Regression: Wildcard modifier edge cases (Wave 11)
# (Different from test_wave11_wildcard.py)
# ======================================================================

class TestWildcardRegression:
    """Wildcard modifier regression tests not in test_wave11_wildcard.py."""

    def test_wildcard_cache_cleared_on_load_all(self):
        """load_all_modifiers clears wildcard flag cache."""
        loader = FlowModifierLoader()
        loader._wildcard_flags["old_pack"] = True
        # load_all_modifiers touches filesystem, so mock discovery
        with patch.object(loader, '_load_shared_modifiers'), \
             patch.object(loader, '_load_pack_modifiers_via_discovery'), \
             patch.object(loader, '_is_local_pack_mode_enabled', return_value=False):
            loader.load_all_modifiers()
        assert "old_pack" not in loader._wildcard_flags

    def test_fnmatch_pattern_target_flow_id(self, tmp_path):
        """target_flow_id with glob pattern matches specific flow."""
        content = textwrap.dedent("""\
            modifier_id: "pattern_mod"
            target_flow_id: "mypack.*"
            phase: "main"
            action: "append"
            step:
              id: "injected"
              type: "handler"
        """)
        f = tmp_path / "pattern.modifier.yaml"
        f.write_text(content)
        loader = FlowModifierLoader()
        result = loader.load_modifier_file(f)
        assert result.success

        # Register the modifier
        loader._loaded_modifiers[result.modifier_id] = result.modifier_def

        # Query for matching flow
        matches = loader.get_modifiers_for_flow("mypack.subflow")
        assert len(matches) == 1
        assert matches[0].modifier_id == "pattern_mod"

        # Non-matching flow
        no_match = loader.get_modifiers_for_flow("otherpack.subflow")
        assert len(no_match) == 0

    def test_get_modifiers_sorted_by_phase_priority_id(self, tmp_path):
        """get_modifiers_for_flow returns modifiers sorted correctly."""
        loader = FlowModifierLoader()
        loader._loaded_modifiers = {
            "m_z": FlowModifierDef(
                modifier_id="m_z", target_flow_id="test", phase="main",
                priority=200, action="append", target_step_id=None,
                step={"id": "z", "type": "handler"}, requires=ModifierRequires(),
            ),
            "m_a": FlowModifierDef(
                modifier_id="m_a", target_flow_id="test", phase="main",
                priority=100, action="append", target_step_id=None,
                step={"id": "a", "type": "handler"}, requires=ModifierRequires(),
            ),
            "m_b": FlowModifierDef(
                modifier_id="m_b", target_flow_id="test", phase="init",
                priority=50, action="append", target_step_id=None,
                step={"id": "b", "type": "handler"}, requires=ModifierRequires(),
            ),
        }
        mods = loader.get_modifiers_for_flow("test")
        ids = [m.modifier_id for m in mods]
        # init phase first, then main; within main: priority 100 < 200
        assert ids == ["m_b", "m_a", "m_z"]


# ======================================================================
# Regression: Combined scenarios
# ======================================================================

class TestCombinedScenarios:
    """Combined modifier scenarios for regression prevention."""

    def test_multiple_phases_multiple_actions(self):
        """Modifiers across multiple phases with different actions."""
        applier = FlowModifierApplier()
        flow = _flow(
            phases=["init", "main", "cleanup"],
            steps=[
                _step("init_s1", "init"),
                _step("main_s1", "main"),
                _step("main_s2", "main"),
                _step("cleanup_s1", "cleanup"),
            ],
        )
        modifiers = [
            _mod("m_init_append", "append", target_step_id=None, phase="init"),
            _mod("m_main_inject", "inject_after", "main_s1", phase="main"),
            _mod("m_cleanup_remove", "remove", "cleanup_s1", phase="cleanup"),
        ]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        ids = [s.id for s in new_flow.steps]
        assert "injected_m_init_append" in ids
        assert "injected_m_main_inject" in ids
        assert "cleanup_s1" not in ids
        assert all(r.success or r.skipped_reason is None for r in results
                   if r.modifier_id != "m_cleanup_remove")

    def test_large_modifier_set(self):
        """Apply 50 modifiers without error."""
        applier = FlowModifierApplier()
        flow = _flow(steps=[_step("s1"), _step("s2")])
        modifiers = [
            _mod(f"m_{i}", "append", target_step_id=None, phase="main", priority=i)
            for i in range(50)
        ]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        assert len(new_flow.steps) == 2 + 50
        assert all(r.success for r in results)

    def test_conflicts_with_and_requires_combined(self):
        """conflicts_with warns even when all modifiers pass requires."""
        applier = FlowModifierApplier()
        flow = _flow()
        modifiers = [
            _mod("m_a", "inject_after", "s1", conflicts_with=["m_b"]),
            _mod("m_b", "inject_after", "s2"),
        ]
        with patch("core_runtime.flow_modifier.logger") as mock_logger:
            new_flow, results = applier.apply_modifiers(flow, modifiers)

        # Both should succeed (conflicts_with is warning-only)
        assert all(r.success for r in results)
        declared = [c for c in mock_logger.warning.call_args_list
                    if "declared" in str(c).lower()]
        assert len(declared) >= 1

    def test_empty_modifiers_list(self):
        """apply_modifiers with empty list returns original flow unchanged."""
        applier = FlowModifierApplier()
        flow = _flow()
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, results = applier.apply_modifiers(flow, [])
        assert [s.id for s in new_flow.steps] == ["s1", "s2", "s3"]
        assert results == []

    def test_original_flow_not_mutated(self):
        """apply_modifiers does not mutate the original FlowDefinition."""
        applier = FlowModifierApplier()
        flow = _flow()
        original_ids = [s.id for s in flow.steps]
        modifiers = [
            _mod("m_add", "inject_after", "s1"),
            _mod("m_del", "remove", "s3"),
        ]
        with patch("core_runtime.flow_modifier.logger"):
            new_flow, _ = applier.apply_modifiers(flow, modifiers)

        # Original unchanged
        assert [s.id for s in flow.steps] == original_ids
        # New flow is different
        assert [s.id for s in new_flow.steps] != original_ids


# ======================================================================
# Regression: FlowModifierDef serialization
# ======================================================================

class TestFlowModifierDefSerialization:
    """to_dict regression tests for FlowModifierDef."""

    def test_to_dict_includes_all_fields(self):
        m = _mod("test_mod", conflicts_with=["other"], compatible_with=["friend"])
        d = m.to_dict()
        assert d["modifier_id"] == "test_mod"
        assert d["target_flow_id"] == "regression.flow"
        assert d["phase"] == "main"
        assert d["priority"] == 100
        assert d["action"] == "inject_after"
        assert d["conflicts_with"] == ["other"]
        assert d["compatible_with"] == ["friend"]
        assert d["resolve_target"] is False

    def test_to_dict_none_conflicts(self):
        m = _mod("test_mod")
        d = m.to_dict()
        assert d["conflicts_with"] is None
        assert d["compatible_with"] is None

    def test_to_dict_source_file_none(self):
        m = _mod("test_mod")
        d = m.to_dict()
        assert d["_source_file"] is None

    def test_to_dict_source_pack_id(self):
        m = _mod("test_mod")
        m.source_pack_id = "my_pack"
        d = m.to_dict()
        assert d["_source_pack_id"] == "my_pack"
