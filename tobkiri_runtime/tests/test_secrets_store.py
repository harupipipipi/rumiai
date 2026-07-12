"""tests/test_secrets_store.py – SecretsStore 単体テスト"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# テスト用固定キー（各テストで monkeypatch 経由で注入）
_TEST_KEY = Fernet.generate_key().decode("utf-8")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """全テスト共通: 環境変数とグローバル状態を隔離する"""
    monkeypatch.setenv("RUMI_SECRETS_KEY", _TEST_KEY)
    # PLAINTEXT ポリシーをデフォルト (auto) にリセット
    monkeypatch.delenv("RUMI_SECRETS_ALLOW_PLAINTEXT", raising=False)


@pytest.fixture()
def store(tmp_path):
    """隔離された SecretsStore を返す"""
    from core_runtime.secrets_store import SecretsStore
    return SecretsStore(secrets_dir=str(tmp_path / "secrets"))


# ──────────────────────────────────────────────
# 正常系
# ──────────────────────────────────────────────

class TestSetAndListKeys:
    """set_secret → list_keys の正常系"""

    def test_set_and_list(self, store):
        result = store.set_secret("MY_API_KEY", "secret_value_123")
        assert result.success is True
        assert result.key == "MY_API_KEY"
        assert result.created is True

        keys = store.list_keys()
        assert len(keys) == 1
        assert keys[0].key == "MY_API_KEY"
        assert keys[0].exists is True
        assert keys[0].deleted is False

    def test_set_overwrite(self, store):
        store.set_secret("TOKEN", "v1")
        r2 = store.set_secret("TOKEN", "v2")
        assert r2.success is True
        assert r2.created is False  # 上書き

        keys = store.list_keys()
        assert len(keys) == 1

    def test_set_multiple_keys(self, store):
        store.set_secret("KEY_A", "a")
        store.set_secret("KEY_B", "b")
        store.set_secret("KEY_C", "c")

        keys = store.list_keys()
        assert len(keys) == 3
        key_names = {k.key for k in keys}
        assert key_names == {"KEY_A", "KEY_B", "KEY_C"}


class TestDeleteSecret:
    """delete_secret の正常系"""

    def test_delete_existing(self, store):
        store.set_secret("TO_DELETE", "val")
        result = store.delete_secret("TO_DELETE")
        assert result.success is True
        assert result.key == "TO_DELETE"

    def test_delete_nonexistent(self, store):
        result = store.delete_secret("NONEXISTENT")
        assert result.success is False
        assert "not found" in result.error.lower()


# ──────────────────────────────────────────────
# 暗号化 / 復号 ラウンドトリップ
# ──────────────────────────────────────────────

class TestEncryptDecryptRoundtrip:
    """暗号化/復号のラウンドトリップ"""

    def test_roundtrip(self, store):
        original = "super_secret_value_!@#$%"
        store.set_secret("ROUND_TRIP", original)

        # 内部メソッドで復号値を確認
        decrypted = store._read_value("ROUND_TRIP")
        assert decrypted == original

    def test_stored_value_is_encrypted(self, store, tmp_path):
        store.set_secret("ENC_CHECK", "plaintext_value")

        # ファイルを直接読んで暗号化されていることを確認
        path = tmp_path / "secrets" / "ENC_CHECK.json"
        assert path.exists()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Fernet トークンは "gAAAAA" で始まる
        assert data["value"].startswith("gAAAAA")
        assert data["value"] != "plaintext_value"

    def test_roundtrip_unicode(self, store):
        original = "日本語の秘密値🔐"
        store.set_secret("UNICODE_KEY", original)
        assert store._read_value("UNICODE_KEY") == original

    def test_roundtrip_empty_string(self, store):
        store.set_secret("EMPTY_VAL", "")
        assert store._read_value("EMPTY_VAL") == ""

    def test_key_file_follows_custom_secrets_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RUMI_SECRETS_KEY", raising=False)
        secrets_dir = tmp_path / "custom" / "secrets"

        from core_runtime.secrets_store import SecretsStore

        store = SecretsStore(secrets_dir=str(secrets_dir))
        result = store.set_secret("FOLLOW_DIR", "value")

        assert result.success is True
        assert (tmp_path / "custom" / ".secrets_key").exists()
        assert not (tmp_path / "user_data" / ".secrets_key").exists()


# ──────────────────────────────────────────────
# KEY バリデーション
# ──────────────────────────────────────────────

class TestKeyValidation:
    """不正キーの拒否"""

    @pytest.mark.parametrize(
        "bad_key",
        [
            "",               # 空
            "lowercase",      # 小文字
            "HAS SPACE",      # スペース
            "HAS-DASH",       # ハイフン
            "HAS.DOT",        # ドット
            "A" * 65,         # 65文字 (超過)
            "日本語",          # 非ASCII
            "../TRAVERSAL",   # パストラバーサル
        ],
    )
    def test_reject_invalid_key_on_set(self, store, bad_key):
        result = store.set_secret(bad_key, "value")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.parametrize(
        "good_key",
        [
            "A",
            "MY_KEY",
            "KEY_123",
            "A" * 64,         # ちょうど64文字
            "ALL_UPPER_CASE_WITH_NUMBERS_0123456789",
        ],
    )
    def test_accept_valid_key(self, store, good_key):
        result = store.set_secret(good_key, "value")
        assert result.success is True

    def test_validate_key_static(self):
        from core_runtime.secrets_store import SecretsStore
        assert SecretsStore.validate_key("") is not None
        assert SecretsStore.validate_key("lowercase") is not None
        assert SecretsStore.validate_key("VALID_KEY") is None


# ──────────────────────────────────────────────
# Tombstone 動作
# ──────────────────────────────────────────────

class TestTombstoneBehavior:
    """delete 後の tombstone 動作"""

    def test_deleted_key_shows_in_list_as_deleted(self, store):
        store.set_secret("TOMBSTONE_KEY", "val")
        store.delete_secret("TOMBSTONE_KEY")

        keys = store.list_keys()
        assert len(keys) == 1
        meta = keys[0]
        assert meta.key == "TOMBSTONE_KEY"
        assert meta.exists is False
        assert meta.deleted is True
        assert meta.deleted_at is not None

    def test_has_secret_returns_false_after_delete(self, store):
        store.set_secret("CHECK_KEY", "val")
        assert store.has_secret("CHECK_KEY") is True

        store.delete_secret("CHECK_KEY")
        assert store.has_secret("CHECK_KEY") is False

    def test_read_value_returns_none_after_delete(self, store):
        store.set_secret("READ_KEY", "val")
        assert store._read_value("READ_KEY") == "val"

        store.delete_secret("READ_KEY")
        assert store._read_value("READ_KEY") is None

    def test_re_set_after_delete(self, store):
        store.set_secret("REVIVE_KEY", "v1")
        store.delete_secret("REVIVE_KEY")

        result = store.set_secret("REVIVE_KEY", "v2")
        assert result.success is True
        assert result.created is True  # tombstone 上書きは created=True

        assert store.has_secret("REVIVE_KEY") is True
        assert store._read_value("REVIVE_KEY") == "v2"


# ──────────────────────────────────────────────
# 平文ポリシー (RUMI_SECRETS_ALLOW_PLAINTEXT)
# ──────────────────────────────────────────────

class TestPlaintextPolicy:
    """RUMI_SECRETS_ALLOW_PLAINTEXT の動作"""

    @staticmethod
    def _write_plaintext_secret(secrets_dir: Path, key: str, value: str):
        """テスト用: 平文の secret ファイルを直接書き込む"""
        secrets_dir.mkdir(parents=True, exist_ok=True)
        path = secrets_dir / f"{key}.json"
        data = {
            "key": key,
            "value": value,  # 平文（暗号化なし）
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "deleted_at": None,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_auto_allows_plaintext_then_migrates(self, monkeypatch, tmp_path):
        """auto モード: 平文 secret があれば読み込み許可 → 自動マイグレーション"""
        monkeypatch.setenv("RUMI_SECRETS_ALLOW_PLAINTEXT", "auto")
        monkeypatch.setenv("RUMI_SECURITY_MODE", "permissive")
        secrets_dir = tmp_path / "secrets"

        # 平文 secret を直接書き込む
        self._write_plaintext_secret(secrets_dir, "PLAIN_KEY", "plain_value")

        from core_runtime.secrets_store import SecretsStore
        s = SecretsStore(secrets_dir=str(secrets_dir))

        # 平文が読める (auto モード: マイグレーションマーカーなし → 許可)
        val = s._read_value("PLAIN_KEY")
        assert val == "plain_value"

        # 自動マイグレーション後、ファイルは暗号化済み
        with open(secrets_dir / "PLAIN_KEY.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["value"].startswith("gAAAAA")

    def test_false_rejects_plaintext(self, monkeypatch, tmp_path):
        """false モード: 平文 secret の読み込みを拒否"""
        monkeypatch.setenv("RUMI_SECRETS_ALLOW_PLAINTEXT", "false")
        secrets_dir = tmp_path / "secrets"

        self._write_plaintext_secret(secrets_dir, "PLAIN_KEY", "plain_value")

        from core_runtime.secrets_store import SecretsStore
        s = SecretsStore(secrets_dir=str(secrets_dir))

        # 平文は拒否される → None
        val = s._read_value("PLAIN_KEY")
        assert val is None

    def test_true_allows_plaintext(self, monkeypatch, tmp_path):
        """true モード: 平文 secret の読み込みを常に許可"""
        monkeypatch.setenv("RUMI_SECRETS_ALLOW_PLAINTEXT", "true")
        secrets_dir = tmp_path / "secrets"

        self._write_plaintext_secret(secrets_dir, "PLAIN_KEY", "plain_value")

        from core_runtime.secrets_store import SecretsStore
        s = SecretsStore(secrets_dir=str(secrets_dir))

        val = s._read_value("PLAIN_KEY")
        assert val == "plain_value"

    def test_auto_migration_marker(self, monkeypatch, tmp_path):
        """auto モード: 全暗号化完了後にマーカーが作成される"""
        monkeypatch.setenv("RUMI_SECRETS_ALLOW_PLAINTEXT", "auto")
        monkeypatch.setenv("RUMI_SECURITY_MODE", "permissive")
        secrets_dir = tmp_path / "secrets"

        # 暗号化済み secret のみの状態で初期化
        from core_runtime.secrets_store import SecretsStore
        s = SecretsStore(secrets_dir=str(secrets_dir))
        s.set_secret("ENC_ONLY", "encrypted_value")

        # マーカーが作成されているか確認
        marker = secrets_dir / ".migration_complete"
        assert marker.exists()


# ──────────────────────────────────────────────
# ジャーナル
# ──────────────────────────────────────────────

class TestJournal:
    """ジャーナル書き込みの検証"""

    def test_journal_written_on_set(self, store, tmp_path):
        store.set_secret("JOURNAL_KEY", "val")

        journal_path = tmp_path / "secrets" / "journal.jsonl"
        assert journal_path.exists()
        lines = journal_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["action"] == "set"
        assert entry["key"] == "JOURNAL_KEY"

    def test_journal_written_on_delete(self, store, tmp_path):
        store.set_secret("DEL_J_KEY", "val")
        store.delete_secret("DEL_J_KEY")

        journal_path = tmp_path / "secrets" / "journal.jsonl"
        lines = journal_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 2
        last = json.loads(lines[-1])
        assert last["action"] == "deleted"
        assert last["key"] == "DEL_J_KEY"


# ──────────────────────────────────────────────
# ハンドラ層バリデーション (T-016a)
# ──────────────────────────────────────────────

class TestSecretsHandlersValidation:
    """secrets_handlers.py の早期バリデーション"""

    @staticmethod
    def _make_mixin():
        from core_runtime.api.secrets_handlers import SecretsHandlersMixin
        return SecretsHandlersMixin()

    def test_set_rejects_invalid_key(self):
        mixin = self._make_mixin()
        result = mixin._secrets_set({"key": "lower_case", "value": "v"})
        assert result["success"] is False
        assert "Invalid key" in result["error"]

    def test_set_rejects_oversized_value(self):
        mixin = self._make_mixin()
        big_value = "x" * (1_048_576 + 1)
        result = mixin._secrets_set({"key": "VALID_KEY", "value": big_value})
        assert result["success"] is False
        assert "too large" in result["error"].lower()

    def test_delete_rejects_invalid_key(self):
        mixin = self._make_mixin()
        result = mixin._secrets_delete({"key": "bad-key"})
        assert result["success"] is False
        assert "Invalid key" in result["error"]
