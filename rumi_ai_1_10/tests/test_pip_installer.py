"""
test_pip_installer.py - PipInstaller テスト

pytest で実行: python -m pytest tests/test_pip_installer.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from urllib.parse import quote, unquote

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core_runtime.pip_installer import (
    PipInstaller,
    PipCandidate,
    ScanResult,
    InstallResult,
    COOLDOWN_SECONDS,
    REJECT_THRESHOLD,
    STATUS_PENDING,
    STATUS_INSTALLED,
    STATUS_REJECTED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    DEFAULT_INDEX_URL,
    BUILDER_IMAGE,
    reset_pip_installer,
)


@pytest.fixture
def tmp_env(tmp_path):
    """テスト用の一時環境を構築"""
    eco_dir = tmp_path / "ecosystem"
    eco_dir.mkdir()

    pack_dir = eco_dir / "test_pack"
    pack_dir.mkdir()

    eco_json = pack_dir / "ecosystem.json"
    eco_json.write_text(json.dumps({
        "pack_id": "test_pack",
        "version": "1.0.0",
    }))

    req_lock = pack_dir / "requirements.lock"
    req_lock.write_text("requests==2.31.0\nflask==3.0.0\n")

    requests_dir = tmp_path / "pip_requests"
    requests_dir.mkdir()

    pack_data_dir = tmp_path / "pack_data"
    pack_data_dir.mkdir()

    return {
        "tmp_path": tmp_path,
        "eco_dir": eco_dir,
        "pack_dir": pack_dir,
        "req_lock": req_lock,
        "requests_dir": requests_dir,
        "pack_data_dir": pack_data_dir,
    }


@pytest.fixture
def installer(tmp_env):
    """PipInstaller インスタンスを作成"""
    with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
        inst = PipInstaller(
            requests_dir=str(tmp_env["requests_dir"]),
            ecosystem_dir=str(tmp_env["eco_dir"]),
        )
        yield inst


class TestScan:
    def test_scan_creates_pending(self, installer, tmp_env):
        """1. scan が pending を作る"""
        result = installer.scan_candidates()
        assert result.scanned_count >= 1
        assert result.pending_created == 1
        items = installer.list_items("pending")
        assert len(items) == 1
        assert items[0]["pack_id"] == "test_pack"
        assert items[0]["status"] == STATUS_PENDING
        assert items[0]["requirements_relpath"] == "requirements.lock"

    def test_scan_skips_installed(self, installer, tmp_env):
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        with installer._lock:
            installer._index[ckey].status = STATUS_INSTALLED
            installer._save_index()
        result = installer.scan_candidates()
        assert result.skipped_installed == 1
        assert result.pending_created == 0


class TestReject:
    def test_reject_sets_cooldown(self, installer, tmp_env):
        """2. reject で cooldown_until が now+1h になる"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        result = installer.reject(ckey, reason="not needed")
        assert result.success is True
        assert result.status == STATUS_REJECTED
        assert result.reject_count == 1
        assert result.cooldown_until != ""
        cd = datetime.fromisoformat(result.cooldown_until.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (cd - now).total_seconds()
        assert 3500 < diff < 3700

    def test_reject_three_times_blocks(self, installer, tmp_env):
        """3. reject 3回で blocked に入る"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        for i in range(3):
            result = installer.reject(ckey, reason=f"reject {i+1}")
        assert result.status == STATUS_BLOCKED
        assert result.reject_count == 3
        blocked = installer.list_blocked()
        assert ckey in blocked

    def test_blocked_skipped_on_scan(self, installer, tmp_env):
        """4. blocked は scan で pending に上がらない"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        for _ in range(3):
            installer.reject(ckey, reason="block it")
        result = installer.scan_candidates()
        assert result.skipped_blocked == 1
        assert result.pending_created == 0


class TestUnblock:
    def test_unblock_removes_blocked(self, installer, tmp_env):
        """5. unblock すると blocked 解除される"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        for _ in range(3):
            installer.reject(ckey, reason="block it")
        assert installer.list_blocked().get(ckey) is not None
        result = installer.unblock(ckey, reason="allow now")
        assert result.success is True
        assert result.status == STATUS_PENDING
        assert installer.list_blocked().get(ckey) is None
        items = installer.list_items("pending")
        assert len(items) == 1
        assert items[0]["candidate_key"] == ckey


class TestApproveDockerCommand:
    @patch("core_runtime.pip_installer.subprocess.run")
    def test_approve_builds_correct_docker_commands(self, mock_run, installer, tmp_env):
        """6. approve が docker コマンドを正しく組む (dry-run)"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            result = installer.approve_and_install(ckey, allow_sdist=False)
        assert result.success is True
        assert result.status == STATUS_INSTALLED
        assert mock_run.call_count == 3
        dl_cmd = mock_run.call_args_list[0][0][0]
        assert "pip" in dl_cmd
        assert "download" in dl_cmd
        assert "--only-binary=:all:" in dl_cmd
        assert "--network=bridge" in dl_cmd
        inst_cmd = mock_run.call_args_list[1][0][0]
        assert "pip" in inst_cmd
        assert "install" in inst_cmd
        assert "--no-index" in inst_cmd
        assert "--network=none" in inst_cmd

    @patch("core_runtime.pip_installer.subprocess.run")
    def test_allow_sdist_omits_only_binary(self, mock_run, installer, tmp_env):
        """8. allow_sdist=true で --only-binary が付かない"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            result = installer.approve_and_install(ckey, allow_sdist=True)
        dl_cmd = mock_run.call_args_list[0][0][0]
        assert "--only-binary=:all:" not in dl_cmd

    @patch("core_runtime.pip_installer.subprocess.run")
    def test_mount_constraints(self, mock_run, installer, tmp_env):
        """10. マウントが /data RW と /src RO に限定されている"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            installer.approve_and_install(ckey)
        for i in range(2):
            cmd = mock_run.call_args_list[i][0][0]
            volumes = []
            for j, arg in enumerate(cmd):
                if arg == "-v" and j + 1 < len(cmd):
                    volumes.append(cmd[j + 1])
            assert len(volumes) == 2
            rw_vols = [v for v in volumes if v.endswith(":rw")]
            ro_vols = [v for v in volumes if v.endswith(":ro")]
            assert len(rw_vols) == 1
            assert len(ro_vols) == 1
            assert ":/data:rw" in rw_vols[0]
            assert ":/src:ro" in ro_vols[0]


class TestCandidateKeyEncoding:
    def test_candidate_key_url_encode_decode(self):
        """7. candidate_key が URL encode/decode で崩れない"""
        pack_id = "my_pack"
        relpath = "requirements.lock"
        sha256 = "abcdef1234567890" * 4
        key = PipInstaller.build_candidate_key(pack_id, relpath, sha256)
        assert ":" in key
        encoded = quote(key, safe="")
        assert ":" not in encoded
        assert "%3A" in encoded
        decoded = unquote(encoded)
        assert decoded == key
        p_pack, p_rel, p_sha = PipInstaller.parse_candidate_key(decoded)
        assert p_pack == pack_id
        assert p_rel == relpath
        assert p_sha == sha256

    def test_candidate_key_with_backend_relpath(self):
        key = "my_pack:backend/requirements.lock:abc123"
        p, r, s = PipInstaller.parse_candidate_key(key)
        assert p == "my_pack"
        assert r == "backend/requirements.lock"
        assert s == "abc123"


class TestDockerCommandOrder:
    @patch("core_runtime.pip_installer.subprocess.run")
    def test_download_before_install(self, mock_run, installer, tmp_env):
        """9. download → install の順で実行される"""
        installer.scan_candidates()
        items = installer.list_items("pending")
        ckey = items[0]["candidate_key"]
        pack_data = tmp_env["pack_data_dir"] / "test_pack" / "python"
        (pack_data / "wheelhouse").mkdir(parents=True, exist_ok=True)
        (pack_data / "site-packages").mkdir(parents=True, exist_ok=True)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            installer.approve_and_install(ckey)
        assert mock_run.call_count == 3
        assert "download" in mock_run.call_args_list[0][0][0]
        assert "install" in mock_run.call_args_list[1][0][0]
        assert "python" in mock_run.call_args_list[2][0][0]


class TestPersistence:
    def test_state_survives_reload(self, tmp_env):
        with patch("core_runtime.pip_installer.PACK_DATA_BASE_DIR", str(tmp_env["pack_data_dir"])):
            inst1 = PipInstaller(
                requests_dir=str(tmp_env["requests_dir"]),
                ecosystem_dir=str(tmp_env["eco_dir"]),
            )
            inst1.scan_candidates()
            items1 = inst1.list_items("pending")
            assert len(items1) == 1
            inst2 = PipInstaller(
                requests_dir=str(tmp_env["requests_dir"]),
                ecosystem_dir=str(tmp_env["eco_dir"]),
            )
            items2 = inst2.list_items("pending")
            assert len(items2) == 1
            assert items2[0]["candidate_key"] == items1[0]["candidate_key"]
