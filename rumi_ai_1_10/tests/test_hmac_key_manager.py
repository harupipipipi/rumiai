"""
test_hmac_key_manager.py - P0: HMAC 鍵管理モジュールのテスト

対象: core_runtime/hmac_key_manager.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core_runtime.hmac_key_manager import (
    HMACKey,
    HMACKeyManager,
    compute_data_hmac,
    generate_or_load_signing_key,
    verify_data_hmac,
)


# ===================================================================
# generate_or_load_signing_key
# ===================================================================

class TestGenerateOrLoadSigningKey:

    def test_generates_new_key_when_file_missing(self, tmp_path):
        key_path = tmp_path / "signing.key"
        key = generate_or_load_signing_key(key_path)
        assert isinstance(key, bytes)
        assert len(key) > 0
        assert key_path.exists()

    def test_loads_existing_key_from_file(self, tmp_path):
        key_path = tmp_path / "signing.key"
        key_path.write_text("abcdef0123456789" * 4, encoding="utf-8")
        key = generate_or_load_signing_key(key_path)
        assert key == ("abcdef0123456789" * 4).encode("utf-8")

    def test_prefers_env_var_over_file(self, tmp_path, monkeypatch):
        key_path = tmp_path / "signing.key"
        key_path.write_text("file_key_value_xxxxxxxxxxxxxxxxxxxx", encoding="utf-8")
        env_value = "a" * 64
        monkeypatch.setenv("TEST_SIGNING_KEY", env_value)
        key = generate_or_load_signing_key(key_path, env_var="TEST_SIGNING_KEY")
        assert key == env_value.encode("utf-8")

    def test_ignores_short_env_var(self, tmp_path, monkeypatch):
        key_path = tmp_path / "signing.key"
        monkeypatch.setenv("TEST_SIGNING_KEY", "short")
        key = generate_or_load_signing_key(key_path, env_var="TEST_SIGNING_KEY")
        assert isinstance(key, bytes)
        assert len(key) > 0
        # A new key was generated and written to file
        assert key_path.exists()

    def test_atomic_write_creates_parent_dirs(self, tmp_path):
        key_path = tmp_path / "deep" / "nested" / "signing.key"
        key = generate_or_load_signing_key(key_path)
        assert key_path.exists()
        assert isinstance(key, bytes)

    def test_file_permissions(self, tmp_path):
        key_path = tmp_path / "signing.key"
        generate_or_load_signing_key(key_path)
        if os.name != "nt":
            mode = oct(key_path.stat().st_mode & 0o777)
            assert mode == "0o600"


# ===================================================================
# compute_data_hmac / verify_data_hmac
# ===================================================================

class TestHmacSignVerify:

    def test_compute_returns_hex_string(self):
        key = b"test-secret-key"
        data = {"action": "approve", "pack_id": "test"}
        sig = compute_data_hmac(key, data)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex digest
        int(sig, 16)  # valid hex

    def test_verify_correct_signature(self):
        key = b"test-secret-key"
        data = {"action": "approve", "pack_id": "test"}
        sig = compute_data_hmac(key, data)
        assert verify_data_hmac(key, data, sig) is True

    def test_verify_rejects_wrong_signature(self):
        key = b"test-secret-key"
        data = {"action": "approve", "pack_id": "test"}
        assert verify_data_hmac(key, data, "0" * 64) is False

    def test_verify_rejects_tampered_data(self):
        key = b"test-secret-key"
        data = {"action": "approve", "pack_id": "test"}
        sig = compute_data_hmac(key, data)
        data["pack_id"] = "evil"
        assert verify_data_hmac(key, data, sig) is False

    def test_hmac_key_fields_excluded(self):
        key = b"test-secret-key"
        data = {"action": "approve", "_hmac_signature": "should_be_excluded"}
        sig1 = compute_data_hmac(key, data)
        data2 = {"action": "approve"}
        sig2 = compute_data_hmac(key, data2)
        assert sig1 == sig2

    def test_different_keys_produce_different_signatures(self):
        data = {"value": 42}
        sig1 = compute_data_hmac(b"key-a", data)
        sig2 = compute_data_hmac(b"key-b", data)
        assert sig1 != sig2

    def test_deterministic(self):
        key = b"deterministic-key"
        data = {"x": 1, "y": 2}
        assert compute_data_hmac(key, data) == compute_data_hmac(key, data)

    def test_key_order_independent(self):
        key = b"order-key"
        data1 = {"b": 2, "a": 1}
        data2 = {"a": 1, "b": 2}
        assert compute_data_hmac(key, data1) == compute_data_hmac(key, data2)


# ===================================================================
# HMACKeyManager - 初期化と鍵生成
# ===================================================================

class TestHMACKeyManagerInit:

    def test_creates_key_on_first_init(self, tmp_path):
        keys_path = str(tmp_path / "keys.json")
        mgr = HMACKeyManager(keys_path=keys_path)
        active = mgr.get_active_key()
        assert isinstance(active, str)
        assert len(active) > 0
        assert Path(keys_path).exists()

    def test_loads_existing_keys(self, tmp_path):
        keys_path = str(tmp_path / "keys.json")
        mgr1 = HMACKeyManager(keys_path=keys_path)
        key1 = mgr1.get_active_key()
        mgr2 = HMACKeyManager(keys_path=keys_path)
        key2 = mgr2.get_active_key()
        assert key1 == key2

    def test_creates_parent_dirs(self, tmp_path):
        keys_path = str(tmp_path / "deep" / "nested" / "keys.json")
        mgr = HMACKeyManager(keys_path=keys_path)
        assert Path(keys_path).exists()
        assert mgr.get_active_key()

    def test_handles_corrupt_key_file(self, tmp_path):
        keys_path = tmp_path / "keys.json"
        keys_path.write_text("NOT VALID JSON", encoding="utf-8")
        mgr = HMACKeyManager(keys_path=str(keys_path))
        # Should recover by generating a new key
        assert mgr.get_active_key()

    def test_key_file_atomic_write(self, tmp_path):
        keys_path = str(tmp_path / "keys.json")
        mgr = HMACKeyManager(keys_path=keys_path)
        # Verify the file is valid JSON
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "keys" in data
        assert "version" in data
        assert len(data["keys"]) == 1
        assert data["keys"][0]["is_active"] is True


# ===================================================================
# HMACKeyManager - verify_token
# ===================================================================

class TestHMACKeyManagerVerifyToken:

    def test_verify_active_key(self, tmp_path):
        mgr = HMACKeyManager(keys_path=str(tmp_path / "keys.json"))
        key = mgr.get_active_key()
        assert mgr.verify_token(key) is True

    def test_reject_invalid_token(self, tmp_path):
        mgr = HMACKeyManager(keys_path=str(tmp_path / "keys.json"))
        assert mgr.verify_token("invalid-token-value") is False

    def test_reject_empty_token(self, tmp_path):
        mgr = HMACKeyManager(keys_path=str(tmp_path / "keys.json"))
        assert mgr.verify_token("") is False


# ===================================================================
# HMACKeyManager - rotate
# ===================================================================

class TestHMACKeyManagerRotate:

    def test_rotate_returns_new_key(self, tmp_path):
        mgr = HMACKeyManager(keys_path=str(tmp_path / "keys.json"))
        old_key = mgr.get_active_key()
        new_key = mgr.rotate()
        assert new_key != old_key
        assert mgr.get_active_key() == new_key

    def test_old_key_valid_during_grace_period(self, tmp_path):
        mgr = HMACKeyManager(
            keys_path=str(tmp_path / "keys.json"),
            grace_period_seconds=3600,
        )
        old_key = mgr.get_active_key()
        mgr.rotate()
        assert mgr.verify_token(old_key) is True

    def test_multiple_rotations(self, tmp_path):
        mgr = HMACKeyManager(
            keys_path=str(tmp_path / "keys.json"),
            grace_period_seconds=3600,
        )
        key1 = mgr.get_active_key()
        key2 = mgr.rotate()
        key3 = mgr.rotate()
        assert key1 != key2 != key3
        assert mgr.get_active_key() == key3
        # Both old keys still valid during grace period
        assert mgr.verify_token(key1) is True
        assert mgr.verify_token(key2) is True

    def test_key_info_after_rotation(self, tmp_path):
        mgr = HMACKeyManager(keys_path=str(tmp_path / "keys.json"))
        mgr.rotate()
        info = mgr.get_key_info()
        assert info["active_keys"] == 1
        assert info["grace_period_keys"] >= 1
        assert info["total_keys"] >= 2

    def test_rotation_persisted(self, tmp_path):
        keys_path = str(tmp_path / "keys.json")
        mgr1 = HMACKeyManager(keys_path=keys_path, grace_period_seconds=3600)
        old_key = mgr1.get_active_key()
        new_key = mgr1.rotate()

        mgr2 = HMACKeyManager(keys_path=keys_path, grace_period_seconds=3600)
        assert mgr2.get_active_key() == new_key
        assert mgr2.verify_token(old_key) is True


# ===================================================================
# HMACKeyManager - grace period expiration
# ===================================================================

class TestHMACKeyManagerGracePeriod:

    def test_expired_key_removed_on_reload(self, tmp_path, monkeypatch):
        keys_path = str(tmp_path / "keys.json")
        mgr = HMACKeyManager(keys_path=keys_path, grace_period_seconds=60)
        old_key = mgr.get_active_key()
        mgr.rotate()

        # Simulate time passing beyond grace period
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        monkeypatch.setattr(
            "core_runtime.hmac_key_manager._now_utc", lambda: future
        )

        mgr2 = HMACKeyManager(keys_path=keys_path, grace_period_seconds=60)
        assert mgr2.verify_token(old_key) is False

    def test_key_within_grace_period_survives(self, tmp_path, monkeypatch):
        keys_path = str(tmp_path / "keys.json")
        mgr = HMACKeyManager(keys_path=keys_path, grace_period_seconds=300)
        old_key = mgr.get_active_key()
        mgr.rotate()

        # 100 seconds into a 300-second grace period
        future = datetime.now(timezone.utc) + timedelta(seconds=100)
        monkeypatch.setattr(
            "core_runtime.hmac_key_manager._now_utc", lambda: future
        )

        mgr2 = HMACKeyManager(keys_path=keys_path, grace_period_seconds=300)
        assert mgr2.verify_token(old_key) is True


# ===================================================================
# HMACKeyManager - env var rotation trigger
# ===================================================================

class TestHMACKeyManagerEnvTrigger:

    def test_env_rotate_triggers_rotation(self, tmp_path, monkeypatch):
        keys_path = str(tmp_path / "keys.json")
        mgr1 = HMACKeyManager(keys_path=keys_path)
        key1 = mgr1.get_active_key()

        monkeypatch.setenv("RUMI_HMAC_ROTATE", "true")
        mgr2 = HMACKeyManager(keys_path=keys_path, grace_period_seconds=3600)
        key2 = mgr2.get_active_key()
        assert key2 != key1
        # Old key in grace
        assert mgr2.verify_token(key1) is True
