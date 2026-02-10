"""
test_capability_installer.py - CapabilityInstaller のテスト

pytest で実行:
    pip install -r requirements-dev.txt
    pytest tests/test_capability_installer.py -v
"""

from __future__ import annotations

import json
import os
import sys
import shutil
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.capability_installer import (
    CapabilityInstaller,
    CandidateStatus,
    reset_capability_installer,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def tmp_ecosystem(tmp_path):
    """
    テスト用 ecosystem ディレクトリを構築する。

    ecosystem/my_pack/share/capability_handlers/fs_read_v1/
        handler.json
        handler.py
    """
    pack_dir = tmp_path / "ecosystem" / "my_pack" / "share" / "capability_handlers" / "fs_read_v1"
    pack_dir.mkdir(parents=True)

    handler_json = {
        "handler_id": "fs_read_handler",
        "permission_id": "fs.read",
        "entrypoint": "handler.py:execute",
        "description": "Test handler",
    }
    (pack_dir / "handler.json").write_text(
        json.dumps(handler_json, indent=2), encoding="utf-8"
    )
    (pack_dir / "handler.py").write_text(
        textwrap.dedent("""\
            def execute(context, args):
                return {"status": "ok"}
        """),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def installer(tmp_path, tmp_ecosystem):
    """テスト用 CapabilityInstaller インスタンスを返す"""
    requests_dir = str(tmp_path / "requests")
    handlers_dest_dir = str(tmp_path / "handlers_dest")

    inst = CapabilityInstaller(
        requests_dir=requests_dir,
        handlers_dest_dir=handlers_dest_dir,
        cooldown_seconds=3600,
        reject_threshold=3,
    )
    return inst


def _get_ecosystem_dir(tmp_path) -> str:
    return str(tmp_path / "ecosystem")


# ======================================================================
# Test 1: scan が pending を作る
# ======================================================================

class TestScanCreatesPending:
    def test_scan_creates_pending(self, installer, tmp_path):
        """scan が候補を検出して pending を作成する"""
        result = installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))

        assert result.scanned_count == 1
        assert result.pending_created == 1
        assert result.skipped_blocked == 0
        assert len(result.errors) == 0

        items = installer.list_items("pending")
        assert len(items) == 1
        assert items[0]["status"] == "pending"
        assert items[0]["candidate"]["handler_id"] == "fs_read_handler"
        assert items[0]["candidate"]["permission_id"] == "fs.read"
        assert items[0]["candidate"]["pack_id"] == "my_pack"
        assert items[0]["candidate"]["slug"] == "fs_read_v1"

    def test_scan_twice_no_duplicate(self, installer, tmp_path):
        """同じ候補を2回 scan しても pending は重複しない"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        result2 = installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))

        assert result2.pending_created == 0
        assert result2.skipped_pending == 1

        items = installer.list_items("pending")
        assert len(items) == 1


# ======================================================================
# Test 2: reject で cooldown が入る（1h）
# ======================================================================

class TestRejectCooldown:
    def test_reject_sets_cooldown(self, installer, tmp_path):
        """reject すると cooldown_until が設定される"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        result = installer.reject(candidate_key, reason="Not needed")

        assert result.success is True
        assert result.status == "rejected"
        assert result.reject_count == 1
        assert result.cooldown_until is not None

    def test_rejected_candidate_skipped_on_scan(self, installer, tmp_path):
        """rejected + cooldown 中の候補は scan でスキップされる"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        installer.reject(candidate_key, reason="Not needed")
        result = installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))

        assert result.skipped_cooldown == 1
        assert result.pending_created == 0


# ======================================================================
# Test 3: reject 3回で blocked へ遷移し、scan しても pending にならない
# ======================================================================

class TestRejectThreeTimesBlocked:
    def test_three_rejections_block(self, installer, tmp_path):
        """3回 reject すると blocked になる"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        installer.reject(candidate_key, reason="No 1")
        # rejected 状態になったので、pending に戻すために cooldown を巻き戻す
        installer._index_items[candidate_key].status = CandidateStatus.PENDING

        installer.reject(candidate_key, reason="No 2")
        installer._index_items[candidate_key].status = CandidateStatus.PENDING

        result3 = installer.reject(candidate_key, reason="No 3")

        assert result3.success is True
        assert result3.status == "blocked"
        assert result3.reject_count == 3

    def test_blocked_not_pending_on_scan(self, installer, tmp_path):
        """blocked の候補は scan しても pending にならない"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        # 3回 reject
        for i in range(2):
            installer.reject(candidate_key, reason=f"No {i+1}")
            installer._index_items[candidate_key].status = CandidateStatus.PENDING
        installer.reject(candidate_key, reason="No 3")

        # scan しても pending にならない
        result = installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        assert result.skipped_blocked == 1
        assert result.pending_created == 0

        pending = installer.list_items("pending")
        assert len(pending) == 0


# ======================================================================
# Test 4: unblock すると再通知可能になる（ただし cooldown）
# ======================================================================

class TestUnblock:
    def test_unblock_makes_renotifiable(self, installer, tmp_path):
        """unblock すると rejected (cooldown付き) になり、cooldown 後に再 pending 可能"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        for i in range(2):
            installer.reject(candidate_key, reason=f"No {i+1}")
            installer._index_items[candidate_key].status = CandidateStatus.PENDING
        installer.reject(candidate_key, reason="No 3")

        # blocked 確認
        assert installer._index_items[candidate_key].status == CandidateStatus.BLOCKED

        # unblock
        ub_result = installer.unblock(candidate_key)
        assert ub_result.success is True
        assert ub_result.status_after == "rejected"

        # blocked リストから消えている
        blocked = installer.list_blocked()
        assert candidate_key not in blocked

        # cooldown 中はスキップ
        scan_result = installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        assert scan_result.skipped_cooldown == 1

        # cooldown を巻き戻す→再 pending
        installer._index_items[candidate_key].cooldown_until = "2020-01-01T00:00:00Z"
        scan_result2 = installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        assert scan_result2.pending_created == 1


