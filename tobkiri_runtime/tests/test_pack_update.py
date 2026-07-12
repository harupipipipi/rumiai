"""
test_pack_update.py - G-1, G-2, G-3 のテスト

G-1: pack.update パーミッションチェック
G-2: apply_update のハッシュ比較
G-3: バージョン履歴とロールバック
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core_runtime.approval_manager import (
    ApprovalManager,
    PackApproval,
    PackStatus,
)
from core_runtime.permission_manager import PermissionManager


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture()
def tmp_dirs(tmp_path):
    packs_dir = tmp_path / "ecosystem"
    grants_dir = tmp_path / "grants"
    packs_dir.mkdir()
    grants_dir.mkdir()
    return packs_dir, grants_dir


@pytest.fixture()
def secret_key():
    return "test-secret-key-for-pack-update"


@pytest.fixture()
def am(tmp_dirs, secret_key):
    packs_dir, grants_dir = tmp_dirs
    return ApprovalManager(
        packs_dir=str(packs_dir),
        grants_dir=str(grants_dir),
        secret_key=secret_key,
    )


@pytest.fixture()
def pm():
    return PermissionManager(mode="permissive")


@pytest.fixture()
def approved_pack(am, tmp_dirs):
    """APPROVED 状態の Pack を準備"""
    packs_dir, _ = tmp_dirs
    pack_dir = packs_dir / "update_pack"
    pack_dir.mkdir()
    (pack_dir / "ecosystem.json").write_text(
        json.dumps({"pack_id": "update_pack"}), encoding="utf-8",
    )
    (pack_dir / "main.py").write_text("print('hello')", encoding="utf-8")

    # _pack_locations に簡易ロケーションを登録
    class _FakeLoc:
        def __init__(self, d):
            self.pack_dir = d
    am._pack_locations["update_pack"] = _FakeLoc(pack_dir)

    am._approvals["update_pack"] = PackApproval(
        pack_id="update_pack",
        status=PackStatus.INSTALLED,
        created_at="2025-01-01T00:00:00Z",
    )
    result = am.approve("update_pack")
    assert result.success
    return am, "update_pack"


# ------------------------------------------------------------------ #
# G-1: pack.update パーミッションチェック
# ------------------------------------------------------------------ #

class TestPackUpdatePermission:
    """G-1: check_permission で pack.update を判定"""

    def test_approved_pack_update_allowed(self, pm, approved_pack):
        """APPROVED Pack に対する pack.update は許可"""
        am, pack_id = approved_pack

        with patch(
            "core_runtime.approval_manager.get_approval_manager",
            return_value=am,
        ):
            result = pm.check_permission("admin", "pack.update", pack_id)
        assert result is True

    def test_non_approved_pack_update_denied(self, pm, am):
        """APPROVED でない Pack に対する pack.update は拒否"""
        am._approvals["pending_pack"] = PackApproval(
            pack_id="pending_pack",
            status=PackStatus.INSTALLED,
            created_at="2025-01-01T00:00:00Z",
        )

        with patch(
            "core_runtime.approval_manager.get_approval_manager",
            return_value=am,
        ):
            result = pm.check_permission("admin", "pack.update", "pending_pack")
        assert result is False

    def test_unknown_pack_update_denied(self, pm, am):
        """存在しない Pack に対する pack.update は拒否"""
        with patch(
            "core_runtime.approval_manager.get_approval_manager",
            return_value=am,
        ):
            result = pm.check_permission("admin", "pack.update", "nonexistent")
        assert result is False

    def test_secure_mode_requires_grant(self, approved_pack):
        """secure モードでは pack.update の grant も必要"""
        am, pack_id = approved_pack
        pm_secure = PermissionManager(mode="secure")

        with patch(
            "core_runtime.approval_manager.get_approval_manager",
            return_value=am,
        ):
            # grant なし → False
            result = pm_secure.check_permission("admin", "pack.update", pack_id)
        assert result is False

        # grant を付与
        pm_secure.grant("admin", "pack.update")
        with patch(
            "core_runtime.approval_manager.get_approval_manager",
            return_value=am,
        ):
            result = pm_secure.check_permission("admin", "pack.update", pack_id)
        assert result is True


# ------------------------------------------------------------------ #
# G-2: apply_update
# ------------------------------------------------------------------ #

class TestApplyUpdate:
    """G-2: apply_update のハッシュ比較"""

    def test_matching_hashes_keeps_approved(self, approved_pack):
        """ハッシュ一致で APPROVED 維持"""
        am, pack_id = approved_pack
        current_hashes = dict(am._approvals[pack_id].file_hashes)

        result = am.apply_update(pack_id, current_hashes)
        assert result.success
        assert am.get_status(pack_id) == PackStatus.APPROVED

    def test_mismatching_hashes_marks_modified(self, approved_pack):
        """ハッシュ不一致で MODIFIED"""
        am, pack_id = approved_pack

        new_hashes = {
            "main.py": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        }
        result = am.apply_update(pack_id, new_hashes)
        assert result.success
        assert result.status == PackStatus.MODIFIED
        assert am.get_status(pack_id) == PackStatus.MODIFIED

    def test_apply_update_unknown_pack(self, am):
        """存在しない Pack に対する apply_update"""
        result = am.apply_update("nonexistent", {})
        assert not result.success
        assert "not found" in result.error.lower()


# ------------------------------------------------------------------ #
# G-3: version history / rollback
# ------------------------------------------------------------------ #

class TestVersionHistory:
    """G-3: バージョン履歴の記録と取得"""

    def test_approve_creates_version_entry(self, approved_pack):
        """approve() でバージョン履歴が記録される"""
        am, pack_id = approved_pack
        history = am.get_version_history(pack_id)

        assert len(history) >= 1
        latest = history[-1]
        assert latest["action"] == "approve"
        assert "file_hashes" in latest
        assert "timestamp" in latest
        assert "version" in latest

    def test_multiple_approvals_accumulate(self, approved_pack):
        """複数回の approve でバージョン履歴が蓄積される"""
        am, pack_id = approved_pack

        # 2回目の approve
        am._approvals[pack_id].status = PackStatus.MODIFIED
        result = am.approve(pack_id)
        assert result.success

        history = am.get_version_history(pack_id)
        assert len(history) >= 2

    def test_empty_history_for_unknown_pack(self, am):
        """存在しない Pack の履歴は空リスト"""
        assert am.get_version_history("nonexistent") == []


class TestRollback:
    """G-3: ロールバック"""

    def test_rollback_to_version(self, approved_pack):
        """指定バージョンにロールバックできる"""
        am, pack_id = approved_pack

        # 初回の approve のハッシュを記録
        history_v1 = am.get_version_history(pack_id)
        v1_hashes = history_v1[0]["file_hashes"]

        # 更新で MODIFIED にする
        new_hashes = {"main.py": "sha256:aaaa"}
        am.apply_update(pack_id, new_hashes)
        assert am.get_status(pack_id) == PackStatus.MODIFIED

        # ロールバック
        result = am.rollback_to_version(pack_id, 0)
        assert result.success
        assert result.status == PackStatus.APPROVED
        assert am.get_status(pack_id) == PackStatus.APPROVED
        assert am._approvals[pack_id].file_hashes == v1_hashes

        # 履歴にロールバックイベントが記録されている
        history = am.get_version_history(pack_id)
        rollback_entry = history[-1]
        assert rollback_entry["action"] == "rollback"
        assert rollback_entry["rollback_to_version_index"] == 0

    def test_rollback_invalid_index(self, approved_pack):
        """無効なインデックスでロールバックするとエラー"""
        am, pack_id = approved_pack

        result = am.rollback_to_version(pack_id, 999)
        assert not result.success
        assert "invalid" in result.error.lower()

    def test_rollback_unknown_pack(self, am):
        """存在しない Pack にロールバックするとエラー"""
        result = am.rollback_to_version("nonexistent", 0)
        assert not result.success
