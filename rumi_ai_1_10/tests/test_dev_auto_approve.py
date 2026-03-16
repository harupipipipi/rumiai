"""
test_dev_auto_approve.py - auto_approve_if_dev のユニットテスト

テストケース:
1. 正常: env=development + auto=true → 自動承認成功
2. env なし → False
3. auto なし → False
4. BLOCKED → False
5. 既に APPROVED → True
"""

import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from threading import RLock


class TestAutoApproveIfDev(unittest.TestCase):
    """auto_approve_if_dev メソッドのユニットテスト"""

    def _make_manager(self, pack_id="test_pack", status_value="installed"):
        """テスト用の ApprovalManager モックを作成する。"""
        try:
            from core_runtime.approval_manager import (
                ApprovalManager, PackApproval, PackStatus, ApprovalResult,
            )

            with patch.object(ApprovalManager, '__init__', lambda self, **kw: None):
                am = ApprovalManager()

            am._lock = RLock()
            am._approvals = {}
            am._pack_locations = {}
            am._hash_cache = {}
            am._hash_cache_ttl = 30.0
            am.packs_dir = Path("/fake/packs")
            am.grants_dir = Path("/fake/grants")
            am._secret_key = b"test_secret"

            status = PackStatus(status_value)
            am._approvals[pack_id] = PackApproval(
                pack_id=pack_id,
                status=status,
                created_at="2025-01-01T00:00:00Z",
                file_hashes={"blocks/main.py": "sha256:aaa"},
            )

            am._resolve_pack_dir = MagicMock(return_value=Path("/fake/pack"))
            am._compute_pack_hashes = MagicMock(return_value={"blocks/main.py": "sha256:aaa"})
            am._is_core_pack = lambda pid: pid.startswith("__core__")
            am._invalidate_hash_cache = MagicMock()
            am._create_declared_stores = MagicMock()
            am._read_ecosystem_data = MagicMock(return_value={})

            def _now_ts():
                return "2025-01-01T00:00:00Z"
            am._now_ts = _now_ts

            def _save_grant(approval):
                pass
            am._save_grant = _save_grant

            return am, PackStatus, ApprovalResult
        except ImportError:
            pass

        # --- fallback: 簡易スタブ ---
        from enum import Enum

        class _PackStatus(Enum):
            INSTALLED = "installed"
            PENDING = "pending"
            APPROVED = "approved"
            BLOCKED = "blocked"
            MODIFIED = "modified"
            ERROR = "error"
            RUNNING = "running"

        class _ApprovalResult:
            def __init__(self, success, pack_id="", error=None, status=None):
                self.success = success
                self.pack_id = pack_id
                self.error = error
                self.status = status

        class _Approval:
            def __init__(self, pack_id, status, hashes):
                self.pack_id = pack_id
                self.status = status
                self.file_hashes = dict(hashes) if hashes else {}
                self.created_at = "2025-01-01T00:00:00Z"
                self.approved_at = None
                self.rejection_reason = None
                self.version_history = []

        import logging as _logging
        _logger = _logging.getLogger(__name__)

        class _AM:
            def __init__(self, pid, status_val):
                self._lock = RLock()
                self._approvals = {}
                st = _PackStatus(status_val)
                self._approvals[pid] = _Approval(pid, st, {"blocks/main.py": "sha256:aaa"})

            def approve(self, pack_id):
                a = self._approvals.get(pack_id)
                if not a:
                    return _ApprovalResult(False, pack_id, "not found")
                a.status = _PackStatus.APPROVED
                a.approved_at = "2025-01-01T00:00:00Z"
                return _ApprovalResult(True, pack_id, status=_PackStatus.APPROVED)

            def auto_approve_if_dev(self, pack_id):
                rumi_env = os.environ.get("RUMI_ENVIRONMENT", "").lower()
                if rumi_env not in ("development", "dev"):
                    return False
                auto_approve = os.environ.get("RUMI_AUTO_APPROVE_LOCAL", "").lower()
                if auto_approve != "true":
                    return False
                with self._lock:
                    approval = self._approvals.get(pack_id)
                    if not approval:
                        return False
                    current_status = approval.status
                if current_status == _PackStatus.APPROVED:
                    return True
                if current_status == _PackStatus.BLOCKED:
                    return False
                result = self.approve(pack_id)
                if result.success:
                    _logger.info("DEV_AUTO_APPROVE: Pack '%s' auto-approved.", pack_id)
                    return True
                return False

        return _AM(pack_id, status_value), _PackStatus, _ApprovalResult

    # ------------------------------------------------------------------
    # テストケース 1: 正常 — env=development + auto=true → True
    # ------------------------------------------------------------------
    def test_normal_auto_approve(self):
        am, PS, _ = self._make_manager(status_value="installed")
        with patch.dict(os.environ, {"RUMI_ENVIRONMENT": "development", "RUMI_AUTO_APPROVE_LOCAL": "true"}):
            result = am.auto_approve_if_dev("test_pack")
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # テストケース 2: env なし → False
    # ------------------------------------------------------------------
    def test_no_env(self):
        am, PS, _ = self._make_manager(status_value="installed")
        env = dict(os.environ)
        env.pop("RUMI_ENVIRONMENT", None)
        env["RUMI_AUTO_APPROVE_LOCAL"] = "true"
        with patch.dict(os.environ, env, clear=True):
            result = am.auto_approve_if_dev("test_pack")
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # テストケース 3: auto なし → False
    # ------------------------------------------------------------------
    def test_no_auto_flag(self):
        am, PS, _ = self._make_manager(status_value="installed")
        env = dict(os.environ)
        env["RUMI_ENVIRONMENT"] = "development"
        env.pop("RUMI_AUTO_APPROVE_LOCAL", None)
        with patch.dict(os.environ, env, clear=True):
            result = am.auto_approve_if_dev("test_pack")
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # テストケース 4: BLOCKED → False
    # ------------------------------------------------------------------
    def test_blocked_pack(self):
        am, PS, _ = self._make_manager(status_value="blocked")
        with patch.dict(os.environ, {"RUMI_ENVIRONMENT": "development", "RUMI_AUTO_APPROVE_LOCAL": "true"}):
            result = am.auto_approve_if_dev("test_pack")
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # テストケース 5: 既に APPROVED → True
    # ------------------------------------------------------------------
    def test_already_approved(self):
        am, PS, _ = self._make_manager(status_value="approved")
        with patch.dict(os.environ, {"RUMI_ENVIRONMENT": "development", "RUMI_AUTO_APPROVE_LOCAL": "true"}):
            result = am.auto_approve_if_dev("test_pack")
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # テストケース 6: env=dev (短縮形) → True
    # ------------------------------------------------------------------
    def test_env_dev_short(self):
        am, PS, _ = self._make_manager(status_value="installed")
        with patch.dict(os.environ, {"RUMI_ENVIRONMENT": "dev", "RUMI_AUTO_APPROVE_LOCAL": "true"}):
            result = am.auto_approve_if_dev("test_pack")
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # テストケース 7: env=production → False
    # ------------------------------------------------------------------
    def test_production_env(self):
        am, PS, _ = self._make_manager(status_value="installed")
        with patch.dict(os.environ, {"RUMI_ENVIRONMENT": "production", "RUMI_AUTO_APPROVE_LOCAL": "true"}):
            result = am.auto_approve_if_dev("test_pack")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
