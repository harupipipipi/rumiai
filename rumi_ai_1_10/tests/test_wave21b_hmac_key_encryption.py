"""
W21-B: HMACKeyManager 鍵暗号化保存のユニットテスト

conftest.py が core_runtime パッケージを __init__.py 実行なしで
sys.modules に登録するため、import は core_runtime.* 名前空間を使用する。
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# conftest.py が core_runtime スタブを登録した上でここに到達する。
# サブモジュールのダミーは conftest では登録されないため、ここで補完する。
# ---------------------------------------------------------------------------
_PKG = "core_runtime"

# paths ダミー
_dummy_paths = types.ModuleType(f"{_PKG}.paths")
_dummy_paths.BASE_DIR = Path("/tmp/dummy_base_dir")
sys.modules.setdefault(f"{_PKG}.paths", _dummy_paths)

# audit_logger ダミー — テスト全体で共有する MagicMock
_dummy_audit_instance = MagicMock()
_dummy_audit = types.ModuleType(f"{_PKG}.audit_logger")
_dummy_audit.get_audit_logger = MagicMock(return_value=_dummy_audit_instance)
sys.modules.setdefault(f"{_PKG}.audit_logger", _dummy_audit)

# di_container ダミー
_dummy_di = types.ModuleType(f"{_PKG}.di_container")
_dummy_di.get_container = MagicMock(return_value=MagicMock())
sys.modules.setdefault(f"{_PKG}.di_container", _dummy_di)

# pack_api_server ダミー
_dummy_pack_api = types.ModuleType(f"{_PKG}.pack_api_server")
class _APIResponse:
    def __init__(self, success, data=None, error=None):
        self.success, self.data, self.error = success, data, error
_dummy_pack_api.APIResponse = _APIResponse
sys.modules.setdefault(f"{_PKG}.pack_api_server", _dummy_pack_api)

# ---------------------------------------------------------------------------
# テスト対象のインポート
# ---------------------------------------------------------------------------
from core_runtime.hmac_key_manager import (  # noqa: E402
    HMACKeyManager,
    HMACKey,
    _FERNET_AVAILABLE,
)

# cryptography が実環境にあるか
try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

_MOD = "core_runtime.hmac_key_manager"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_audit_mock():
    _dummy_audit_instance.reset_mock()
    yield

@pytest.fixture()
def keys_path(tmp_path):
    return str(tmp_path / "hmac_keys.json")


# ===========================================================================
# 1. cryptography あり + strict: 暗号化保存される
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestEncryptedSaveStrict:
    def test_encrypted_save_strict(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        mgr = HMACKeyManager(keys_path=keys_path)
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("encryption") == "fernet"
        assert "payload" in data
        assert data.get("version") == "1.0"


# ===========================================================================
# 2. cryptography あり + strict: 暗号化ファイルが正常にロードされる
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestEncryptedLoadStrict:
    def test_encrypted_load_strict(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        mgr1 = HMACKeyManager(keys_path=keys_path)
        key1 = mgr1.get_active_key()
        mgr2 = HMACKeyManager(keys_path=keys_path)
        key2 = mgr2.get_active_key()
        assert key1 == key2


# ===========================================================================
# 3. cryptography あり + permissive: 暗号化保存される
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestEncryptedSavePermissive:
    def test_encrypted_save_permissive(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "permissive")
        mgr = HMACKeyManager(keys_path=keys_path)
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("encryption") == "fernet"


# ===========================================================================
# 4. cryptography なし + strict: RuntimeError
# ===========================================================================
class TestNoCryptoStrict:
    def test_no_crypto_strict_raises(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        with patch(f"{_MOD}._FERNET_AVAILABLE", False), \
             patch(f"{_MOD}._Fernet", None):
            with pytest.raises(RuntimeError, match="cryptography"):
                HMACKeyManager(keys_path=keys_path)


# ===========================================================================
# 5. cryptography なし + permissive: 平文フォールバック
# ===========================================================================
class TestNoCryptoPermissive:
    def test_no_crypto_permissive_plaintext_fallback(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "permissive")
        with patch(f"{_MOD}._FERNET_AVAILABLE", False), \
             patch(f"{_MOD}._Fernet", None):
            mgr = HMACKeyManager(keys_path=keys_path)
            key = mgr.get_active_key()
            assert isinstance(key, str) and len(key) > 0
            with open(keys_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert "encryption" not in data
            assert "keys" in data


# ===========================================================================
# 6. レガシー平文 → ロード → 次回保存で暗号化マイグレーション
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestLegacyPlaintextMigration:
    def test_legacy_plaintext_migration(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        keys_path = tmp_path / "hmac_keys.json"
        legacy_data = {
            "version": "1.0",
            "updated_at": "2025-01-01T00:00:00Z",
            "grace_period_seconds": 86400,
            "keys": [{
                "key": "legacy_test_key_value_12345",
                "created_at": "2025-01-01T00:00:00Z",
                "rotated_at": None,
                "is_active": True,
            }],
        }
        keys_path.write_text(json.dumps(legacy_data), encoding="utf-8")
        mgr = HMACKeyManager(keys_path=str(keys_path))
        assert mgr.get_active_key() == "legacy_test_key_value_12345"
        mgr.rotate()
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("encryption") == "fernet"
        assert "payload" in data


# ===========================================================================
# 7. 暗号化鍵ファイル消失 → バックアップ + 新規生成
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestEncKeyLostRecovery:
    def test_enc_key_lost_recovery(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        keys_path = str(tmp_path / "hmac_keys.json")
        enc_key_path = tmp_path / "hmac_keys.key"
        mgr1 = HMACKeyManager(keys_path=keys_path)
        key1 = mgr1.get_active_key()
        assert enc_key_path.exists()
        enc_key_path.unlink()
        mgr2 = HMACKeyManager(keys_path=keys_path)
        key2 = mgr2.get_active_key()
        assert key1 != key2
        assert (tmp_path / "hmac_keys.json.bak").exists()


# ===========================================================================
# 8. 暗号化鍵ファイルのパーミッションが 0o600
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
@pytest.mark.skipif(os.name == "nt", reason="Unix only")
class TestEncKeyFilePermissions:
    def test_enc_key_file_permissions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        keys_path = str(tmp_path / "hmac_keys.json")
        HMACKeyManager(keys_path=keys_path)
        enc_key_path = tmp_path / "hmac_keys.key"
        assert enc_key_path.exists()
        mode = oct(enc_key_path.stat().st_mode & 0o777)
        assert mode == oct(0o600)


# ===========================================================================
# 9. 暗号化ファイルの JSON 構造
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestEncryptedFileJsonStructure:
    def test_encrypted_file_json_structure(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        HMACKeyManager(keys_path=keys_path)
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert set(data.keys()) == {"version", "encryption", "payload"}
        assert data["version"] == "1.0"
        assert data["encryption"] == "fernet"
        assert isinstance(data["payload"], str) and len(data["payload"]) > 0


# ===========================================================================
# 10. 暗号化 → 復号ラウンドトリップ
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestEncryptDecryptRoundtrip:
    def test_encrypt_decrypt_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        keys_path = str(tmp_path / "hmac_keys.json")
        mgr = HMACKeyManager(keys_path=keys_path)
        original = '{"test": "data", "number": 42}'
        encrypted = mgr._encrypt_data(original)
        decrypted = mgr._decrypt_data(encrypted)
        assert decrypted == original


# ===========================================================================
# 11. payload 改ざん → バックアップ + 新規生成
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestTamperedPayloadRecovery:
    def test_tampered_payload_recovery(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        keys_path = tmp_path / "hmac_keys.json"
        mgr1 = HMACKeyManager(keys_path=str(keys_path))
        key1 = mgr1.get_active_key()
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["payload"] = "TAMPERED_INVALID_PAYLOAD_DATA"
        keys_path.write_text(json.dumps(data), encoding="utf-8")
        mgr2 = HMACKeyManager(keys_path=str(keys_path))
        key2 = mgr2.get_active_key()
        assert key1 != key2
        assert (tmp_path / "hmac_keys.json.bak").exists()


# ===========================================================================
# 12. _is_encrypted_format() の判定
# ===========================================================================
class TestIsEncryptedFormat:
    def test_encrypted_true(self):
        assert HMACKeyManager._is_encrypted_format(
            {"version": "1.0", "encryption": "fernet", "payload": "x"}) is True

    def test_plaintext_false(self):
        assert HMACKeyManager._is_encrypted_format(
            {"version": "1.0", "keys": []}) is False

    def test_missing_payload_false(self):
        assert HMACKeyManager._is_encrypted_format(
            {"version": "1.0", "encryption": "fernet"}) is False

    def test_wrong_encryption_false(self):
        assert HMACKeyManager._is_encrypted_format(
            {"version": "1.0", "encryption": "aes", "payload": "x"}) is False

    def test_non_dict_false(self):
        assert HMACKeyManager._is_encrypted_format("string") is False
        assert HMACKeyManager._is_encrypted_format(None) is False


# ===========================================================================
# 13. 平文フォールバック時に監査ログ
# ===========================================================================
class TestPlaintextFallbackAuditLog:
    def test_plaintext_fallback_audit_log(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "permissive")
        _dummy_audit_instance.reset_mock()
        with patch(f"{_MOD}._FERNET_AVAILABLE", False), \
             patch(f"{_MOD}._Fernet", None):
            HMACKeyManager(keys_path=keys_path)
        calls = _dummy_audit_instance.log_security_event.call_args_list
        found = any(
            c.kwargs.get("event_type") == "hmac_key_plaintext_fallback"
            and c.kwargs.get("severity") == "warning"
            for c in calls
        )
        assert found, f"plaintext_fallback audit not found. Calls: {calls}"


# ===========================================================================
# 14. マイグレーション時に監査ログ
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestMigrationAuditLog:
    def test_migration_audit_log(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        keys_path = tmp_path / "hmac_keys.json"
        legacy_data = {
            "version": "1.0",
            "updated_at": "2025-01-01T00:00:00Z",
            "grace_period_seconds": 86400,
            "keys": [{
                "key": "migration_test_key_abc",
                "created_at": "2025-01-01T00:00:00Z",
                "rotated_at": None,
                "is_active": True,
            }],
        }
        keys_path.write_text(json.dumps(legacy_data), encoding="utf-8")
        _dummy_audit_instance.reset_mock()
        HMACKeyManager(keys_path=str(keys_path))
        calls = _dummy_audit_instance.log_security_event.call_args_list
        found = any(
            c.kwargs.get("event_type") == "hmac_key_legacy_migration"
            and c.kwargs.get("severity") == "info"
            for c in calls
        )
        assert found, f"legacy_migration audit not found. Calls: {calls}"


# ===========================================================================
# 15. rotate() が暗号化モードでも動作する
# ===========================================================================
@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
class TestRotateWithEncryption:
    def test_rotate_with_encryption(self, keys_path, monkeypatch):
        monkeypatch.setenv("RUMI_SECURITY_MODE", "strict")
        mgr = HMACKeyManager(keys_path=keys_path)
        old_key = mgr.get_active_key()
        new_key = mgr.rotate()
        assert new_key != old_key
        assert mgr.get_active_key() == new_key
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("encryption") == "fernet"
        mgr2 = HMACKeyManager(keys_path=keys_path)
        assert mgr2.get_active_key() == new_key
        assert mgr2.verify_token(old_key) is True
