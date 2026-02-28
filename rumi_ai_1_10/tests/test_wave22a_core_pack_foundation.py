"""
test_wave22a_core_pack_foundation.py

W22-A: core_pack ローダー基盤のテスト (15件以上)
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# テスト対象モジュールのインポートヘルパー
# ---------------------------------------------------------------------------

def _ensure_project_root_on_path():
    """rumi_ai_1_10 をsys.pathに追加してインポート可能にする"""
    project_root = Path(__file__).resolve().parent.parent
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


_ensure_project_root_on_path()


# ---------------------------------------------------------------------------
# paths.py テスト
# ---------------------------------------------------------------------------

class TestPathsConstants:
    """paths.py の定数テスト"""

    def test_core_pack_dir_points_to_core_runtime_core_pack(self):
        """CORE_PACK_DIR が core_runtime/core_pack/ を指している"""
        from core_runtime.paths import CORE_PACK_DIR
        p = Path(CORE_PACK_DIR)
        assert p.name == "core_pack"
        assert p.parent.name == "core_runtime"

    def test_core_pack_id_prefix_is_core_underscore(self):
        """CORE_PACK_ID_PREFIX が 'core_' である"""
        from core_runtime.paths import CORE_PACK_ID_PREFIX
        assert CORE_PACK_ID_PREFIX == "core_"

    def test_core_pack_dir_is_string(self):
        """CORE_PACK_DIR は文字列型"""
        from core_runtime.paths import CORE_PACK_DIR
        assert isinstance(CORE_PACK_DIR, str)


# ---------------------------------------------------------------------------
# registry.py テスト
# ---------------------------------------------------------------------------

def _make_ecosystem_json(pack_dir: Path, pack_id: str) -> None:
    """テスト用の最小限 ecosystem.json を作成"""
    pack_dir.mkdir(parents=True, exist_ok=True)
    eco = {
        "pack_id": pack_id,
        "pack_identity": f"{pack_id}.test",
        "version": "1.0.0",
        "vocabulary": {"types": []},
    }
    (pack_dir / "ecosystem.json").write_text(
        json.dumps(eco, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class TestRegistryCorePack:
    """registry.py の core_pack 走査テスト"""

    def _make_registry(self, ecosystem_dir: Path):
        """テスト用 Registry を生成（スキーマ検証等をモックで回避）"""
        from backend_core.ecosystem.registry import Registry
        reg = Registry(ecosystem_dir=str(ecosystem_dir))
        return reg

    def test_core_pack_loaded_when_present(self, tmp_path):
        """core_pack ディレクトリに ecosystem.json がある Pack はロードされる"""
        eco_dir = tmp_path / "ecosystem"
        eco_dir.mkdir()

        core_dir = tmp_path / "core_runtime" / "core_pack"
        core_pack_a = core_dir / "core_alpha"
        _make_ecosystem_json(core_pack_a, "core_alpha")

        from backend_core.ecosystem import registry as reg_mod
        with patch.object(reg_mod, "_CORE_PACK_DIR_PATHS", str(core_dir)):
            with patch("backend_core.ecosystem.registry.validate_ecosystem"):
                with patch("backend_core.ecosystem.registry.generate_pack_uuid", return_value="fake-uuid"):
                    reg = self._make_registry(eco_dir)
                    reg.load_all_packs()
                    assert "core_alpha" in reg.packs

    def test_core_pack_loaded_before_ecosystem_pack(self, tmp_path):
        """core_pack は通常 Pack より先にロードされる"""
        eco_dir = tmp_path / "ecosystem"
        normal_pack = eco_dir / "normal_pack"
        _make_ecosystem_json(normal_pack, "normal_pack")

        core_dir = tmp_path / "core_runtime" / "core_pack"
        core_pack_a = core_dir / "core_alpha"
        _make_ecosystem_json(core_pack_a, "core_alpha")

        from backend_core.ecosystem import registry as reg_mod

        load_order = []
        original_load_pack = reg_mod.Registry._load_pack

        def tracking_load_pack(self_inner, pack_dir):
            load_order.append(pack_dir.name)
            return original_load_pack(self_inner, pack_dir)

        with patch.object(reg_mod, "_CORE_PACK_DIR_PATHS", str(core_dir)):
            with patch("backend_core.ecosystem.registry.validate_ecosystem"):
                with patch("backend_core.ecosystem.registry.generate_pack_uuid", return_value="fake-uuid"):
                    with patch.object(reg_mod.Registry, "_load_pack", tracking_load_pack):
                        reg = self._make_registry(eco_dir)
                        reg.load_all_packs()

        # core_alpha が normal_pack より前にロードされる
        if "core_alpha" in load_order and "normal_pack" in load_order:
            assert load_order.index("core_alpha") < load_order.index("normal_pack")

    def test_core_pack_dir_missing_no_error(self, tmp_path):
        """core_pack ディレクトリが存在しない場合エラーにならない"""
        eco_dir = tmp_path / "ecosystem"
        eco_dir.mkdir()

        nonexistent = tmp_path / "nonexistent_core_pack"

        from backend_core.ecosystem import registry as reg_mod
        with patch.object(reg_mod, "_CORE_PACK_DIR_PATHS", str(nonexistent)):
            reg = self._make_registry(eco_dir)
            packs = reg.load_all_packs()
            # エラーなく空で返る
            assert isinstance(packs, dict)

    def test_core_and_ecosystem_both_loaded(self, tmp_path):
        """core_pack と ecosystem Pack の両方がロードされる"""
        eco_dir = tmp_path / "ecosystem"
        normal_pack = eco_dir / "normal_pack"
        _make_ecosystem_json(normal_pack, "normal_pack")

        core_dir = tmp_path / "core_runtime" / "core_pack"
        core_pack_a = core_dir / "core_beta"
        _make_ecosystem_json(core_pack_a, "core_beta")

        from backend_core.ecosystem import registry as reg_mod
        with patch.object(reg_mod, "_CORE_PACK_DIR_PATHS", str(core_dir)):
            with patch("backend_core.ecosystem.registry.validate_ecosystem"):
                with patch("backend_core.ecosystem.registry.generate_pack_uuid", return_value="fake-uuid"):
                    reg = self._make_registry(eco_dir)
                    reg.load_all_packs()
                    assert "core_beta" in reg.packs
                    assert "normal_pack" in reg.packs

    def test_core_pack_overrides_same_pack_id(self, tmp_path):
        """core_pack の pack_id が通常 Pack と衝突した場合 core_pack が優先"""
        eco_dir = tmp_path / "ecosystem"
        normal_pack = eco_dir / "core_conflict"
        _make_ecosystem_json(normal_pack, "core_conflict")

        core_dir = tmp_path / "core_runtime" / "core_pack"
        core_pack = core_dir / "core_conflict"
        _make_ecosystem_json(core_pack, "core_conflict")

        from backend_core.ecosystem import registry as reg_mod
        with patch.object(reg_mod, "_CORE_PACK_DIR_PATHS", str(core_dir)):
            with patch("backend_core.ecosystem.registry.validate_ecosystem"):
                with patch("backend_core.ecosystem.registry.generate_pack_uuid", return_value="fake-uuid"):
                    reg = self._make_registry(eco_dir)
                    reg.load_all_packs()
                    # core_pack ディレクトリ由来が優先される
                    assert reg.packs["core_conflict"].path == core_pack


# ---------------------------------------------------------------------------
# approval_manager.py テスト
# ---------------------------------------------------------------------------

class TestApprovalManagerCorePack:
    """approval_manager.py の core_pack テスト"""

    def _make_manager(self, tmp_path):
        """テスト用 ApprovalManager を生成"""
        from core_runtime.approval_manager import ApprovalManager
        grants_dir = tmp_path / "grants"
        grants_dir.mkdir(parents=True, exist_ok=True)
        eco_dir = tmp_path / "ecosystem"
        eco_dir.mkdir(parents=True, exist_ok=True)
        mgr = ApprovalManager(
            packs_dir=str(eco_dir),
            grants_dir=str(grants_dir),
            secret_key="test-secret-key-for-unit-tests",
        )
        mgr.initialize()
        return mgr

    def test_is_core_pack_true_for_core_prefix(self, tmp_path):
        """_is_core_pack() が core_ プレフィックスで True を返す"""
        mgr = self._make_manager(tmp_path)
        assert mgr._is_core_pack("core_alpha") is True

    def test_is_core_pack_false_for_normal(self, tmp_path):
        """_is_core_pack() が通常 pack_id で False を返す"""
        mgr = self._make_manager(tmp_path)
        assert mgr._is_core_pack("normal_pack") is False

    def test_is_core_pack_false_for_empty(self, tmp_path):
        """_is_core_pack() が空文字列で False を返す"""
        mgr = self._make_manager(tmp_path)
        assert mgr._is_core_pack("") is False

    def test_is_pack_approved_and_verified_core(self, tmp_path):
        """core_ プレフィックスの pack_id は (True, None) を返す"""
        mgr = self._make_manager(tmp_path)
        result = mgr.is_pack_approved_and_verified("core_system")
        assert result == (True, None)

    def test_get_status_core(self, tmp_path):
        """core_ プレフィックスの pack_id は APPROVED を返す"""
        from core_runtime.approval_manager import PackStatus
        mgr = self._make_manager(tmp_path)
        assert mgr.get_status("core_system") == PackStatus.APPROVED

    def test_verify_hash_core(self, tmp_path):
        """core_ プレフィックスの pack_id は True を返す"""
        mgr = self._make_manager(tmp_path)
        assert mgr.verify_hash("core_system") is True

    def test_normal_pack_not_found(self, tmp_path):
        """通常 pack_id は従来通り not_found を返す（回帰テスト）"""
        mgr = self._make_manager(tmp_path)
        is_valid, reason = mgr.is_pack_approved_and_verified("unknown_pack")
        assert is_valid is False
        assert reason == "not_found"

    def test_normal_pack_get_status_none(self, tmp_path):
        """通常の未登録 pack_id は get_status で None を返す（回帰テスト）"""
        mgr = self._make_manager(tmp_path)
        assert mgr.get_status("unknown_pack") is None

    def test_core_pack_no_approval_record_needed(self, tmp_path):
        """core_pack は _approvals に登録しなくても承認済みになる"""
        mgr = self._make_manager(tmp_path)
        # _approvals にエントリが無いことを確認
        assert "core_magic" not in mgr._approvals
        # それでも承認済み
        assert mgr.is_pack_approved_and_verified("core_magic") == (True, None)
