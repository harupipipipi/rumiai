"""
W20-C: VULN-C03 — secrets_store plaintext fallback hardening tests.

Tests for RUMI_SECURITY_MODE integration with _is_plaintext_allowed()
and CRITICAL audit logging on plaintext fallback.
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# core_runtime パッケージのダミー登録
# secrets_store.py は相対インポート (.audit_logger, .di_container) を
# 実行時にのみ使用するが、パッケージとして認識させるためダミーを登録する。
# ---------------------------------------------------------------------------
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# __init__.py の大量インポートを回避するため、ダミーパッケージを先に登録
if "core_runtime" not in sys.modules:
    _pkg = types.ModuleType("core_runtime")
    _pkg.__path__ = [str(Path(__file__).resolve().parent.parent / "core_runtime")]
    _pkg.__package__ = "core_runtime"
    sys.modules["core_runtime"] = _pkg

# 相対インポート先のダミーモジュール
for _mod_name in ("audit_logger", "di_container"):
    _fqn = f"core_runtime.{_mod_name}"
    if _fqn not in sys.modules:
        sys.modules[_fqn] = types.ModuleType(_fqn)

from core_runtime.secrets_store import (  # noqa: E402
    SecretsStore,
    _crypto,
    _FERNET_PREFIX,
)
from cryptography.fernet import Fernet  # noqa: E402

# テスト用固定 Fernet キー
TEST_FERNET_KEY = Fernet.generate_key().decode("utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_crypto(monkeypatch):
    """各テスト前に暗号化バックエンドをリセットし、固定キーを使用する。"""
    monkeypatch.setenv("RUMI_SECRETS_KEY", TEST_FERNET_KEY)
    _crypto._initialized = False
    _crypto._fernet = None
    yield
    _crypto._initialized = False
    _crypto._fernet = None


@pytest.fixture()
def secrets_dir(tmp_path):
    """隔離された secrets ディレクトリを返す。"""
    d = tmp_path / "secrets"
    d.mkdir()
    return d


def _write_plaintext_secret(secrets_dir: Path, key: str, value: str) -> None:
    """平文のシークレット JSON ファイルを直接作成する。"""
    path = secrets_dir / f"{key}.json"
    path.write_text(json.dumps({
        "key": key,
        "value": value,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "deleted_at": None,
    }, ensure_ascii=False), encoding="utf-8")


def _write_migration_marker(secrets_dir: Path) -> None:
    """マイグレーション完了マーカーを作成する。"""
    marker = secrets_dir / ".migration_complete"
    marker.write_text(json.dumps({
        "completed_at": "2025-01-01T00:00:00Z",
        "note": "All secrets migrated to encrypted storage.",
    }), encoding="utf-8")


def _make_store(secrets_dir: Path, monkeypatch, *,
                security_mode: str | None = None,
                plaintext_policy: str = "auto") -> SecretsStore:
    """指定した環境変数で SecretsStore を生成する。"""
    monkeypatch.setenv("RUMI_SECRETS_ALLOW_PLAINTEXT", plaintext_policy)
    if security_mode is not None:
        monkeypatch.setenv("RUMI_SECURITY_MODE", security_mode)
    else:
        monkeypatch.delenv("RUMI_SECURITY_MODE", raising=False)
    return SecretsStore(secrets_dir=str(secrets_dir))


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------

class TestSecurityModeStrictAutoPlaintextBlocked:
    """SECURITY_MODE=strict + policy=auto → 平文禁止（マーカー有無に関係なく）"""

    def test_strict_auto_no_marker(self, secrets_dir, monkeypatch):
        """strict + auto + マーカーなし → 平文禁止"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="strict", plaintext_policy="auto")
        result = store._read_value("API_KEY")
        assert result is None, "strict モードでは auto でも平文を読めてはいけない"

    def test_strict_auto_with_marker(self, secrets_dir, monkeypatch):
        """strict + auto + マーカーあり → 平文禁止"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        _write_migration_marker(secrets_dir)
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="strict", plaintext_policy="auto")
        result = store._read_value("API_KEY")
        assert result is None, "strict + マーカーありでも平文は禁止"


class TestSecurityModeStrictExplicitPolicy:
    """SECURITY_MODE=strict + 明示的ポリシー"""

    def test_strict_true_allows_plaintext(self, secrets_dir, monkeypatch):
        """strict + policy=true → 平文許可（明示的 true は尊重）"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="strict", plaintext_policy="true")
        result = store._read_value("API_KEY")
        assert result == "secret123", "明示的 true は SECURITY_MODE に関係なく尊重"

    def test_strict_false_blocks_plaintext(self, secrets_dir, monkeypatch):
        """strict + policy=false → 平文禁止"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="strict", plaintext_policy="false")
        result = store._read_value("API_KEY")
        assert result is None, "policy=false は常に平文禁止"


class TestSecurityModePermissive:
    """SECURITY_MODE=permissive + policy=auto → 従来のマーカーベース判定"""

    def test_permissive_auto_no_marker_allows(self, secrets_dir, monkeypatch):
        """permissive + auto + マーカーなし → 平文許可"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="permissive", plaintext_policy="auto")
        result = store._read_value("API_KEY")
        assert result == "secret123", "permissive + マーカーなし → 平文許可"

    def test_permissive_auto_with_marker_blocks(self, secrets_dir, monkeypatch):
        """permissive + auto + マーカーあり → 平文禁止"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        _write_migration_marker(secrets_dir)
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="permissive", plaintext_policy="auto")
        result = store._read_value("API_KEY")
        assert result is None, "permissive + マーカーあり → 平文禁止"


class TestSecurityModeDefault:
    """SECURITY_MODE 未設定（デフォルト strict）"""

    def test_default_mode_auto_blocks(self, secrets_dir, monkeypatch):
        """SECURITY_MODE 未設定 + policy=auto → 平文禁止（デフォルト strict）"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode=None, plaintext_policy="auto")
        result = store._read_value("API_KEY")
        assert result is None, "デフォルト(strict) + auto → 平文禁止"


