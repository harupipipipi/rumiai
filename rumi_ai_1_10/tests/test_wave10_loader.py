"""
test_wave10_loader.py - Wave 10-A flow_loader テスト

テスト対象:
- depends_on パース（正常、非list、非string要素）
- _sort_steps トポロジカルソート（正常な依存、循環依存フォールバック）
- 存在しない step_id への依存で警告
- cross-phase depends_on で警告
- ファイルサイズ上限テスト
- データ構造サイズチェックテスト（_check_yaml_complexity）
- 型変換警告テスト（bool id, bool phase, float flow_id）
- depends_on なしの既存形式が正常動作すること（後方互換）
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Optional

import pytest
import yaml

from core_runtime.flow_loader import (
    FlowLoader,
    FlowStep,
    _check_yaml_complexity,
)


# ======================================================================
# ヘルパー
# ======================================================================

def _write_flow(
    tmp_path: Path,
    flow_id: str,
    steps: list,
    phases: Optional[list] = None,
) -> Path:
    """テスト用 .flow.yaml を書き出して Path を返す"""
    if phases is None:
        phases = ["init"]
    data = {
        "flow_id": flow_id,
        "inputs": {},
        "outputs": {},
        "phases": phases,
        "steps": steps,
    }
    p = tmp_path / f"{flow_id}.flow.yaml"
    p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return p


def _make_step(
    step_id: str,
    phase: str = "init",
    priority: int = 100,
    step_type: str = "action",
    depends_on=None,
    **extra,
) -> dict:
    """テスト用ステップ辞書を生成"""
    d: dict = {"id": step_id, "phase": phase, "type": step_type, "priority": priority}
    if depends_on is not None:
        d["depends_on"] = depends_on
    d.update(extra)
    return d


# ======================================================================
# 後方互換: depends_on なしの既存形式
# ======================================================================

class TestBackwardCompat:
    """depends_on なしの既存形式が正常動作すること"""

    def test_load_without_depends_on(self, tmp_path):
        steps = [
            _make_step("a", priority=10),
            _make_step("b", priority=20),
        ]
        p = _write_flow(tmp_path, "compat_flow", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert result.flow_def is not None
        assert [s.id for s in result.flow_def.steps] == ["a", "b"]
        assert result.flow_def.steps[0].depends_on is None
        assert result.flow_def.steps[1].depends_on is None

    def test_to_dict_without_depends_on(self, tmp_path):
        steps = [_make_step("x")]
        p = _write_flow(tmp_path, "dict_flow", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        d = result.flow_def.to_dict()
        step_dict = d["steps"][0]
        assert "depends_on" not in step_dict


# ======================================================================
# depends_on パース
# ======================================================================

class TestDependsOnParse:

    def test_valid_depends_on(self, tmp_path):
        steps = [
            _make_step("a", priority=10),
            _make_step("b", priority=20, depends_on=["a"]),
        ]
        p = _write_flow(tmp_path, "dep_valid", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        step_b = [s for s in result.flow_def.steps if s.id == "b"][0]
        assert step_b.depends_on == ["a"]

    def test_depends_on_not_list(self, tmp_path):
        """depends_on が list でない場合は警告して None にフォールバック"""
        steps = [_make_step("a", depends_on="not_a_list")]
        p = _write_flow(tmp_path, "dep_notlist", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert result.flow_def.steps[0].depends_on is None
        assert any("must be a list" in w for w in result.warnings)

    def test_depends_on_non_string_element(self, tmp_path):
        """depends_on 要素が str でない場合は警告して全体を None にフォールバック"""
        steps = [_make_step("a", depends_on=["valid", 123])]
        p = _write_flow(tmp_path, "dep_nonstr", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert result.flow_def.steps[0].depends_on is None
        assert any("must be a string" in w for w in result.warnings)

    def test_depends_on_empty_list(self, tmp_path):
        """空リストは有効"""
        steps = [_make_step("a", depends_on=[])]
        p = _write_flow(tmp_path, "dep_empty", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert result.flow_def.steps[0].depends_on == []

    def test_depends_on_in_to_dict(self, tmp_path):
        """depends_on が None でなければ to_dict に含まれる"""
        steps = [
            _make_step("a", priority=10),
            _make_step("b", priority=20, depends_on=["a"]),
        ]
        p = _write_flow(tmp_path, "dep_dict", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        d = result.flow_def.to_dict()
        step_a = [s for s in d["steps"] if s["id"] == "a"][0]
        step_b = [s for s in d["steps"] if s["id"] == "b"][0]
        assert "depends_on" not in step_a
        assert step_b["depends_on"] == ["a"]


# ======================================================================
# _sort_steps トポロジカルソート
# ======================================================================

class TestTopologicalSort:

    def test_simple_dependency(self, tmp_path):
        """b depends_on a → a が先に来る（priority が逆でも）"""
        steps = [
            _make_step("b", priority=10, depends_on=["a"]),
            _make_step("a", priority=20),
        ]
        p = _write_flow(tmp_path, "topo_simple", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        ids = [s.id for s in result.flow_def.steps]
        assert ids.index("a") < ids.index("b")

    def test_chain_dependency(self, tmp_path):
        """c -> b -> a のチェーン"""
        steps = [
            _make_step("c", priority=10, depends_on=["b"]),
            _make_step("b", priority=20, depends_on=["a"]),
            _make_step("a", priority=30),
        ]
        p = _write_flow(tmp_path, "topo_chain", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        ids = [s.id for s in result.flow_def.steps]
        assert ids == ["a", "b", "c"]

    def test_circular_dependency_fallback(self, tmp_path, caplog):
        """循環依存 → 既存ソート結果を維持 + warning"""
        steps = [
            _make_step("a", priority=10, depends_on=["b"]),
            _make_step("b", priority=20, depends_on=["a"]),
        ]
        p = _write_flow(tmp_path, "topo_cycle", steps)
        loader = FlowLoader()
        with caplog.at_level(logging.WARNING):
            result = loader.load_flow_file(p, "official")
        assert result.success
        # 既存ソート順: priority 10 (a) → priority 20 (b)
        ids = [s.id for s in result.flow_def.steps]
        assert ids == ["a", "b"]
        assert any("Circular dependency" in r.message for r in caplog.records)

    def test_nonexistent_dependency_warning(self, tmp_path, caplog):
        """存在しない step_id への depends_on → warning（ロード継続）"""
        steps = [
            _make_step("a", depends_on=["ghost"]),
        ]
        p = _write_flow(tmp_path, "topo_ghost", steps)
        loader = FlowLoader()
        with caplog.at_level(logging.WARNING):
            result = loader.load_flow_file(p, "official")
        assert result.success
        assert any("does not exist" in r.message for r in caplog.records)

    def test_cross_phase_dependency_warning(self, tmp_path, caplog):
        """phase をまたぐ depends_on → warning（phase 順序が優先）"""
        steps = [
            _make_step("a", phase="init", priority=10),
            _make_step("b", phase="main", priority=10, depends_on=["a"]),
        ]
        p = _write_flow(tmp_path, "topo_cross", steps, phases=["init", "main"])
        loader = FlowLoader()
        with caplog.at_level(logging.WARNING):
            result = loader.load_flow_file(p, "official")
        assert result.success
        ids = [s.id for s in result.flow_def.steps]
        assert ids == ["a", "b"]
        assert any("cross-phase" in r.message for r in caplog.records)

    def test_no_deps_preserves_order(self, tmp_path):
        """depends_on がない場合は既存ソート順を維持"""
        steps = [
            _make_step("c", priority=30),
            _make_step("a", priority=10),
            _make_step("b", priority=20),
        ]
        p = _write_flow(tmp_path, "topo_nodep", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        ids = [s.id for s in result.flow_def.steps]
        assert ids == ["a", "b", "c"]

    def test_stable_sort_with_deps(self, tmp_path):
        """depends_on がないステップ同士は既存ソート順を保持"""
        steps = [
            _make_step("d", priority=10),
            _make_step("c", priority=10),
            _make_step("b", priority=10, depends_on=["d"]),
            _make_step("a", priority=10),
        ]
        p = _write_flow(tmp_path, "topo_stable", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        ids = [s.id for s in result.flow_def.steps]
        # 既存ソート: priority 同一 → id アルファベット順 → a, b, c, d
        # b depends_on d → d は b の前に来る必要がある
        # トポロジカルソート: d より先に a, c が来てもよい（依存なし）、d の後に b
        assert ids.index("d") < ids.index("b")


# ======================================================================
# ファイルサイズ上限
# ======================================================================

class TestFileSizeLimit:

    def test_within_limit(self, tmp_path):
        """上限内のファイルは正常ロード"""
        steps = [_make_step("a")]
        p = _write_flow(tmp_path, "size_ok", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success

    def test_exceeds_limit(self, tmp_path, monkeypatch):
        """上限超過のファイルはエラー"""
        monkeypatch.setenv("RUMI_MAX_FLOW_FILE_BYTES", "10")
        steps = [_make_step("a")]
        p = _write_flow(tmp_path, "size_big", steps)
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert not result.success
        assert any("exceeds size limit" in e for e in result.errors)

    def test_exact_limit(self, tmp_path, monkeypatch):
        """ファイルサイズ == 上限 → 許可（> であり >= ではない）"""
        steps = [_make_step("a")]
        p = _write_flow(tmp_path, "size_exact", steps)
        file_size = p.stat().st_size
        monkeypatch.setenv("RUMI_MAX_FLOW_FILE_BYTES", str(file_size))
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success


# ======================================================================
# データ構造サイズチェック (_check_yaml_complexity)
# ======================================================================

class TestYamlComplexity:

    def test_simple_data(self):
        """スカラー値は OK"""
        _check_yaml_complexity("hello")
        _check_yaml_complexity(42)
        _check_yaml_complexity(None)

    def test_normal_dict(self):
        """通常の dict は OK"""
        data = {"a": {"b": {"c": 1}}}
        _check_yaml_complexity(data)

    def test_depth_exceeded(self):
        """深さ超過で ValueError"""
        data: dict = {}
        current = data
        for i in range(25):
            current[f"level_{i}"] = {}
            current = current[f"level_{i}"]
        with pytest.raises(ValueError, match="maximum depth"):
            _check_yaml_complexity(data, max_depth=20)

    def test_node_count_exceeded(self):
        """ノード数超過で ValueError"""
        data = {f"key_{i}": f"val_{i}" for i in range(200)}
        with pytest.raises(ValueError, match="maximum node count"):
            _check_yaml_complexity(data, max_nodes=100)

    def test_within_limits(self):
        """上限ちょうどは OK（超過でないため）"""
        # depth=1 (root dict) + 1 level of keys
        data = {"a": 1}
        # nodes: root(1) + key "a"(1) + value 1(1) = 3
        _check_yaml_complexity(data, max_depth=1, max_nodes=3)

    def test_list_depth(self):
        """リストも深さにカウントされる"""
        data: list = []
        current_list = data
        for _ in range(25):
            inner: list = []
            current_list.append(inner)
            current_list = inner
        with pytest.raises(ValueError, match="maximum depth"):
            _check_yaml_complexity(data, max_depth=20)


# ======================================================================
# YAML 1.1 型変換警告
# ======================================================================

class TestYaml11TypeWarning:

    def test_bool_step_id(self, tmp_path):
        """step_id が bool → 警告 + str 変換"""
        # YAML 1.1 で yes → True に変換される
        raw_yaml = textwrap.dedent("""\
            flow_id: "bool_id_flow"
            inputs: {}
            outputs: {}
            phases:
              - init
            steps:
              - id: yes
                phase: init
                type: action
        """)
        p = tmp_path / "bool_id.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert any("interpreted as boolean" in w for w in result.warnings)
        # True が str に変換される
        assert result.flow_def.steps[0].id == "True"

    def test_bool_phase(self, tmp_path):
        """phase が bool → 警告 + str 変換（phases リストに "True" があれば成功）"""
        raw_yaml = textwrap.dedent("""\
            flow_id: "bool_phase_flow"
            inputs: {}
            outputs: {}
            phases:
              - "True"
            steps:
              - id: step1
                phase: yes
                type: action
        """)
        p = tmp_path / "bool_phase.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert any("interpreted as boolean" in w for w in result.warnings)
        assert result.flow_def.steps[0].phase == "True"

    def test_float_flow_id(self, tmp_path):
        """flow_id が float → 警告 + str 変換"""
        raw_yaml = textwrap.dedent("""\
            flow_id: 1.5
            inputs: {}
            outputs: {}
            phases:
              - init
            steps:
              - id: step1
                phase: init
                type: action
        """)
        p = tmp_path / "float_id.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert result.flow_id == "1.5"
        assert any("auto-converted" in w for w in result.warnings)

    def test_int_flow_id(self, tmp_path):
        """flow_id が int → 警告 + str 変換"""
        raw_yaml = textwrap.dedent("""\
            flow_id: 42
            inputs: {}
            outputs: {}
            phases:
              - init
            steps:
              - id: step1
                phase: init
                type: action
        """)
        p = tmp_path / "int_id.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert result.flow_id == "42"
        assert any("auto-converted" in w for w in result.warnings)

    def test_bool_flow_id(self, tmp_path):
        """flow_id が bool → 警告 + str 変換"""
        raw_yaml = textwrap.dedent("""\
            flow_id: true
            inputs: {}
            outputs: {}
            phases:
              - init
            steps:
              - id: step1
                phase: init
                type: action
        """)
        p = tmp_path / "bool_flow_id.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert result.flow_id == "True"
        assert any("auto-converted" in w for w in result.warnings)

    def test_bool_output(self, tmp_path):
        """output が bool → 警告 + str 変換"""
        raw_yaml = textwrap.dedent("""\
            flow_id: "output_bool"
            inputs: {}
            outputs: {}
            phases:
              - init
            steps:
              - id: step1
                phase: init
                type: action
                output: yes
        """)
        p = tmp_path / "bool_output.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert any("interpreted as boolean" in w for w in result.warnings)
        assert result.flow_def.steps[0].output == "True"

    def test_bool_when(self, tmp_path):
        """when が bool → 警告 + str 変換"""
        raw_yaml = textwrap.dedent("""\
            flow_id: "when_bool"
            inputs: {}
            outputs: {}
            phases:
              - init
            steps:
              - id: step1
                phase: init
                type: action
                when: yes
        """)
        p = tmp_path / "bool_when.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert any("interpreted as boolean" in w for w in result.warnings)
        assert result.flow_def.steps[0].when == "True"

    def test_string_values_no_warning(self, tmp_path):
        """クォートされた文字列は警告なし"""
        raw_yaml = textwrap.dedent("""\
            flow_id: "normal_flow"
            inputs: {}
            outputs: {}
            phases:
              - init
            steps:
              - id: "yes"
                phase: init
                type: action
                output: "true"
                when: "on"
        """)
        p = tmp_path / "quoted.flow.yaml"
        p.write_text(raw_yaml, encoding="utf-8")
        loader = FlowLoader()
        result = loader.load_flow_file(p, "official")
        assert result.success
        assert len(result.warnings) == 0