# ======================================================================
# Test 5: approve で trust 登録＋コピー＋reload が動く
# ======================================================================

class TestApprove:
    @patch("core_runtime.capability_installer.CapabilityInstaller._audit_event")
    def test_approve_installs(self, mock_audit, installer, tmp_path):
        """approve_and_install が trust 登録 + コピーを行う"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        # Trust store と Registry をモック
        mock_trust_store = MagicMock()
        mock_trust_store.is_loaded.return_value = True
        mock_trust_store.add_trust.return_value = True

        mock_registry = MagicMock()
        mock_registry_result = MagicMock()
        mock_registry_result.success = True
        mock_registry.load_all.return_value = mock_registry_result

        mock_executor = MagicMock()

        with patch("core_runtime.capability_installer._get_trust_store", return_value=mock_trust_store), \
             patch("core_runtime.capability_installer._get_handler_registry", return_value=mock_registry), \
             patch("core_runtime.capability_installer._get_executor", return_value=mock_executor):
            result = installer.approve_and_install(candidate_key, notes="Test approve")

        assert result.success is True
        assert result.status == "installed"
        assert result.handler_id == "fs_read_handler"
        assert result.permission_id == "fs.read"
        assert result.sha256 != ""

        # コピー先が存在
        dest_dir = Path(installer._handlers_dest_dir) / "fs_read_v1"
        assert (dest_dir / "handler.json").exists()
        assert (dest_dir / "handler.py").exists()

        # Trust store に呼ばれた
        mock_trust_store.add_trust.assert_called_once()

        # index が installed
        item_after = installer.get_item(candidate_key)
        assert item_after["status"] == "installed"

    @patch("core_runtime.capability_installer.CapabilityInstaller._audit_event")
    def test_approve_idempotent(self, mock_audit, installer, tmp_path):
        """既に installed の候補を再 approve しても成功（idempotent）"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        mock_trust_store = MagicMock()
        mock_trust_store.is_loaded.return_value = True
        mock_trust_store.add_trust.return_value = True

        with patch("core_runtime.capability_installer._get_trust_store", return_value=mock_trust_store), \
             patch("core_runtime.capability_installer._get_handler_registry", return_value=MagicMock()), \
             patch("core_runtime.capability_installer._get_executor", return_value=MagicMock()):
            result1 = installer.approve_and_install(candidate_key)
            result2 = installer.approve_and_install(candidate_key)

        assert result1.success is True
        assert result2.success is True
        assert result2.status == "installed"


# ======================================================================
# Test 6: entrypoint に ../ がある候補は approve/install で拒否される
# ======================================================================

