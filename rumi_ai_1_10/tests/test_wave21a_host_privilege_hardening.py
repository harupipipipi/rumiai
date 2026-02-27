"""
test_wave21a_host_privilege_hardening.py

W21-A: host_privilege_manager 永続化 + 認証 + 監査のテスト (17 cases)
"""
from __future__ import annotations

import hashlib
import hmac as _hmac_mod
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# ダミーモジュール — 相対インポート回避用
# ---------------------------------------------------------------------------

_FAKE_KEY = b"test_signing_key_for_unit_tests__"


def _fake_generate_or_load_signing_key(key_path, **kwargs):
    return _FAKE_KEY


def _fake_compute_data_hmac(key, data_dict):
    """テスト用の HMAC 計算 (本番同等ロジック)。"""
    filtered = {k: v for k, v in data_dict.items() if not k.startswith("_hmac")}
    payload = json.dumps(filtered, sort_keys=True, ensure_ascii=False)
    return _hmac_mod.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _fake_verify_data_hmac(key, data_dict, expected_hmac):
    computed = _fake_compute_data_hmac(key, data_dict)
    return _hmac_mod.compare_digest(computed, expected_hmac)


# hmac_key_manager ダミー
_dummy_hmac = types.ModuleType("core_runtime.hmac_key_manager")
_dummy_hmac.generate_or_load_signing_key = _fake_generate_or_load_signing_key
_dummy_hmac.compute_data_hmac = _fake_compute_data_hmac
_dummy_hmac.verify_data_hmac = _fake_verify_data_hmac
sys.modules["core_runtime.hmac_key_manager"] = _dummy_hmac

# audit_logger ダミー
_dummy_audit = types.ModuleType("core_runtime.audit_logger")
_mock_audit_logger = MagicMock()
_dummy_audit.get_audit_logger = MagicMock(return_value=_mock_audit_logger)
sys.modules["core_runtime.audit_logger"] = _dummy_audit

# paths ダミー
_dummy_paths = types.ModuleType("core_runtime.paths")
_dummy_paths.BASE_DIR = Path("/tmp/dummy_base_dir_w21a")
sys.modules.setdefault("core_runtime.paths", _dummy_paths)

# di_container ダミー
_dummy_di = types.ModuleType("core_runtime.di_container")
_dummy_container = MagicMock()
_dummy_di.get_container = MagicMock(return_value=_dummy_container)
sys.modules.setdefault("core_runtime.di_container", _dummy_di)

# ---------------------------------------------------------------------------
# テスト対象のインポート (ダミー設定後にインポート)
# ---------------------------------------------------------------------------

# モジュールキャッシュを削除して再ロードを強制
sys.modules.pop("core_runtime.host_privilege_manager", None)