class TestAuditLogOnPlaintextFallback:
    """平文フォールバック時の CRITICAL 監査ログ"""

    @patch.object(SecretsStore, "_audit")
    def test_plaintext_fallback_triggers_audit(self, mock_audit,
                                                secrets_dir, monkeypatch):
        """平文フォールバック発生時に監査ログが記録される"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="permissive", plaintext_policy="auto")
        store._read_value("API_KEY")

        # plaintext_fallback イベントが呼ばれたか確認
        fallback_calls = [
            c for c in mock_audit.call_args_list
            if c[0][0] == "plaintext_fallback"
        ]
        assert len(fallback_calls) >= 1, "plaintext_fallback 監査ログが記録されるべき"

    @patch.object(SecretsStore, "_audit")
    def test_audit_severity_is_critical(self, mock_audit,
                                        secrets_dir, monkeypatch):
        """監査ログの severity が critical である"""
        _write_plaintext_secret(secrets_dir, "API_KEY", "secret123")
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="permissive", plaintext_policy="auto")
        store._read_value("API_KEY")

        fallback_calls = [
            c for c in mock_audit.call_args_list
            if c[0][0] == "plaintext_fallback"
        ]
        assert len(fallback_calls) >= 1, "監査ログが記録されていない"
        details = fallback_calls[0][0][2]
        assert details.get("severity") == "critical", (
            f"severity は critical であるべき: got {details.get('severity')}"
        )


class TestRegressionEncryptedSecrets:
    """回帰テスト: 暗号化済みシークレットと新規保存"""

    def test_encrypted_secret_read(self, secrets_dir, monkeypatch):
        """暗号化済みシークレットの読み込みが影響を受けない"""
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="strict", plaintext_policy="auto")
        store.set_secret("DB_PASS", "mypassword", actor="test")
        result = store._read_value("DB_PASS")
        assert result == "mypassword", "暗号化済みシークレットは正常に読める"

    def test_new_secret_is_encrypted(self, secrets_dir, monkeypatch):
        """新規シークレットの保存が暗号化される"""
        store = _make_store(secrets_dir, monkeypatch,
                            security_mode="strict", plaintext_policy="auto")
        store.set_secret("TOKEN", "abc123", actor="test")
        path = secrets_dir / "TOKEN.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["value"].startswith(_FERNET_PREFIX), (
            "保存された value は Fernet 暗号化されているべき"
        )
