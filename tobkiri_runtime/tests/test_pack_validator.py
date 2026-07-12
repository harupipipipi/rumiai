"""
test_pack_validator.py - pack_validator のユニットテスト
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from core_runtime.pack_validator import validate_packs, ValidationReport


# ======================================================================
# ヘルパー
# ======================================================================

def _make_pack(
    ecosystem_dir: Path,
    pack_id: str,
    eco_data: dict,
    flow_files: dict[str, str] | None = None,
) -> Path:
    """
    tmp ecosystem ディレクトリ内に Pack を作成する。

    Args:
        ecosystem_dir: ecosystem ルート
        pack_id: ディレクトリ名
        eco_data: ecosystem.json の内容
        flow_files: {相対パス: ファイル内容} の辞書（flows/ 以下に作成）

    Returns:
        Pack ディレクトリの Path
    """
    pack_dir = ecosystem_dir / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)

    eco_json = pack_dir / "ecosystem.json"
    eco_json.write_text(
        json.dumps(eco_data, ensure_ascii=False), encoding="utf-8",
    )

    if flow_files:
        flows_dir = pack_dir / "flows"
        flows_dir.mkdir(exist_ok=True)
        for rel_path, content in flow_files.items():
            fpath = flows_dir / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

    return pack_dir


# ======================================================================
# テスト: connectivity 存在チェック
# ======================================================================

class TestConnectivityPresence:
    """connectivity フィールドの有無チェック"""

    def test_connectivity_present_and_populated(self, tmp_path: Path):
        """connectivity が宣言されていて中身もある → warning なし"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "pack_a", {
            "pack_id": "pack_a",
            "connectivity": ["pack_b"],
        })
        _make_pack(eco_dir, "pack_b", {
            "pack_id": "pack_b",
            "connectivity": ["pack_a"],
        })
        report = validate_packs(str(eco_dir))
        assert isinstance(report, ValidationReport)
        assert report.pack_count == 2
        assert len(report.warnings) == 0
        assert len(report.errors) == 0
        assert report.valid_count == 2

    def test_connectivity_missing(self, tmp_path: Path):
        """connectivity が未宣言 → warning"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "pack_a", {"pack_id": "pack_a"})
        report = validate_packs(str(eco_dir))
        assert report.pack_count == 1
        assert any("not declared" in w for w in report.warnings)
        assert report.valid_count == 0

    def test_connectivity_empty_list(self, tmp_path: Path):
        """connectivity が空リスト → warning"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "pack_a", {
            "pack_id": "pack_a",
            "connectivity": [],
        })
        report = validate_packs(str(eco_dir))
        assert report.pack_count == 1
        assert any("empty" in w for w in report.warnings)

    def test_connectivity_not_a_list(self, tmp_path: Path):
        """connectivity がリストでない → warning"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "pack_a", {
            "pack_id": "pack_a",
            "connectivity": "pack_b",
        })
        report = validate_packs(str(eco_dir))
        assert any("not a list" in w for w in report.warnings)


# ======================================================================
# テスト: pack_id 不一致
# ======================================================================

class TestPackIdMismatch:
    """pack_id とディレクトリ名の不一致チェック"""

    def test_pack_id_matches(self, tmp_path: Path):
        """pack_id 一致 → mismatch warning なし"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "my_pack", {
            "pack_id": "my_pack",
            "connectivity": ["other"],
        })
        report = validate_packs(str(eco_dir))
        assert not any("mismatch" in w for w in report.warnings)

    def test_pack_id_mismatch(self, tmp_path: Path):
        """pack_id 不一致 → warning"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "dir_name", {
            "pack_id": "different_name",
            "connectivity": ["other"],
        })
        report = validate_packs(str(eco_dir))
        assert any("mismatch" in w for w in report.warnings)


# ======================================================================
# テスト: ${ctx.*} 参照チェック
# ======================================================================

class TestCtxReferences:
    """${ctx.*} 変数参照の connectivity チェック"""

    def test_ctx_ref_in_connectivity(self, tmp_path: Path):
        """参照先が connectivity に含まれる → ctx warning なし"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(
            eco_dir, "pack_a",
            {"pack_id": "pack_a", "connectivity": ["pack_b"]},
            flow_files={
                "main.json": '{"action": "${ctx.pack_b.some_key}"}',
            },
        )
        _make_pack(eco_dir, "pack_b", {
            "pack_id": "pack_b",
            "connectivity": ["pack_a"],
        })
        report = validate_packs(str(eco_dir))
        ctx_warnings = [
            w for w in report.warnings
            if "ctx." in w and "[pack_a]" in w
        ]
        assert len(ctx_warnings) == 0

    def test_ctx_ref_not_in_connectivity(self, tmp_path: Path):
        """参照先が connectivity に含まれない → warning"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(
            eco_dir, "pack_a",
            {"pack_id": "pack_a", "connectivity": ["pack_c"]},
            flow_files={
                "main.json": '{"action": "${ctx.pack_b.some_key}"}',
            },
        )
        _make_pack(eco_dir, "pack_b", {
            "pack_id": "pack_b",
            "connectivity": ["pack_a"],
        })
        _make_pack(eco_dir, "pack_c", {
            "pack_id": "pack_c",
            "connectivity": ["pack_a"],
        })
        report = validate_packs(str(eco_dir))
        ctx_warnings = [
            w for w in report.warnings
            if "ctx.pack_b" in w and "[pack_a]" in w
        ]
        assert len(ctx_warnings) >= 1

    def test_ctx_self_reference_ignored(self, tmp_path: Path):
        """自身への参照 (${ctx.pack_a.*}) はスキップ"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(
            eco_dir, "pack_a",
            {"pack_id": "pack_a", "connectivity": ["pack_b"]},
            flow_files={
                "main.json": '{"action": "${ctx.pack_a.my_key}"}',
            },
        )
        _make_pack(eco_dir, "pack_b", {
            "pack_id": "pack_b",
            "connectivity": ["pack_a"],
        })
        report = validate_packs(str(eco_dir))
        ctx_warnings = [w for w in report.warnings if "ctx.pack_a" in w]
        assert len(ctx_warnings) == 0

    def test_ctx_ref_in_yaml(self, tmp_path: Path):
        """YAML ファイル内の参照も検出"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(
            eco_dir, "pack_a",
            {"pack_id": "pack_a", "connectivity": ["pack_b"]},
            flow_files={
                "flow.yml": "steps:\n  - action: ${ctx.pack_c.value}\n",
            },
        )
        _make_pack(eco_dir, "pack_b", {
            "pack_id": "pack_b",
            "connectivity": ["pack_a"],
        })
        report = validate_packs(str(eco_dir))
        ctx_warnings = [w for w in report.warnings if "ctx.pack_c" in w]
        assert len(ctx_warnings) >= 1


# ======================================================================
# テスト: エッジケース
# ======================================================================

class TestEdgeCases:
    """エッジケースのテスト"""

    def test_ecosystem_dir_not_exists(self, tmp_path: Path):
        """存在しない ecosystem ディレクトリ → error"""
        report = validate_packs(str(tmp_path / "nonexistent"))
        assert len(report.errors) >= 1
        assert report.pack_count == 0

    def test_invalid_json(self, tmp_path: Path):
        """壊れた ecosystem.json → error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = eco_dir / "broken_pack"
        pack_dir.mkdir(parents=True)
        (pack_dir / "ecosystem.json").write_text(
            "{invalid json", encoding="utf-8",
        )
        report = validate_packs(str(eco_dir))
        assert report.pack_count == 1
        assert any("invalid JSON" in e for e in report.errors)

    def test_empty_ecosystem_dir(self, tmp_path: Path):
        """空の ecosystem ディレクトリ → pack_count=0, 問題なし"""
        eco_dir = tmp_path / "ecosystem"
        eco_dir.mkdir()
        report = validate_packs(str(eco_dir))
        assert report.pack_count == 0
        assert len(report.warnings) == 0
        assert len(report.errors) == 0

    def test_report_type(self, tmp_path: Path):
        """ValidationReport の型確認"""
        eco_dir = tmp_path / "ecosystem"
        eco_dir.mkdir()
        report = validate_packs(str(eco_dir))
        assert isinstance(report, ValidationReport)
        assert isinstance(report.warnings, list)
        assert isinstance(report.errors, list)
        assert isinstance(report.pack_count, int)
        assert isinstance(report.valid_count, int)

    def test_no_flow_files(self, tmp_path: Path):
        """Flow ファイルがない場合でも正常動作"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "pack_a", {
            "pack_id": "pack_a",
            "connectivity": ["pack_b"],
        })
        _make_pack(eco_dir, "pack_b", {
            "pack_id": "pack_b",
            "connectivity": ["pack_a"],
        })
        report = validate_packs(str(eco_dir))
        assert report.pack_count == 2
        # Flow なし → ctx 系 warning なし、connectivity 宣言済み → warning なし
        assert len(report.warnings) == 0
