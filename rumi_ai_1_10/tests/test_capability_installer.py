"""
test_capability_installer.py - capability_installer.py regression tests (Wave 12 T-044)

Covers:
  - CandidateInfo: to_dict / from_dict round-trip
  - IndexItem: to_dict / from_dict, status parsing
  - CandidateStatus enum values
  - ScanResult / ApproveResult / RejectResult / UnblockResult dataclasses
  - CapabilityInstaller: init, make_candidate_key, _validate_slug,
    _check_no_symlinks, _validate_entrypoint, _parse_ts
  - CapabilityInstaller: scan_candidates (mock ecosystem), reject, unblock
  - Persistence: index.json / blocked.json round-trip
  - Edge cases: empty dirs, missing handler.json, symlink detection
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core_runtime.capability_installer import (
    CandidateInfo,
    CandidateStatus,
    IndexItem,
    ScanResult,
    ApproveResult,
    RejectResult,
    UnblockResult,
    CapabilityInstaller,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_REJECT_THRESHOLD,
    _SLUG_PATTERN,
)


# ======================================================================
# CandidateInfo
# ======================================================================

class TestCandidateInfo:
    """CandidateInfo serialization tests."""

    def test_to_dict_round_trip(self):
        ci = CandidateInfo(
            pack_id="mypack",
            slug="my-handler",
            handler_id="handler_001",
            permission_id="perm_read",
            entrypoint="handler.py:execute",
            source_dir="/tmp/src",
            handler_py_sha256="abc123def456",
        )
        d = ci.to_dict()
        restored = CandidateInfo.from_dict(d)
        assert restored.pack_id == ci.pack_id
        assert restored.slug == ci.slug
        assert restored.handler_id == ci.handler_id
        assert restored.handler_py_sha256 == ci.handler_py_sha256

    def test_from_dict_missing_fields(self):
        ci = CandidateInfo.from_dict({})
        assert ci.pack_id == ""
        assert ci.slug == ""
        assert ci.handler_id == ""


# ======================================================================
# IndexItem
# ======================================================================

class TestIndexItem:
    """IndexItem serialization and status parsing."""

    def test_to_dict_round_trip(self):
        ci = CandidateInfo(
            pack_id="p", slug="s", handler_id="h",
            permission_id="perm", entrypoint="handler.py:run",
            source_dir="/src", handler_py_sha256="sha",
        )
        item = IndexItem(
            candidate_key="p:s:h:sha",
            status=CandidateStatus.PENDING,
            reject_count=0,
            last_event_ts="2025-01-01T00:00:00Z",
            candidate=ci,
        )
        d = item.to_dict()
        restored = IndexItem.from_dict(d)
        assert restored.candidate_key == "p:s:h:sha"
        assert restored.status == CandidateStatus.PENDING
        assert restored.candidate is not None
        assert restored.candidate.pack_id == "p"

    def test_from_dict_invalid_status_defaults_to_pending(self):
        d = {"candidate_key": "k", "status": "nonexistent_status"}
        item = IndexItem.from_dict(d)
        assert item.status == CandidateStatus.PENDING

    def test_from_dict_without_candidate(self):
        d = {"candidate_key": "k", "status": "installed"}
        item = IndexItem.from_dict(d)
        assert item.candidate is None
        assert item.status == CandidateStatus.INSTALLED


# ======================================================================
# CandidateStatus
# ======================================================================

class TestCandidateStatus:
    """CandidateStatus enum values."""

    def test_all_values(self):
        assert CandidateStatus.PENDING.value == "pending"
        assert CandidateStatus.INSTALLED.value == "installed"
        assert CandidateStatus.REJECTED.value == "rejected"
        assert CandidateStatus.BLOCKED.value == "blocked"
        assert CandidateStatus.FAILED.value == "failed"

    def test_string_enum(self):
        assert isinstance(CandidateStatus.PENDING, str)
        assert CandidateStatus.PENDING == "pending"


# ======================================================================
# Result dataclasses
# ======================================================================

class TestResultDataclasses:
    """to_dict tests for result dataclasses."""

    def test_scan_result(self):
        sr = ScanResult(scanned_count=5, pending_created=2, skipped_blocked=1)
        d = sr.to_dict()
        assert d["scanned_count"] == 5
        assert d["pending_created"] == 2

    def test_approve_result_success(self):
        ar = ApproveResult(success=True, status="installed",
                           installed_to="/dest", handler_id="h1",
                           permission_id="p1", sha256="abc")
        d = ar.to_dict()
        assert d["success"] is True
        assert d["installed_to"] == "/dest"
        assert "error" not in d

    def test_approve_result_failure(self):
        ar = ApproveResult(success=False, error="Not found")
        d = ar.to_dict()
        assert d["success"] is False
        assert d["error"] == "Not found"

    def test_reject_result(self):
        rr = RejectResult(success=True, status="rejected",
                          reject_count=1, cooldown_until="2025-01-02T00:00:00Z")
        d = rr.to_dict()
        assert d["reject_count"] == 1

    def test_unblock_result(self):
        ur = UnblockResult(success=True, status_after="rejected")
        d = ur.to_dict()
        assert d["success"] is True
        assert "error" not in d


# ======================================================================
# CapabilityInstaller - static helpers
# ======================================================================

class TestCapabilityInstallerStatic:
    """Static helper method tests."""

    def test_make_candidate_key(self):
        key = CapabilityInstaller.make_candidate_key("p", "s", "h", "sha")
        assert key == "p:s:h:sha"

    def test_make_candidate_key_with_colons(self):
        key = CapabilityInstaller.make_candidate_key("a:b", "c", "d", "e")
        assert key == "a:b:c:d:e"

    # --- _validate_slug ---

    @pytest.mark.parametrize("slug,expected_valid", [
        ("my-handler", True),
        ("my_handler", True),
        ("handler123", True),
        ("A-Z_0-9", True),
        ("valid", True),
        ("", False),
        ("has space", False),
        ("has/slash", False),
        ("has.dot", False),
        ("has@at", False),
        ("../traversal", False),
    ])
    def test_validate_slug(self, slug: str, expected_valid: bool):
        valid, error = CapabilityInstaller._validate_slug(slug)
        assert valid is expected_valid

    # --- _check_no_symlinks ---

    def test_check_no_symlinks_regular_files(self, tmp_path):
        f = tmp_path / "regular.py"
        f.touch()
        valid, error = CapabilityInstaller._check_no_symlinks(f)
        assert valid is True

    def test_check_no_symlinks_detects_symlink(self, tmp_path):
        target = tmp_path / "target.py"
        target.touch()
        link = tmp_path / "link.py"
        link.symlink_to(target)
        valid, error = CapabilityInstaller._check_no_symlinks(link)
        assert valid is False
        assert "Symbolic link" in error

    # --- _validate_entrypoint ---

    def test_validate_entrypoint_valid(self, tmp_path):
        handler = tmp_path / "handler.py"
        handler.write_text("def execute(): pass")
        valid, error, path = CapabilityInstaller._validate_entrypoint(
            "handler.py:execute", tmp_path
        )
        assert valid is True
        assert path == handler

    def test_validate_entrypoint_no_colon(self, tmp_path):
        valid, error, path = CapabilityInstaller._validate_entrypoint(
            "handler.py", tmp_path
        )
        assert valid is False
        assert "format" in error.lower()

    def test_validate_entrypoint_path_traversal(self, tmp_path):
        valid, error, path = CapabilityInstaller._validate_entrypoint(
            "../../../etc/passwd:execute", tmp_path
        )
        assert valid is False
        assert "traversal" in error.lower()

    def test_validate_entrypoint_file_not_found(self, tmp_path):
        valid, error, path = CapabilityInstaller._validate_entrypoint(
            "missing.py:execute", tmp_path
        )
        assert valid is False
        assert "not found" in error.lower()

    # --- _parse_ts ---

    def test_parse_ts_valid_z(self):
        dt = CapabilityInstaller._parse_ts("2025-01-01T00:00:00Z")
        assert dt is not None
        assert dt.year == 2025

    def test_parse_ts_valid_offset(self):
        dt = CapabilityInstaller._parse_ts("2025-01-01T00:00:00+00:00")
        assert dt is not None

    def test_parse_ts_empty(self):
        assert CapabilityInstaller._parse_ts("") is None

    def test_parse_ts_invalid(self):
        assert CapabilityInstaller._parse_ts("not-a-date") is None


# ======================================================================
# CapabilityInstaller - lifecycle (with tmp_path)
# ======================================================================

class TestCapabilityInstallerLifecycle:
    """CapabilityInstaller init and persistence."""

    def test_init_creates_dirs(self, tmp_path):
        req_dir = tmp_path / "requests"
        dest_dir = tmp_path / "handlers"
        installer = CapabilityInstaller(
            requests_dir=str(req_dir),
            handlers_dest_dir=str(dest_dir),
        )
        assert req_dir.exists()
        assert dest_dir.exists()

    def test_list_items_empty(self, tmp_path):
        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        items = installer.list_items()
        assert items == []

    def test_list_blocked_empty(self, tmp_path):
        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        blocked = installer.list_blocked()
        assert blocked == {}


# ======================================================================
# CapabilityInstaller - scan_candidates
# ======================================================================

class TestScanCandidates:
    """scan_candidates with mock filesystem."""

    def _setup_candidate(self, eco_dir: Path, pack_id: str, slug: str,
                          handler_id: str = "h1",
                          permission_id: str = "p1") -> Path:
        """Create a minimal candidate handler structure."""
        slug_dir = eco_dir / pack_id / "share" / "capability_handlers" / slug
        slug_dir.mkdir(parents=True, exist_ok=True)

        handler_json = {
            "handler_id": handler_id,
            "permission_id": permission_id,
            "entrypoint": "handler.py:execute",
        }
        (slug_dir / "handler.json").write_text(
            json.dumps(handler_json), encoding="utf-8"
        )
        (slug_dir / "handler.py").write_text("def execute(): pass", encoding="utf-8")
        return slug_dir

    def test_scan_finds_candidates(self, tmp_path):
        eco_dir = tmp_path / "ecosystem"
        self._setup_candidate(eco_dir, "pack_a", "my-handler")

        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        with patch.object(CapabilityInstaller, '_compute_sha256', return_value="fakehash"):
            result = installer.scan_candidates(ecosystem_dir=str(eco_dir))

        assert result.scanned_count == 1
        assert result.pending_created == 1

    def test_scan_skips_invalid_slug(self, tmp_path):
        eco_dir = tmp_path / "ecosystem"
        # Create a slug with invalid characters
        slug_dir = eco_dir / "pack_a" / "share" / "capability_handlers" / "bad..slug"
        slug_dir.mkdir(parents=True)
        (slug_dir / "handler.json").write_text("{}", encoding="utf-8")

        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        result = installer.scan_candidates(ecosystem_dir=str(eco_dir))
        assert result.scanned_count == 1
        assert result.pending_created == 0
        assert len(result.errors) >= 1

    def test_scan_skips_missing_handler_json(self, tmp_path):
        eco_dir = tmp_path / "ecosystem"
        slug_dir = eco_dir / "pack_a" / "share" / "capability_handlers" / "valid-slug"
        slug_dir.mkdir(parents=True)
        # No handler.json

        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        result = installer.scan_candidates(ecosystem_dir=str(eco_dir))
        assert result.pending_created == 0
        assert any("handler.json" in e.get("error", "") for e in result.errors)

    def test_scan_nonexistent_ecosystem_dir(self, tmp_path):
        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        result = installer.scan_candidates(ecosystem_dir=str(tmp_path / "nonexistent"))
        assert result.scanned_count == 0

    def test_scan_excludes_hidden_dirs(self, tmp_path):
        eco_dir = tmp_path / "ecosystem"
        # Hidden pack directory
        slug_dir = eco_dir / ".hidden_pack" / "share" / "capability_handlers" / "slug"
        slug_dir.mkdir(parents=True)
        (slug_dir / "handler.json").write_text('{"handler_id":"h","permission_id":"p"}')
        (slug_dir / "handler.py").write_text("def execute(): pass")

        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        result = installer.scan_candidates(ecosystem_dir=str(eco_dir))
        assert result.scanned_count == 0

    def test_scan_idempotent(self, tmp_path):
        eco_dir = tmp_path / "ecosystem"
        self._setup_candidate(eco_dir, "pack_a", "my-handler")

        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        with patch.object(CapabilityInstaller, '_compute_sha256', return_value="fakehash"):
            result1 = installer.scan_candidates(ecosystem_dir=str(eco_dir))
            result2 = installer.scan_candidates(ecosystem_dir=str(eco_dir))

        assert result1.pending_created == 1
        assert result2.pending_created == 0
        assert result2.skipped_pending == 1


# ======================================================================
# CapabilityInstaller - reject / unblock
# ======================================================================

class TestRejectUnblock:
    """reject and unblock workflow tests."""

    def _make_installer_with_pending(self, tmp_path) -> tuple:
        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
            cooldown_seconds=3600,
            reject_threshold=3,
        )
        ci = CandidateInfo(
            pack_id="p", slug="s", handler_id="h",
            permission_id="perm", entrypoint="handler.py:execute",
            source_dir="/src", handler_py_sha256="sha",
        )
        key = "p:s:h:sha"
        item = IndexItem(
            candidate_key=key,
            status=CandidateStatus.PENDING,
            reject_count=0,
            last_event_ts=installer._now_ts(),
            candidate=ci,
        )
        installer._index_items[key] = item
        return installer, key

    def test_reject_increments_count(self, tmp_path):
        installer, key = self._make_installer_with_pending(tmp_path)
        result = installer.reject(key, reason="test")
        assert result.success is True
        assert result.reject_count == 1
        assert result.status == "rejected"

    def test_reject_sets_cooldown(self, tmp_path):
        installer, key = self._make_installer_with_pending(tmp_path)
        result = installer.reject(key)
        assert result.cooldown_until is not None

    def test_reject_threshold_blocks(self, tmp_path):
        installer, key = self._make_installer_with_pending(tmp_path)
        for i in range(3):
            result = installer.reject(key)
        assert result.status == "blocked"
        assert result.reject_count == 3

    def test_reject_nonexistent_key(self, tmp_path):
        installer, _ = self._make_installer_with_pending(tmp_path)
        result = installer.reject("nonexistent_key")
        assert result.success is False

    def test_reject_installed_fails(self, tmp_path):
        installer, key = self._make_installer_with_pending(tmp_path)
        installer._index_items[key].status = CandidateStatus.INSTALLED
        result = installer.reject(key)
        assert result.success is False

    def test_unblock_blocked_candidate(self, tmp_path):
        installer, key = self._make_installer_with_pending(tmp_path)
        # Block it first
        for _ in range(3):
            installer.reject(key)
        assert installer._index_items[key].status == CandidateStatus.BLOCKED

        result = installer.unblock(key)
        assert result.success is True
        assert result.status_after == "rejected"
        assert installer._index_items[key].status == CandidateStatus.REJECTED

    def test_unblock_non_blocked_fails(self, tmp_path):
        installer, key = self._make_installer_with_pending(tmp_path)
        result = installer.unblock(key)
        assert result.success is False


# ======================================================================
# CapabilityInstaller - persistence
# ======================================================================

class TestPersistence:
    """Index and blocked file persistence tests."""

    def test_index_save_and_load(self, tmp_path):
        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        ci = CandidateInfo(
            pack_id="p", slug="s", handler_id="h",
            permission_id="perm", entrypoint="handler.py:execute",
            source_dir="/src", handler_py_sha256="sha",
        )
        key = "p:s:h:sha"
        item = IndexItem(
            candidate_key=key,
            status=CandidateStatus.PENDING,
            candidate=ci,
            last_event_ts=installer._now_ts(),
        )
        installer._index_items[key] = item
        installer._save_index()

        # New instance loads the same data
        installer2 = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        assert key in installer2._index_items
        assert installer2._index_items[key].status == CandidateStatus.PENDING

    def test_blocked_save_and_load(self, tmp_path):
        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        installer._blocked["test_key"] = {
            "candidate_key": "test_key",
            "blocked_at": installer._now_ts(),
            "reason": "test",
        }
        installer._save_blocked()

        installer2 = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        assert "test_key" in installer2._blocked

    def test_event_log_append(self, tmp_path):
        installer = CapabilityInstaller(
            requests_dir=str(tmp_path / "req"),
            handlers_dest_dir=str(tmp_path / "dest"),
        )
        installer._append_event("test_event", "key_1", actor="tester")
        installer._append_event("test_event_2", "key_2", actor="tester")

        log_path = tmp_path / "req" / "requests.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        entry = json.loads(lines[0])
        assert entry["event"] == "test_event"
