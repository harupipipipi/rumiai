"""
test_pack_scaffold.py - PackScaffold のユニットテスト (Wave 14 T-055)
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from core_runtime.pack_scaffold import PackScaffold, main, VALID_TEMPLATES


# ======================================================================
# Fixture
# ======================================================================

@pytest.fixture
def scaffold():
    return PackScaffold()


# ======================================================================
# テスト: minimal テンプレート
# ======================================================================

class TestMinimalTemplate:
    """minimal テンプレートの生成確認"""

    def test_creates_pack_directory(self, scaffold, tmp_path: Path):
        result = scaffold.generate("my_pack", tmp_path, template="minimal")
        assert result == tmp_path / "my_pack"
        assert result.is_dir()

    def test_creates_ecosystem_json(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        eco = tmp_path / "my_pack" / "ecosystem.json"
        assert eco.is_file()

    def test_creates_init_py(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        init = tmp_path / "my_pack" / "__init__.py"
        assert init.is_file()

    def test_minimal_has_exactly_two_files(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        pack_dir = tmp_path / "my_pack"
        files = list(pack_dir.rglob("*"))
        file_only = [f for f in files if f.is_file()]
        assert len(file_only) == 2

    def test_ecosystem_json_is_valid_json(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        eco = tmp_path / "my_pack" / "ecosystem.json"
        data = json.loads(eco.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_ecosystem_json_has_pack_id(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        eco = tmp_path / "my_pack" / "ecosystem.json"
        data = json.loads(eco.read_text(encoding="utf-8"))
        assert data["pack_id"] == "my_pack"

    def test_ecosystem_json_has_required_fields(self, scaffold, tmp_path: Path):
        scaffold.generate("test_pack", tmp_path, template="minimal")
        eco = tmp_path / "test_pack" / "ecosystem.json"
        data = json.loads(eco.read_text(encoding="utf-8"))
        for field in ("pack_id", "version", "description", "capabilities",
                       "flows", "connectivity", "trust"):
            assert field in data, f"Missing field: {field}"

    def test_ecosystem_json_connectivity_is_list(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        eco = tmp_path / "my_pack" / "ecosystem.json"
        data = json.loads(eco.read_text(encoding="utf-8"))
        assert isinstance(data["connectivity"], list)

    def test_ecosystem_json_version_format(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        eco = tmp_path / "my_pack" / "ecosystem.json"
        data = json.loads(eco.read_text(encoding="utf-8"))
        assert data["version"] == "0.1.0"


# ======================================================================
# テスト: capability テンプレート
# ======================================================================

class TestCapabilityTemplate:
    """capability テンプレートの生成確認"""

    def test_creates_capability_handler(self, scaffold, tmp_path: Path):
        scaffold.generate("cap_pack", tmp_path, template="capability")
        handler = tmp_path / "cap_pack" / "capability_handler.py"
        assert handler.is_file()

    def test_has_ecosystem_json(self, scaffold, tmp_path: Path):
        scaffold.generate("cap_pack", tmp_path, template="capability")
        assert (tmp_path / "cap_pack" / "ecosystem.json").is_file()

    def test_has_init_py(self, scaffold, tmp_path: Path):
        scaffold.generate("cap_pack", tmp_path, template="capability")
        assert (tmp_path / "cap_pack" / "__init__.py").is_file()

    def test_capability_has_exactly_three_files(self, scaffold, tmp_path: Path):
        scaffold.generate("cap_pack", tmp_path, template="capability")
        pack_dir = tmp_path / "cap_pack"
        file_only = [f for f in pack_dir.rglob("*") if f.is_file()]
        assert len(file_only) == 3

    def test_capability_handler_contains_handle_function(self, scaffold, tmp_path: Path):
        scaffold.generate("cap_pack", tmp_path, template="capability")
        handler = tmp_path / "cap_pack" / "capability_handler.py"
        content = handler.read_text(encoding="utf-8")
        assert "def handle(" in content


# ======================================================================
# テスト: flow テンプレート
# ======================================================================

class TestFlowTemplate:
    """flow テンプレートの生成確認"""

    def test_creates_flows_directory(self, scaffold, tmp_path: Path):
        scaffold.generate("flow_pack", tmp_path, template="flow")
        flows_dir = tmp_path / "flow_pack" / "flows"
        assert flows_dir.is_dir()

    def test_creates_sample_flow_yaml(self, scaffold, tmp_path: Path):
        scaffold.generate("flow_pack", tmp_path, template="flow")
        flow = tmp_path / "flow_pack" / "flows" / "sample_flow.yaml"
        assert flow.is_file()

    def test_has_ecosystem_json(self, scaffold, tmp_path: Path):
        scaffold.generate("flow_pack", tmp_path, template="flow")
        assert (tmp_path / "flow_pack" / "ecosystem.json").is_file()

    def test_flow_does_not_have_capability_handler(self, scaffold, tmp_path: Path):
        scaffold.generate("flow_pack", tmp_path, template="flow")
        handler = tmp_path / "flow_pack" / "capability_handler.py"
        assert not handler.exists()

    def test_sample_flow_yaml_content(self, scaffold, tmp_path: Path):
        scaffold.generate("flow_pack", tmp_path, template="flow")
        flow = tmp_path / "flow_pack" / "flows" / "sample_flow.yaml"
        content = flow.read_text(encoding="utf-8")
        assert "sample_flow" in content
        assert "steps:" in content


# ======================================================================
# テスト: full テンプレート
# ======================================================================

class TestFullTemplate:
    """full テンプレートの生成確認"""

    def test_has_all_minimal_files(self, scaffold, tmp_path: Path):
        scaffold.generate("full_pack", tmp_path, template="full")
        assert (tmp_path / "full_pack" / "ecosystem.json").is_file()
        assert (tmp_path / "full_pack" / "__init__.py").is_file()

    def test_has_capability_handler(self, scaffold, tmp_path: Path):
        scaffold.generate("full_pack", tmp_path, template="full")
        assert (tmp_path / "full_pack" / "capability_handler.py").is_file()

    def test_has_flows_directory_and_sample(self, scaffold, tmp_path: Path):
        scaffold.generate("full_pack", tmp_path, template="full")
        assert (tmp_path / "full_pack" / "flows" / "sample_flow.yaml").is_file()

    def test_has_tests_directory(self, scaffold, tmp_path: Path):
        scaffold.generate("full_pack", tmp_path, template="full")
        assert (tmp_path / "full_pack" / "tests").is_dir()
        assert (tmp_path / "full_pack" / "tests" / "__init__.py").is_file()

    def test_has_readme(self, scaffold, tmp_path: Path):
        scaffold.generate("full_pack", tmp_path, template="full")
        readme = tmp_path / "full_pack" / "README.md"
        assert readme.is_file()
        content = readme.read_text(encoding="utf-8")
        assert "full_pack" in content

    def test_full_has_exactly_six_files(self, scaffold, tmp_path: Path):
        scaffold.generate("full_pack", tmp_path, template="full")
        pack_dir = tmp_path / "full_pack"
        file_only = [f for f in pack_dir.rglob("*") if f.is_file()]
        assert len(file_only) == 6


# ======================================================================
# テスト: pack_id バリデーション
# ======================================================================

class TestPackIdValidation:
    """pack_id バリデーションのテスト"""

    def test_empty_pack_id_raises(self, scaffold, tmp_path: Path):
        with pytest.raises(ValueError, match="Invalid pack_id"):
            scaffold.generate("", tmp_path)

    def test_pack_id_with_spaces_raises(self, scaffold, tmp_path: Path):
        with pytest.raises(ValueError, match="Invalid pack_id"):
            scaffold.generate("my pack", tmp_path)

    def test_pack_id_with_dots_raises(self, scaffold, tmp_path: Path):
        with pytest.raises(ValueError, match="Invalid pack_id"):
            scaffold.generate("my.pack", tmp_path)

    def test_pack_id_with_slash_raises(self, scaffold, tmp_path: Path):
        with pytest.raises(ValueError, match="Invalid pack_id"):
            scaffold.generate("my/pack", tmp_path)

    def test_pack_id_too_long_raises(self, scaffold, tmp_path: Path):
        long_id = "a" * 65
        with pytest.raises(ValueError, match="Invalid pack_id"):
            scaffold.generate(long_id, tmp_path)

    def test_valid_pack_id_with_hyphens(self, scaffold, tmp_path: Path):
        result = scaffold.generate("my-pack", tmp_path)
        assert result.is_dir()

    def test_valid_pack_id_with_underscores(self, scaffold, tmp_path: Path):
        result = scaffold.generate("my_pack", tmp_path)
        assert result.is_dir()

    def test_valid_pack_id_max_length(self, scaffold, tmp_path: Path):
        pack_id = "a" * 64
        result = scaffold.generate(pack_id, tmp_path)
        assert result.is_dir()


# ======================================================================
# テスト: 上書き防止
# ======================================================================

class TestOverwriteProtection:
    """上書き防止のテスト"""

    def test_existing_nonempty_dir_raises(self, scaffold, tmp_path: Path):
        pack_dir = tmp_path / "my_pack"
        pack_dir.mkdir()
        (pack_dir / "some_file.txt").write_text("existing", encoding="utf-8")
        with pytest.raises(FileExistsError, match="already exists"):
            scaffold.generate("my_pack", tmp_path)

    def test_existing_empty_dir_is_allowed(self, scaffold, tmp_path: Path):
        pack_dir = tmp_path / "my_pack"
        pack_dir.mkdir()
        result = scaffold.generate("my_pack", tmp_path)
        assert result == pack_dir
        assert (pack_dir / "ecosystem.json").is_file()

    def test_force_overwrites_existing(self, scaffold, tmp_path: Path):
        pack_dir = tmp_path / "my_pack"
        pack_dir.mkdir()
        (pack_dir / "some_file.txt").write_text("existing", encoding="utf-8")
        result = scaffold.generate("my_pack", tmp_path, force=True)
        assert result == pack_dir
        assert (pack_dir / "ecosystem.json").is_file()
        # 元のファイルも残っている（削除はしない）
        assert (pack_dir / "some_file.txt").is_file()

    def test_force_updates_ecosystem_json(self, scaffold, tmp_path: Path):
        scaffold.generate("my_pack", tmp_path, template="minimal")
        eco = tmp_path / "my_pack" / "ecosystem.json"
        original = eco.read_text(encoding="utf-8")
        # force で再生成
        scaffold.generate("my_pack", tmp_path, template="full", force=True)
        updated = eco.read_text(encoding="utf-8")
        assert original == updated  # ecosystem.json の内容は同じ pack_id なので同一
        # full テンプレートの追加ファイルが存在する
        assert (tmp_path / "my_pack" / "README.md").is_file()

    def test_nonexistent_target_dir_is_created(self, scaffold, tmp_path: Path):
        deep_dir = tmp_path / "a" / "b" / "c"
        result = scaffold.generate("my_pack", deep_dir)
        assert result.is_dir()
        assert (result / "ecosystem.json").is_file()


# ======================================================================
# テスト: テンプレートバリデーション
# ======================================================================

class TestTemplateValidation:
    """未知テンプレートの検証"""

    def test_unknown_template_raises(self, scaffold, tmp_path: Path):
        with pytest.raises(ValueError, match="Unknown template"):
            scaffold.generate("my_pack", tmp_path, template="nonexistent")

    def test_valid_templates_constant(self):
        assert "minimal" in VALID_TEMPLATES
        assert "capability" in VALID_TEMPLATES
        assert "flow" in VALID_TEMPLATES
        assert "full" in VALID_TEMPLATES


# ======================================================================
# テスト: CLI エントリポイント
# ======================================================================

class TestCLI:
    """CLI main() のテスト"""

    def test_cli_generates_pack(self, tmp_path: Path):
        exit_code = main(["test_pack", "--output", str(tmp_path)])
        assert exit_code == 0
        assert (tmp_path / "test_pack" / "ecosystem.json").is_file()

    def test_cli_with_template(self, tmp_path: Path):
        exit_code = main(["test_pack", "-t", "full", "-o", str(tmp_path)])
        assert exit_code == 0
        assert (tmp_path / "test_pack" / "README.md").is_file()

    def test_cli_invalid_pack_id(self, tmp_path: Path):
        exit_code = main(["invalid pack!", "-o", str(tmp_path)])
        assert exit_code == 1

    def test_cli_force_flag(self, tmp_path: Path):
        main(["test_pack", "-o", str(tmp_path)])
        exit_code = main(["test_pack", "-o", str(tmp_path), "--force"])
        assert exit_code == 0

    def test_cli_existing_dir_without_force(self, tmp_path: Path):
        main(["test_pack", "-o", str(tmp_path), "-t", "full"])
        exit_code = main(["test_pack", "-o", str(tmp_path)])
        assert exit_code == 1

    def test_cli_default_template_is_minimal(self, tmp_path: Path):
        main(["test_pack", "-o", str(tmp_path)])
        pack_dir = tmp_path / "test_pack"
        file_only = [f for f in pack_dir.rglob("*") if f.is_file()]
        assert len(file_only) == 2
