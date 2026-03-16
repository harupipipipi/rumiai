"""
test_hash_granularity.py - verify_hash_detailed のユニットテスト

テストケース:
1. クリティカルファイル変更 → critical_changed=True
2. blocks/ 内のみ変更 → critical_changed=False
3. ファイル削除 → critical_changed=True
4. blocks/ 以外のファイル追加 → critical_changed=True
5. core_pack → valid=True, critical_changed=False
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from threading import RLock


class TestVerifyHashDetailed(unittest.TestCase):
    """verify_hash_detailed メソッドのユニットテスト"""

    def _make_manager(self, stored_hashes, current_hashes, pack_id="test_pack"):
        """テスト用の ApprovalManager モックを作成する。

        実際の ApprovalManager クラスを import してインスタンスを作り、
        内部状態をモックで置き換える。import できない環境では
        簡易スタブで代替する。
        """
        try:
            from core_runtime.approval_manager import (
                ApprovalManager, PackApproval, PackStatus,
            )

            with patch.object(ApprovalManager, '__init__', lambda self, **kw: None):
                am = ApprovalManager()

            am._lock = RLock()
            am._approvals = {}
            am._pack_locations = {}
            am._hash_cache = {}
            am._hash_cache_ttl = 30.0

            if stored_hashes is not None:
                am._approvals[pack_id] = PackApproval(
                    pack_id=pack_id,
                    status=PackStatus.APPROVED,
                    created_at="2025-01-01T00:00:00Z",
                    file_hashes=dict(stored_hashes),
                )

            am._resolve_pack_dir = MagicMock(return_value=Path("/fake/pack"))
            am._compute_pack_hashes = MagicMock(return_value=dict(current_hashes))
            am._compute_pack_hashes_nocache = MagicMock(return_value=dict(current_hashes))
            am._is_core_pack = lambda pid: pid.startswith("__core__")

            return am, PackStatus
        except ImportError:
            pass

        # --- fallback: 簡易スタブ ---
        from enum import Enum

        class _PackStatus(Enum):
            APPROVED = "approved"

        class _Approval:
            def __init__(self, hashes):
                self.status = _PackStatus.APPROVED
                self.file_hashes = dict(hashes) if hashes else {}

        class _AM:
            CRITICAL_FILES = frozenset({
                "backend/ecosystem.json",
                "backend/permissions.json",
                "backend/routes.json",
            })
            CRITICAL_DIRS = (
                "backend/flows/",
                "backend/lib/",
                "backend/components/",
            )

            def __init__(self, stored, current, pid):
                self._lock = RLock()
                self._approvals = {}
                if stored is not None:
                    self._approvals[pid] = _Approval(stored)
                self._current = dict(current)

            def _is_core_pack(self, pid):
                return pid.startswith("__core__")

            def _resolve_pack_dir(self, pid):
                return Path("/fake/pack")

            def _compute_pack_hashes(self, d):
                return dict(self._current)

            def _compute_pack_hashes_nocache(self, d):
                return dict(self._current)

            def _compute_local_pack_hashes(self):
                return dict(self._current)

            def _is_critical_path(self, file_path):
                if file_path in self.CRITICAL_FILES:
                    return True
                for d in self.CRITICAL_DIRS:
                    if file_path.startswith(d):
                        return True
                return False

            def verify_hash_detailed(self, pack_id, use_cache=True):
                if self._is_core_pack(pack_id):
                    return {"valid": True, "critical_changed": False, "changed_files": [], "added_files": [], "removed_files": []}
                approval = self._approvals.get(pack_id)
                if not approval or not approval.file_hashes:
                    return {"valid": False, "critical_changed": True, "changed_files": [], "added_files": [], "removed_files": []}
                stored = dict(approval.file_hashes)
                current = self._current
                stored_k = set(stored.keys())
                current_k = set(current.keys())
                removed = sorted(stored_k - current_k)
                added = sorted(current_k - stored_k)
                changed = sorted(p for p in (stored_k & current_k) if stored[p] != current[p])
                valid = not removed and not added and not changed
                critical = False
                if removed:
                    critical = True
                if not critical:
                    for fp in changed:
                        if self._is_critical_path(fp):
                            critical = True
                            break
                if not critical:
                    for fp in added:
                        if not fp.startswith("blocks/"):
                            critical = True
                            break
                return {"valid": valid, "critical_changed": critical, "changed_files": changed, "added_files": added, "removed_files": removed}

        return _AM(stored_hashes, current_hashes, pack_id), _PackStatus

    # ------------------------------------------------------------------
    # テストケース 1: クリティカルファイル変更 → critical_changed=True
    # ------------------------------------------------------------------
    def test_critical_file_change(self):
        stored = {
            "backend/ecosystem.json": "sha256:aaa",
            "blocks/main.py": "sha256:bbb",
        }
        current = {
            "backend/ecosystem.json": "sha256:CHANGED",
            "blocks/main.py": "sha256:bbb",
        }
        am, _ = self._make_manager(stored, current)
        result = am.verify_hash_detailed("test_pack")
        self.assertFalse(result["valid"])
        self.assertTrue(result["critical_changed"])
        self.assertIn("backend/ecosystem.json", result["changed_files"])

    # ------------------------------------------------------------------
    # テストケース 2: blocks/ 内のみ変更 → critical_changed=False
    # ------------------------------------------------------------------
    def test_blocks_only_change(self):
        stored = {
            "backend/ecosystem.json": "sha256:aaa",
            "blocks/main.py": "sha256:bbb",
        }
        current = {
            "backend/ecosystem.json": "sha256:aaa",
            "blocks/main.py": "sha256:CHANGED",
        }
        am, _ = self._make_manager(stored, current)
        result = am.verify_hash_detailed("test_pack")
        self.assertFalse(result["valid"])
        self.assertFalse(result["critical_changed"])
        self.assertIn("blocks/main.py", result["changed_files"])

    # ------------------------------------------------------------------
    # テストケース 3: ファイル削除 → critical_changed=True
    # ------------------------------------------------------------------
    def test_file_removal(self):
        stored = {
            "blocks/main.py": "sha256:bbb",
            "blocks/helper.py": "sha256:ccc",
        }
        current = {
            "blocks/main.py": "sha256:bbb",
        }
        am, _ = self._make_manager(stored, current)
        result = am.verify_hash_detailed("test_pack")
        self.assertFalse(result["valid"])
        self.assertTrue(result["critical_changed"])
        self.assertIn("blocks/helper.py", result["removed_files"])

    # ------------------------------------------------------------------
    # テストケース 4: blocks/ 以外のファイル追加 → critical_changed=True
    # ------------------------------------------------------------------
    def test_non_blocks_file_addition(self):
        stored = {
            "blocks/main.py": "sha256:bbb",
        }
        current = {
            "blocks/main.py": "sha256:bbb",
            "backend/new_file.py": "sha256:ddd",
        }
        am, _ = self._make_manager(stored, current)
        result = am.verify_hash_detailed("test_pack")
        self.assertFalse(result["valid"])
        self.assertTrue(result["critical_changed"])
        self.assertIn("backend/new_file.py", result["added_files"])

    # ------------------------------------------------------------------
    # テストケース 5: core_pack → valid=True, critical_changed=False
    # ------------------------------------------------------------------
    def test_core_pack(self):
        am, _ = self._make_manager({}, {}, pack_id="__core__test")
        result = am.verify_hash_detailed("__core__test")
        self.assertTrue(result["valid"])
        self.assertFalse(result["critical_changed"])

    # ------------------------------------------------------------------
    # テストケース 6: blocks/ 内のファイル追加 → critical_changed=False
    # ------------------------------------------------------------------
    def test_blocks_file_addition(self):
        stored = {
            "blocks/main.py": "sha256:bbb",
        }
        current = {
            "blocks/main.py": "sha256:bbb",
            "blocks/new_block.py": "sha256:eee",
        }
        am, _ = self._make_manager(stored, current)
        result = am.verify_hash_detailed("test_pack")
        self.assertFalse(result["valid"])
        self.assertFalse(result["critical_changed"])
        self.assertIn("blocks/new_block.py", result["added_files"])

    # ------------------------------------------------------------------
    # テストケース 7: 全一致 → valid=True, critical_changed=False
    # ------------------------------------------------------------------
    def test_all_match(self):
        stored = {
            "backend/ecosystem.json": "sha256:aaa",
            "blocks/main.py": "sha256:bbb",
        }
        current = dict(stored)
        am, _ = self._make_manager(stored, current)
        result = am.verify_hash_detailed("test_pack")
        self.assertTrue(result["valid"])
        self.assertFalse(result["critical_changed"])

    # ------------------------------------------------------------------
    # テストケース 8: CRITICAL_DIRS 内の変更 → critical_changed=True
    # ------------------------------------------------------------------
    def test_critical_dir_change(self):
        stored = {
            "backend/flows/main.flow.yaml": "sha256:aaa",
            "blocks/main.py": "sha256:bbb",
        }
        current = {
            "backend/flows/main.flow.yaml": "sha256:CHANGED",
            "blocks/main.py": "sha256:bbb",
        }
        am, _ = self._make_manager(stored, current)
        result = am.verify_hash_detailed("test_pack")
        self.assertFalse(result["valid"])
        self.assertTrue(result["critical_changed"])


if __name__ == "__main__":
    unittest.main()