from core_runtime.host_privilege_manager import (
    HostPrivilegeManager,
    PrivilegeResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_audit_mock():
    """各テスト前に audit mock をリセット"""
    _mock_audit_logger.reset_mock()
    _dummy_audit.get_audit_logger.reset_mock()
    _dummy_audit.get_audit_logger.return_value = _mock_audit_logger
    yield


@pytest.fixture
def mgr(tmp_path):
    """tmp_path を data_dir に使う HostPrivilegeManager"""
    return HostPrivilegeManager(data_dir=str(tmp_path))


# ======================================================================
# 1. grant -> has_privilege が True
# ======================================================================
class TestGrantAndHasPrivilege:
    def test_grant_then_has_privilege(self, mgr):
        result = mgr.grant("pack_a", "priv_x")
        assert result.success is True
        assert mgr.has_privilege("pack_a", "priv_x") is True


# ======================================================================
# 2. grant -> revoke -> has_privilege が False
# ======================================================================
class TestGrantRevokeHasPrivilege:
    def test_grant_revoke_then_no_privilege(self, mgr):
        mgr.grant("pack_a", "priv_x")
        result = mgr.revoke("pack_a", "priv_x")
        assert result.success is True
        assert mgr.has_privilege("pack_a", "priv_x") is False


# ======================================================================
# 3. revoke_all で全特権削除
# ======================================================================
class TestRevokeAll:
    def test_revoke_all_removes_all(self, mgr):
        mgr.grant("pack_a", "priv_x")
        mgr.grant("pack_a", "priv_y")
        result = mgr.revoke_all("pack_a")
        assert result.success is True
        assert mgr.has_privilege("pack_a", "priv_x") is False
        assert mgr.has_privilege("pack_a", "priv_y") is False


# ======================================================================
# 4. 永続化: grant -> 新インスタンス -> has_privilege True
# ======================================================================
class TestPersistence:
    def test_persistence_across_instances(self, tmp_path):
        mgr1 = HostPrivilegeManager(data_dir=str(tmp_path))
        mgr1.grant("pack_a", "priv_x")

        mgr2 = HostPrivilegeManager(data_dir=str(tmp_path))
        assert mgr2.has_privilege("pack_a", "priv_x") is True


# ======================================================================
# 5. HMAC 署名付きファイルのロード成功
# ======================================================================
class TestHmacLoadSuccess:
    def test_hmac_signed_file_loads(self, tmp_path):
        data = {
            "version": "1.0",
            "updated_at": "2026-01-01T00:00:00Z",
            "grants": {"pack_a": ["priv_x"]},
        }
        sig = _fake_compute_data_hmac(_FAKE_KEY, data)
        data["hmac_signature"] = sig

        persist_path = tmp_path / "host_privileges.json"
        persist_path.write_text(json.dumps(data), encoding="utf-8")

        mgr = HostPrivilegeManager(data_dir=str(tmp_path))
        assert mgr.has_privilege("pack_a", "priv_x") is True


# ======================================================================
# 6. HMAC 署名改ざん -> WARNING + 内容は受け入れ
# ======================================================================
class TestHmacTampered:
    def test_tampered_hmac_warns_but_accepts(self, tmp_path):
        data = {
            "version": "1.0",
            "updated_at": "2026-01-01T00:00:00Z",
            "grants": {"pack_a": ["priv_x"]},
            "hmac_signature": "0" * 64,
        }
        persist_path = tmp_path / "host_privileges.json"
        persist_path.write_text(json.dumps(data), encoding="utf-8")

        import logging
        with patch.object(
            logging.getLogger("core_runtime.host_privilege_manager"),
            "warning",
        ) as mock_warn:
            mgr = HostPrivilegeManager(data_dir=str(tmp_path))
            assert mgr.has_privilege("pack_a", "priv_x") is True
            found = any(
                "HMAC" in str(c) for c in mock_warn.call_args_list
            )
            assert found, (
                "Expected HMAC warning log, got: "
                + str(mock_warn.call_args_list)
            )


# ======================================================================
# 7. 署名なしレガシーファイル -> WARNING + 受け入れ -> 保存で署名付与
# ======================================================================
class TestLegacyNoSignature:
    def test_legacy_file_accepted_and_signed_on_save(self, tmp_path):
        data = {
            "version": "1.0",
            "updated_at": "2026-01-01T00:00:00Z",
            "grants": {"pack_a": ["priv_x"]},
        }
        persist_path = tmp_path / "host_privileges.json"
        persist_path.write_text(json.dumps(data), encoding="utf-8")

        mgr = HostPrivilegeManager(data_dir=str(tmp_path))
        assert mgr.has_privilege("pack_a", "priv_x") is True

        # 保存をトリガー
        mgr.grant("pack_a", "priv_y")

        # ファイルに hmac_signature が付与されていること
        saved = json.loads(persist_path.read_text(encoding="utf-8"))
        assert "hmac_signature" in saved
        assert len(saved["hmac_signature"]) == 64


# ======================================================================
# 8. caller 認証: 信頼済み caller -> 成功
# ======================================================================
class TestCallerTrusted:
    def test_trusted_caller_succeeds(self, mgr):
        result = mgr.grant("pack_a", "priv_x", caller_id="kernel")
        assert result.success is True

    def test_all_default_trusted_callers(self, mgr):
        for caller in ("system", "kernel", "approval_manager"):
            result = mgr.grant("pack_a", f"priv_{caller}", caller_id=caller)
            assert result.success is True, f"Caller {caller} should be trusted"


# ======================================================================
# 9. caller 認証: 未信頼 caller -> 失敗
# ======================================================================
class TestCallerUntrusted:
    def test_untrusted_caller_rejected(self, mgr):
        result = mgr.grant("pack_a", "priv_x", caller_id="evil_actor")
        assert result.success is False
        assert "Unauthorized caller" in result.error


# ======================================================================
# 10. caller_id=None -> "system" として成功
# ======================================================================
class TestCallerNoneDefault:
    def test_none_caller_defaults_to_system(self, mgr):
        result = mgr.grant("pack_a", "priv_x", caller_id=None)
        assert result.success is True

    def test_omitted_caller_defaults_to_system(self, mgr):
        result = mgr.grant("pack_a", "priv_y")
        assert result.success is True


# ======================================================================
# 11. 入力バリデーション: 空 pack_id -> 失敗
# ======================================================================
class TestValidationEmpty:
    def test_empty_pack_id_rejected(self, mgr):
        result = mgr.grant("", "priv_x")
        assert result.success is False
        assert "Invalid pack_id" in result.error

    def test_empty_privilege_id_rejected(self, mgr):
        result = mgr.grant("pack_a", "")
        assert result.success is False
        assert "Invalid privilege_id" in result.error


# ======================================================================
# 12. 入力バリデーション: 不正文字 pack_id -> 失敗
# ======================================================================
class TestValidationInvalidChars:
    def test_invalid_chars_pack_id(self, mgr):
        result = mgr.grant("pack a!", "priv_x")
        assert result.success is False
        assert "Invalid pack_id" in result.error

    def test_invalid_chars_privilege_id(self, mgr):
        result = mgr.grant("pack_a", "priv/x")
        assert result.success is False
        assert "Invalid privilege_id" in result.error

    def test_slash_rejected(self, mgr):
        result = mgr.grant("../etc/passwd", "priv_x")
        assert result.success is False


# ======================================================================
# 13. 入力バリデーション: 256文字超 -> 失敗
# ======================================================================
class TestValidationTooLong:
    def test_pack_id_too_long(self, mgr):
        long_id = "a" * 257
        result = mgr.grant(long_id, "priv_x")
        assert result.success is False
        assert "exceeds" in result.error

    def test_pack_id_exactly_256_ok(self, mgr):
        ok_id = "a" * 256
        result = mgr.grant(ok_id, "priv_x")
        assert result.success is True


# ======================================================================
# 14. execute: 未付与の privilege -> 失敗
# ======================================================================
class TestExecuteNotGranted:
    def test_execute_without_grant(self, mgr):
        result = mgr.execute("pack_a", "priv_x", {"key": "val"})
        assert result.success is False
        assert "not granted" in result.error.lower()

    def test_execute_after_grant(self, mgr):
        mgr.grant("pack_a", "priv_x")
        result = mgr.execute("pack_a", "priv_x", {"key": "val"})
        assert result.success is True
        assert result.data["privilege_id"] == "priv_x"


# ======================================================================
# 15. list_privileges: 正しいリストが返る
# ======================================================================
class TestListPrivileges:
    def test_list_privileges_empty(self, mgr):
        result = mgr.list_privileges()
        assert result == []

    def test_list_privileges_after_grants(self, mgr):
        mgr.grant("pack_a", "priv_x")
        mgr.grant("pack_a", "priv_y")
        mgr.grant("pack_b", "priv_z")
        result = mgr.list_privileges()
        pack_ids = {entry["pack_id"] for entry in result}
        assert "pack_a" in pack_ids
        assert "pack_b" in pack_ids
        for entry in result:
            if entry["pack_id"] == "pack_a":
                assert set(entry["privileges"]) == {"priv_x", "priv_y"}


# ======================================================================
# 16. 監査ログ: grant 時に log_security_event が呼ばれる
# ======================================================================
class TestAuditLog:
    def test_grant_logs_security_event(self, mgr):
        mgr.grant("pack_a", "priv_x")
        calls = _mock_audit_logger.log_security_event.call_args_list
        event_types = [
            c.kwargs.get("event_type", c.args[0] if c.args else None)
            for c in calls
        ]
        assert "host_privilege_grant" in event_types

    def test_revoke_logs_security_event(self, mgr):
        mgr.grant("pack_a", "priv_x")
        _mock_audit_logger.reset_mock()
        mgr.revoke("pack_a", "priv_x")
        calls = _mock_audit_logger.log_security_event.call_args_list
        event_types = [
            c.kwargs.get("event_type", c.args[0] if c.args else None)
            for c in calls
        ]
        assert "host_privilege_revoke" in event_types

    def test_unauthorized_caller_logs_warning(self, mgr):
        _mock_audit_logger.reset_mock()
        mgr.grant("pack_a", "priv_x", caller_id="evil")
        calls = _mock_audit_logger.log_security_event.call_args_list
        event_types = [
            c.kwargs.get("event_type", c.args[0] if c.args else None)
            for c in calls
        ]
        assert "host_privilege_unauthorized" in event_types


# ======================================================================
# 17. 環境変数 RUMI_PRIVILEGE_TRUSTED_CALLERS で追加 caller が信頼される
# ======================================================================
class TestEnvTrustedCallers:
    def test_env_adds_trusted_caller(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_PRIVILEGE_TRUSTED_CALLERS", "custom_bot,another_bot")
        mgr = HostPrivilegeManager(data_dir=str(tmp_path))
        result = mgr.grant("pack_a", "priv_x", caller_id="custom_bot")
        assert result.success is True

    def test_env_adds_multiple_trusted_callers(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_PRIVILEGE_TRUSTED_CALLERS", " bot_a , bot_b ")
        mgr = HostPrivilegeManager(data_dir=str(tmp_path))
        assert mgr.grant("pack_a", "p1", caller_id="bot_a").success is True
        assert mgr.grant("pack_a", "p2", caller_id="bot_b").success is True

    def test_env_empty_no_effect(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_PRIVILEGE_TRUSTED_CALLERS", "")
        mgr = HostPrivilegeManager(data_dir=str(tmp_path))
        result = mgr.grant("pack_a", "priv_x", caller_id="unknown")
        assert result.success is False
