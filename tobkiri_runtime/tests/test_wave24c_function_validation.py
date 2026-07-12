"""
test_wave24c_function_validation.py - W24-C manifest.json バリデーションのテスト
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
    eco_data: dict | None = None,
) -> Path:
    """ecosystem ディレクトリ内に最小限の Pack を作成する。"""
    pack_dir = ecosystem_dir / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    if eco_data is None:
        eco_data = {"pack_id": pack_id, "connectivity": []}
    (pack_dir / "ecosystem.json").write_text(
        json.dumps(eco_data, ensure_ascii=False), encoding="utf-8",
    )
    return pack_dir


def _make_function(
    pack_dir: Path,
    func_name: str,
    manifest: dict | str | None = "valid",
    create_main_py: bool = True,
) -> Path:
    """
    Pack 内に function ディレクトリを作成する。

    Args:
        pack_dir: Pack ルートディレクトリ
        func_name: function ディレクトリ名
        manifest: dict -> JSON化, str "valid" -> デフォルト正常manifest,
                  str その他 -> そのまま書き込み(不正JSON用), None -> manifest.json 未作成
        create_main_py: main.py を作成するか
    """
    func_dir = pack_dir / "functions" / func_name
    func_dir.mkdir(parents=True, exist_ok=True)

    if manifest == "valid":
        manifest = {
            "function_id": func_name,
            "description": f"Test function {func_name}",
            "requires": ["runtime"],
            "tags": ["test"],
        }

    if manifest is not None:
        manifest_path = func_dir / "manifest.json"
        if isinstance(manifest, dict):
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8",
            )
        else:
            manifest_path.write_text(manifest, encoding="utf-8")

    if create_main_py:
        (func_dir / "main.py").write_text("# entry point\n", encoding="utf-8")

    return func_dir


# ======================================================================
# テスト: functions/ ディレクトリなし（後方互換）
# ======================================================================

class TestNoFunctionsDir:

    def test_no_functions_dir_no_errors(self, tmp_path: Path):
        """functions/ ディレクトリがない Pack -> function 系 error/warning なし"""
        eco_dir = tmp_path / "ecosystem"
        _make_pack(eco_dir, "pack_a")
        report = validate_packs(str(eco_dir))
        func_msgs = [m for m in report.errors + report.warnings if "functions/" in m]
        assert len(func_msgs) == 0


# ======================================================================
# テスト: 正常系
# ======================================================================

class TestValidManifest:

    def test_valid_function_no_errors(self, tmp_path: Path):
        """正常な manifest.json -> function 系 error なし"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func")
        report = validate_packs(str(eco_dir))
        func_errors = [e for e in report.errors if "functions/" in e]
        assert len(func_errors) == 0

    def test_valid_function_with_all_optional_fields(self, tmp_path: Path):
        """全オプションフィールドが正常 -> function 系 error/warning なし"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "full_func", manifest={
            "function_id": "full_func",
            "description": "A complete function",
            "requires": ["runtime"],
            "caller_requires": ["auth"],
            "host_execution": False,
            "tags": ["util", "core"],
            "input_schema": {"type": "object"},
            "output_schema": {"type": "string"},
        })
        report = validate_packs(str(eco_dir))
        func_errors = [e for e in report.errors if "functions/" in e]
        func_warnings = [w for w in report.warnings if "functions/" in w]
        assert len(func_errors) == 0
        assert len(func_warnings) == 0


# ======================================================================
# テスト: function_id 系エラー
# ======================================================================

class TestFunctionIdErrors:

    def test_function_id_missing(self, tmp_path: Path):
        """function_id 欠落 -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "requires": ["runtime"],
            "tags": ["test"],
            "description": "no id",
        })
        report = validate_packs(str(eco_dir))
        assert any("function_id" in e and "missing" in e for e in report.errors)

    def test_function_id_mismatch(self, tmp_path: Path):
        """function_id がディレクトリ名と不一致 -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "wrong_name",
            "requires": ["runtime"],
            "tags": ["test"],
            "description": "mismatch",
        })
        report = validate_packs(str(eco_dir))
        assert any("does not match directory" in e for e in report.errors)

    def test_function_id_invalid_pattern_uppercase(self, tmp_path: Path):
        """function_id に大文字 -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "MyFunc",
            "requires": ["runtime"],
            "tags": ["test"],
            "description": "uppercase",
        })
        report = validate_packs(str(eco_dir))
        assert any("pattern" in e for e in report.errors)

    def test_function_id_invalid_pattern_starts_with_number(self, tmp_path: Path):
        """function_id が数字始まり -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "1func",
            "requires": ["runtime"],
            "tags": ["test"],
            "description": "starts with number",
        })
        report = validate_packs(str(eco_dir))
        assert any("pattern" in e for e in report.errors)


# ======================================================================
# テスト: requires 系エラー
# ======================================================================

class TestRequiresErrors:

    def test_requires_missing(self, tmp_path: Path):
        """requires 欠落 -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "tags": ["test"],
            "description": "no requires",
        })
        report = validate_packs(str(eco_dir))
        assert any("requires" in e and "missing" in e for e in report.errors)

    def test_requires_not_a_list(self, tmp_path: Path):
        """requires が list でない -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": "runtime",
            "tags": ["test"],
            "description": "string requires",
        })
        report = validate_packs(str(eco_dir))
        assert any("requires must be a list" in e for e in report.errors)

    def test_caller_requires_not_a_list(self, tmp_path: Path):
        """caller_requires が list でない -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "caller_requires": "auth",
            "tags": ["test"],
            "description": "string caller_requires",
        })
        report = validate_packs(str(eco_dir))
        assert any("caller_requires must be a list" in e for e in report.errors)


