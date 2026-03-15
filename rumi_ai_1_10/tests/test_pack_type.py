# tests/test_pack_type.py
"""
Pack Type 関連のテスト

Wave 1: pack_type / provides_runtime / runtime_type バリデーション
Wave 2: ルール拡張承認フロー (approve_rule / is_rule_approved)
Wave 3: 依存関係検証 (validate_rule_dependencies)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


# ======================================================================
# Helpers
# ======================================================================

def _create_pack_dir(eco_dir: Path, pack_id: str, eco_data: dict) -> Path:
    """テスト用 Pack ディレクトリを作成し ecosystem.json を書き込む"""
    pack_dir = eco_dir / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    eco_json = pack_dir / "ecosystem.json"
    with open(eco_json, "w", encoding="utf-8") as f:
        json.dump(eco_data, f, ensure_ascii=False)
    return pack_dir


# ======================================================================
# Wave 1: pack_validator.py テスト
# ======================================================================


class TestPackTypeValidation:
    """pack_type フィールドのバリデーションテスト"""

    @pytest.fixture
    def temp_ecosystem(self, tmp_path):
        eco_dir = tmp_path / "ecosystem"
        eco_dir.mkdir()
        return eco_dir

    def test_pack_type_valid_values(self, temp_ecosystem):
        """有効な pack_type 値はエラーにならない"""
        from core_runtime.pack_validator import validate_packs

        for pt in ["rule", "application", "library"]:
            _create_pack_dir(temp_ecosystem, f"test_{pt}", {
                "pack_id": f"test_{pt}",
                "pack_type": pt,
                "connectivity": [],
            })

        report = validate_packs(str(temp_ecosystem))
        type_errors = [e for e in report.errors if "pack_type" in e]
        assert len(type_errors) == 0, f"Unexpected errors: {type_errors}"

    def test_pack_type_invalid_value(self, temp_ecosystem):
        """無効な pack_type はエラーになる"""
        from core_runtime.pack_validator import validate_packs

        _create_pack_dir(temp_ecosystem, "test_bad", {
            "pack_id": "test_bad",
            "pack_type": "invalid_type",
            "connectivity": [],
        })

        report = validate_packs(str(temp_ecosystem))
        type_errors = [e for e in report.errors if "pack_type" in e]
        assert len(type_errors) >= 1

    def test_pack_type_default_when_omitted(self, temp_ecosystem):
        """pack_type 省略時はエラーにならない（デフォルト application）"""
        from core_runtime.pack_validator import validate_packs

        _create_pack_dir(temp_ecosystem, "test_default", {
            "pack_id": "test_default",
            "connectivity": [],
        })

        report = validate_packs(str(temp_ecosystem))
        type_errors = [e for e in report.errors if "pack_type" in e]
        assert len(type_errors) == 0

    def test_provides_runtime_valid_for_rule(self, temp_ecosystem):
        """pack_type rule での provides_runtime は有効"""
        from core_runtime.pack_validator import validate_packs

        _create_pack_dir(temp_ecosystem, "test_rule_rt", {
            "pack_id": "test_rule_rt",
            "pack_type": "rule",
            "provides_runtime": ["binary", "wasm"],
            "connectivity": [],
        })

        report = validate_packs(str(temp_ecosystem))
        pr_errors = [e for e in report.errors if "provides_runtime" in e]
        assert len(pr_errors) == 0

    def test_provides_runtime_invalid_for_application(self, temp_ecosystem):
        """pack_type application での provides_runtime はエラー"""
        from core_runtime.pack_validator import validate_packs

        _create_pack_dir(temp_ecosystem, "test_app_pr", {
            "pack_id": "test_app_pr",
            "pack_type": "application",
            "provides_runtime": ["binary"],
            "connectivity": [],
        })

        report = validate_packs(str(temp_ecosystem))
        pr_errors = [e for e in report.errors if "provides_runtime" in e]
        assert len(pr_errors) >= 1

    def test_provides_runtime_invalid_type(self, temp_ecosystem):
        """provides_runtime が list[str] でなければエラー"""
        from core_runtime.pack_validator import validate_packs

        _create_pack_dir(temp_ecosystem, "test_pr_bad", {
            "pack_id": "test_pr_bad",
            "pack_type": "rule",
            "provides_runtime": "not_a_list",
            "connectivity": [],
        })

        report = validate_packs(str(temp_ecosystem))
        pr_errors = [e for e in report.errors if "provides_runtime" in e]
        assert len(pr_errors) >= 1

    def test_runtime_type_valid_values(self, temp_ecosystem):
        """有効な runtime_type 値はエラーにならない"""
        from core_runtime.pack_validator import validate_packs

        for rt in ["python", "binary", "command"]:
            _create_pack_dir(temp_ecosystem, f"test_rt_{rt}", {
                "pack_id": f"test_rt_{rt}",
                "runtime_type": rt,
                "connectivity": [],
            })

        report = validate_packs(str(temp_ecosystem))
        rt_errors = [e for e in report.errors if "runtime_type" in e]
        assert len(rt_errors) == 0

    def test_runtime_type_invalid_value(self, temp_ecosystem):
        """無効な runtime_type はエラーになる"""
        from core_runtime.pack_validator import validate_packs

        _create_pack_dir(temp_ecosystem, "test_rt_bad", {
            "pack_id": "test_rt_bad",
            "runtime_type": "java",
            "connectivity": [],
        })

        report = validate_packs(str(temp_ecosystem))
        rt_errors = [e for e in report.errors if "runtime_type" in e]
        assert len(rt_errors) >= 1

    def test_runtime_type_default_when_omitted(self, temp_ecosystem):
        """runtime_type 省略時はエラーにならない（デフォルト python）"""
        from core_runtime.pack_validator import validate_packs

        _create_pack_dir(temp_ecosystem, "test_rt_def", {
            "pack_id": "test_rt_def",
            "connectivity": [],
        })

        report = validate_packs(str(temp_ecosystem))
        rt_errors = [e for e in report.errors if "runtime_type" in e]
        assert len(rt_errors) == 0


# ======================================================================
# Wave 2: approval_manager.py テスト
# ======================================================================


class TestRuleApproval:
    """ルール拡張承認フローのテスト"""

    @pytest.fixture
    def temp_dirs(self, tmp_path):
        eco_dir = tmp_path / "ecosystem"
        eco_dir.mkdir()
        grants_dir = tmp_path / "grants"
        grants_dir.mkdir()
        return eco_dir, grants_dir

    def _make_am(self, eco_dir, grants_dir):
        from core_runtime.approval_manager import ApprovalManager
        am = ApprovalManager(
            packs_dir=str(eco_dir),
            grants_dir=str(grants_dir),
            secret_key="test_secret_key_for_testing_only",
        )
        am.initialize()
        return am

    def test_approve_rule_success(self, temp_dirs):
        """rule Pack の approve -> approve_rule フローが成功する"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_rule", {
            "pack_id": "my_rule",
            "pack_type": "rule",
            "provides_runtime": ["binary"],
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()

        result1 = am.approve("my_rule")
        assert result1.success is True

        result2 = am.approve_rule("my_rule")
        assert result2.success is True

        assert am.is_rule_approved("my_rule") is True

    def test_approve_rule_not_approved_first(self, temp_dirs):
        """通常承認前に approve_rule を呼ぶとエラー"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_rule2", {
            "pack_id": "my_rule2",
            "pack_type": "rule",
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()

        result = am.approve_rule("my_rule2")
        assert result.success is False
        assert "approved first" in result.error

    def test_approve_rule_on_application_pack(self, temp_dirs):
        """application Pack に approve_rule を呼ぶとエラー"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_app", {
            "pack_id": "my_app",
            "pack_type": "application",
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()
        am.approve("my_app")

        result = am.approve_rule("my_app")
        assert result.success is False
        assert "only valid for pack_type" in result.error

    def test_approve_rule_on_default_pack_type(self, temp_dirs):
        """pack_type 省略（デフォルト application）の Pack に approve_rule はエラー"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_default", {
            "pack_id": "my_default",
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()
        am.approve("my_default")

        result = am.approve_rule("my_default")
        assert result.success is False

    def test_is_rule_approved_non_rule_pack(self, temp_dirs):
        """rule でない Pack の is_rule_approved は True（不要だから）"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_app2", {
            "pack_id": "my_app2",
            "pack_type": "application",
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()
        am.approve("my_app2")

        assert am.is_rule_approved("my_app2") is True

    def test_is_rule_approved_unapproved_rule(self, temp_dirs):
        """rule Pack が通常承認のみの場合 is_rule_approved は False"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_rule3", {
            "pack_id": "my_rule3",
            "pack_type": "rule",
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()
        am.approve("my_rule3")

        assert am.is_rule_approved("my_rule3") is False

    def test_approve_rule_not_found(self, temp_dirs):
        """存在しない Pack に approve_rule を呼ぶとエラー"""
        eco_dir, grants_dir = temp_dirs
        am = self._make_am(eco_dir, grants_dir)

        result = am.approve_rule("nonexistent")
        assert result.success is False
        assert "not found" in result.error

    def test_rule_approved_persisted(self, temp_dirs):
        """ルール拡張承認が grants.json に永続化される"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_rule_p", {
            "pack_id": "my_rule_p",
            "pack_type": "rule",
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()
        am.approve("my_rule_p")
        am.approve_rule("my_rule_p")

        # 新しい AM インスタンスで読み込み
        am2 = self._make_am(eco_dir, grants_dir)
        approval = am2.get_approval("my_rule_p")
        assert approval is not None
        assert approval.rule_approved is True
        assert approval.rule_approved_at is not None

    def test_version_history_records_approve_rule(self, temp_dirs):
        """approve_rule がバージョン履歴に記録される"""
        eco_dir, grants_dir = temp_dirs
        _create_pack_dir(eco_dir, "my_rule_vh", {
            "pack_id": "my_rule_vh",
            "pack_type": "rule",
        })

        am = self._make_am(eco_dir, grants_dir)
        am.scan_packs()
        am.approve("my_rule_vh")
        am.approve_rule("my_rule_vh")

        history = am.get_version_history("my_rule_vh")
        actions = [h["action"] for h in history]
        assert "approve" in actions
        assert "approve_rule" in actions


# ======================================================================
# Wave 3: dependency_resolver.py テスト
# ======================================================================


class TestValidateRuleDependencies:
    """validate_rule_dependencies のテスト"""

    def test_no_issues_when_all_approved(self):
        """全て承認済みなら問題なし"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "rule_a": {"pack_type": "rule", "provides_runtime": ["binary"]},
            "app_b": {
                "pack_type": "application",
                "depends_on": [{"pack_id": "rule_a"}],
            },
        }

        mock_am = MagicMock()
        mock_am.is_pack_approved_and_verified.return_value = (True, None)
        mock_am.is_rule_approved.return_value = True

        issues = validate_rule_dependencies(packs, approval_manager=mock_am)
        assert len(issues) == 0

    def test_rule_not_approved(self):
        """rule Pack が通常承認されていない場合"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "rule_a": {"pack_type": "rule"},
            "app_b": {
                "pack_type": "application",
                "depends_on": [{"pack_id": "rule_a"}],
            },
        }

        mock_am = MagicMock()
        mock_am.is_pack_approved_and_verified.return_value = (False, "not_approved")
        mock_am.is_rule_approved.return_value = False

        issues = validate_rule_dependencies(packs, approval_manager=mock_am)
        rule_issues = [i for i in issues if i["type"] == "rule_not_approved"]
        assert len(rule_issues) >= 1
        assert rule_issues[0]["rule_pack_id"] == "rule_a"

    def test_rule_not_rule_approved(self):
        """rule Pack が通常承認済みだがルール拡張承認されていない場合"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "rule_a": {"pack_type": "rule"},
            "app_b": {
                "pack_type": "application",
                "depends_on": [{"pack_id": "rule_a"}],
            },
        }

        mock_am = MagicMock()
        mock_am.is_pack_approved_and_verified.return_value = (True, None)
        mock_am.is_rule_approved.return_value = False

        issues = validate_rule_dependencies(packs, approval_manager=mock_am)
        rr_issues = [i for i in issues if i["type"] == "rule_not_rule_approved"]
        assert len(rr_issues) >= 1

    def test_missing_binary_provider(self):
        """runtime_type binary で binary provider が依存にない場合"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "app_bin": {
                "pack_type": "application",
                "runtime_type": "binary",
                "depends_on": [],
            },
        }

        issues = validate_rule_dependencies(packs)
        bin_issues = [i for i in issues if i["type"] == "missing_binary_provider"]
        assert len(bin_issues) >= 1
        assert bin_issues[0]["pack_id"] == "app_bin"

    def test_binary_provider_present(self):
        """runtime_type binary で binary provider が依存に含まれる場合は OK"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "rule_bin": {
                "pack_type": "rule",
                "provides_runtime": ["binary"],
            },
            "app_bin": {
                "pack_type": "application",
                "runtime_type": "binary",
                "depends_on": [{"pack_id": "rule_bin"}],
            },
        }

        issues = validate_rule_dependencies(packs)
        bin_issues = [i for i in issues if i["type"] == "missing_binary_provider"]
        assert len(bin_issues) == 0

    def test_no_approval_manager_skips_approval_check(self):
        """approval_manager が None なら承認チェックをスキップ"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "rule_a": {"pack_type": "rule"},
            "app_b": {
                "pack_type": "application",
                "depends_on": [{"pack_id": "rule_a"}],
            },
        }

        issues = validate_rule_dependencies(packs, approval_manager=None)
        approval_issues = [
            i for i in issues
            if i["type"] in ("rule_not_approved", "rule_not_rule_approved")
        ]
        assert len(approval_issues) == 0

    def test_python_runtime_no_binary_check(self):
        """runtime_type python はバイナリプロバイダチェック不要"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "app_py": {
                "pack_type": "application",
                "runtime_type": "python",
                "depends_on": [],
            },
        }

        issues = validate_rule_dependencies(packs)
        bin_issues = [i for i in issues if i["type"] == "missing_binary_provider"]
        assert len(bin_issues) == 0

    def test_default_runtime_type_no_binary_check(self):
        """runtime_type 省略時はバイナリプロバイダチェック不要"""
        from core_runtime.dependency_resolver import validate_rule_dependencies

        packs = {
            "app_default": {
                "pack_type": "application",
                "depends_on": [],
            },
        }

        issues = validate_rule_dependencies(packs)
        bin_issues = [i for i in issues if i["type"] == "missing_binary_provider"]
        assert len(bin_issues) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