class TestPathTraversal:
    def test_scan_rejects_path_traversal(self, tmp_path):
        """entrypoint に ../ がある候補は scan でエラーになる"""
        pack_dir = tmp_path / "ecosystem" / "evil_pack" / "share" / "capability_handlers" / "evil_slug"
        pack_dir.mkdir(parents=True)

        handler_json = {
            "handler_id": "evil_handler",
            "permission_id": "evil.perm",
            "entrypoint": "../../../etc/passwd:execute",
        }
        (pack_dir / "handler.json").write_text(json.dumps(handler_json), encoding="utf-8")
        (pack_dir / "handler.py").write_text("def execute(c, a): pass", encoding="utf-8")

        inst = CapabilityInstaller(
            requests_dir=str(tmp_path / "requests"),
            handlers_dest_dir=str(tmp_path / "handlers_dest"),
        )
        result = inst.scan_candidates(ecosystem_dir=str(tmp_path / "ecosystem"))

        assert result.scanned_count == 1
        assert result.pending_created == 0
        assert len(result.errors) == 1
        assert "traversal" in result.errors[0]["error"].lower()


# ======================================================================
# Test 7: sha256 が変わったら approve が失敗（TOCTOU）
# ======================================================================

class TestSha256Toctou:
    @patch("core_runtime.capability_installer.CapabilityInstaller._audit_event")
    def test_sha256_change_fails_approve(self, mock_audit, installer, tmp_path):
        """scan 後に handler.py が変更されると approve が失敗する"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        # handler.py を変更
        handler_py = (
            tmp_path / "ecosystem" / "my_pack" / "share"
            / "capability_handlers" / "fs_read_v1" / "handler.py"
        )
        handler_py.write_text("def execute(c, a): return {'status': 'HACKED'}", encoding="utf-8")

        mock_trust_store = MagicMock()
        mock_trust_store.is_loaded.return_value = True
        mock_trust_store.add_trust.return_value = True

        with patch("core_runtime.capability_installer._get_trust_store", return_value=mock_trust_store):
            result = installer.approve_and_install(candidate_key)

        assert result.success is False
        assert "SHA-256 mismatch" in result.error

        # index が failed
        item_after = installer.get_item(candidate_key)
        assert item_after["status"] == "failed"


# ======================================================================
# Test 8: requests.jsonl にイベントが記録される
# ======================================================================

class TestEventLog:
    def test_events_logged(self, installer, tmp_path):
        """操作がイベントログに記録される"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))

        log_path = Path(installer._requests_dir) / "requests.jsonl"
        assert log_path.exists()

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1

        event = json.loads(lines[0])
        assert event["event"] == "capability_handler.requested"
        assert "candidate_key" in event
        assert "ts" in event


# ======================================================================
# Test 9: blocked.json に永続化される
# ======================================================================

class TestBlockedPersistence:
    def test_blocked_persisted(self, installer, tmp_path):
        """blocked 状態が blocked.json に永続化される"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        candidate_key = items[0]["candidate_key"]

        for i in range(2):
            installer.reject(candidate_key, reason=f"No {i+1}")
            installer._index_items[candidate_key].status = CandidateStatus.PENDING
        installer.reject(candidate_key, reason="No 3")

        blocked_path = Path(installer._requests_dir) / "blocked.json"
        assert blocked_path.exists()

        with open(blocked_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert candidate_key in data["blocked"]
        assert data["blocked"][candidate_key]["reject_count"] == 3


# ======================================================================
# Test 10: index.json に永続化 + 再ロードで復元される
# ======================================================================

class TestIndexPersistence:
    def test_index_persisted_and_reloaded(self, installer, tmp_path):
        """index.json に永続化され、再インスタンス化で復元される"""
        installer.scan_candidates(ecosystem_dir=_get_ecosystem_dir(tmp_path))
        items = installer.list_items("pending")
        assert len(items) == 1
        candidate_key = items[0]["candidate_key"]

        # 新しいインスタンスで再ロード
        inst2 = CapabilityInstaller(
            requests_dir=str(installer._requests_dir),
            handlers_dest_dir=str(installer._handlers_dest_dir),
        )
        items2 = inst2.list_items("pending")
        assert len(items2) == 1
        assert items2[0]["candidate_key"] == candidate_key