# ======================================================================
# テスト: host_execution / tags / schema エラー
# ======================================================================

class TestOptionalFieldErrors:

    def test_host_execution_not_bool(self, tmp_path: Path):
        """host_execution が bool でない -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "host_execution": "yes",
            "tags": ["test"],
            "description": "bad host_execution",
        })
        report = validate_packs(str(eco_dir))
        assert any("host_execution must be a boolean" in e for e in report.errors)

    def test_tags_not_a_list(self, tmp_path: Path):
        """tags が list でない -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "tags": "test",
            "description": "string tags",
        })
        report = validate_packs(str(eco_dir))
        assert any("tags must be a list" in e for e in report.errors)

    def test_input_schema_not_dict(self, tmp_path: Path):
        """input_schema が dict でない -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "tags": ["test"],
            "description": "bad schema",
            "input_schema": ["not", "a", "dict"],
        })
        report = validate_packs(str(eco_dir))
        assert any("input_schema must be a dict" in e for e in report.errors)

    def test_output_schema_not_dict(self, tmp_path: Path):
        """output_schema が dict でない -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "tags": ["test"],
            "description": "bad output schema",
            "output_schema": "string",
        })
        report = validate_packs(str(eco_dir))
        assert any("output_schema must be a dict" in e for e in report.errors)


# ======================================================================
# テスト: ファイル系エラー
# ======================================================================

class TestFileErrors:

    def test_main_py_missing(self, tmp_path: Path):
        """main.py 欠落 -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", create_main_py=False)
        report = validate_packs(str(eco_dir))
        assert any("main.py not found" in e for e in report.errors)

    def test_manifest_invalid_json(self, tmp_path: Path):
        """manifest.json が不正な JSON -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest="{invalid json!!}")
        report = validate_packs(str(eco_dir))
        assert any("invalid JSON" in e for e in report.errors)


# ======================================================================
# テスト: warnings
# ======================================================================

class TestWarnings:

    def test_host_execution_true_warning(self, tmp_path: Path):
        """host_execution: true -> warning (error ではない)"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "host_execution": True,
            "tags": ["test"],
            "description": "host exec func",
        })
        report = validate_packs(str(eco_dir))
        func_errors = [e for e in report.errors if "functions/" in e]
        assert len(func_errors) == 0
        assert any("host_execution is true" in w for w in report.warnings)

    def test_description_missing_warning(self, tmp_path: Path):
        """description 未設定 -> warning"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "tags": ["test"],
        })
        report = validate_packs(str(eco_dir))
        assert any("description" in w and "missing" in w for w in report.warnings)

    def test_tags_missing_warning(self, tmp_path: Path):
        """tags 未設定 -> warning"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "my_func", manifest={
            "function_id": "my_func",
            "requires": ["runtime"],
            "description": "has desc but no tags",
        })
        report = validate_packs(str(eco_dir))
        assert any("tags" in w and "discoverability" in w for w in report.warnings)


# ======================================================================
# テスト: 複数 function / エッジケース
# ======================================================================

class TestMultipleAndEdgeCases:

    def test_multiple_functions_partial_invalid(self, tmp_path: Path):
        """複数 function で一部のみ不正 -> 不正な function のみ error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "good_func")
        _make_function(pack_dir, "bad_func", manifest={
            "function_id": "bad_func",
            "description": "missing requires",
            "tags": ["test"],
        })
        report = validate_packs(str(eco_dir))
        func_errors = [e for e in report.errors if "functions/" in e]
        assert len(func_errors) >= 1
        assert all("bad_func" in e for e in func_errors)
        assert not any("good_func" in e for e in func_errors)

    def test_hidden_directory_skipped(self, tmp_path: Path):
        """隠しディレクトリ (.hidden) はスキップされる"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "good_func")
        # 隠しディレクトリ — manifest.json なしでも error にならないはず
        hidden_dir = pack_dir / "functions" / ".hidden"
        hidden_dir.mkdir(parents=True, exist_ok=True)
        report = validate_packs(str(eco_dir))
        func_errors = [e for e in report.errors if "functions/" in e]
        assert len(func_errors) == 0

    def test_manifest_not_found(self, tmp_path: Path):
        """manifest.json がない function ディレクトリ -> error"""
        eco_dir = tmp_path / "ecosystem"
        pack_dir = _make_pack(eco_dir, "pack_a")
        _make_function(pack_dir, "no_manifest", manifest=None)
        report = validate_packs(str(eco_dir))
        assert any("manifest.json not found" in e for e in report.errors)
