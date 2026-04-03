"""tests/test_security_guards.py — セキュリティガード強化テスト

Wave 1-1: os._exit(42) 保護（レート制限）
Wave 1-2: --permissive ガード強化（lockfile チェック）
"""
import time
import pytest


# ======================================================================
# Wave 1-1: restart レート制限テスト
# ======================================================================


def _make_mixin():
    """テスト用に ControlPanelHandlersMixin のインスタンスを生成する"""
    from core_runtime.api.control_panel_handlers import ControlPanelHandlersMixin
    cls = type("_Stub", (ControlPanelHandlersMixin,), {})
    return cls()


class TestRestartRateLimit:
    """_panel_restart_kernel のレート制限テスト"""

    def test_first_call_succeeds(self, monkeypatch):
        """初回呼び出しは成功する"""
        import core_runtime.api.control_panel_handlers as mod
        monkeypatch.setattr(mod, "_last_restart_time", 0.0)
        monkeypatch.setattr("os._exit", lambda code: None)
        obj = _make_mixin()
        result = obj._panel_restart_kernel()
        assert result.get("restarting") is True

    def test_second_call_within_60s_rejected(self, monkeypatch):
        """60秒以内の2回目は HTTP 429 で拒否される"""
        import core_runtime.api.control_panel_handlers as mod
        monkeypatch.setattr(mod, "_last_restart_time", time.time() - 10)
        obj = _make_mixin()
        result = obj._panel_restart_kernel()
        assert result.get("status_code") == 429
        assert "rate limit" in result.get("error", "").lower()

    def test_call_after_60s_succeeds(self, monkeypatch):
        """60秒経過後の呼び出しは成功する"""
        import core_runtime.api.control_panel_handlers as mod
        monkeypatch.setattr(mod, "_last_restart_time", time.time() - 61)
        monkeypatch.setattr("os._exit", lambda code: None)
        obj = _make_mixin()
        result = obj._panel_restart_kernel()
        assert result.get("restarting") is True


# ======================================================================
# Wave 1-2: permissive ガード強化テスト
# ======================================================================


class TestPermissiveGuard:
    """_check_permissive_production_guard のテスト"""

    def test_no_env_exits(self, monkeypatch):
        """環境変数なしで sys.exit(1) が呼ばれる"""
        monkeypatch.delenv("RUMI_ALLOW_PERMISSIVE", raising=False)
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        monkeypatch.delenv("RUMI_USER_DATA", raising=False)
        from app import _check_permissive_production_guard
        with pytest.raises(SystemExit) as exc_info:
            _check_permissive_production_guard()
        assert exc_info.value.code == 1

    def test_env_ok_but_no_lockfile_exits(self, monkeypatch, tmp_path):
        """環境変数OKだが lockfile がない場合 sys.exit(1)"""
        monkeypatch.setenv("RUMI_ALLOW_PERMISSIVE", "true")
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        from app import _check_permissive_production_guard
        with pytest.raises(SystemExit) as exc_info:
            _check_permissive_production_guard()
        assert exc_info.value.code == 1

    def test_lockfile_ok_but_no_env_exits(self, monkeypatch, tmp_path):
        """lockfile はあるが環境変数がない場合 sys.exit(1)"""
        monkeypatch.delenv("RUMI_ALLOW_PERMISSIVE", raising=False)
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        lock = tmp_path / "permissive.lock"
        lock.touch()
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        from app import _check_permissive_production_guard
        with pytest.raises(SystemExit) as exc_info:
            _check_permissive_production_guard()
        assert exc_info.value.code == 1

    def test_both_ok_returns(self, monkeypatch, tmp_path):
        """環境変数 + lockfile の両方が揃えば正常 return"""
        monkeypatch.setenv("RUMI_ALLOW_PERMISSIVE", "true")
        lock = tmp_path / "permissive.lock"
        lock.touch()
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        from app import _check_permissive_production_guard
        _check_permissive_production_guard()

    def test_dev_environment_with_lockfile_returns(self, monkeypatch, tmp_path):
        """RUMI_ENVIRONMENT=dev + lockfile で正常 return"""
        monkeypatch.delenv("RUMI_ALLOW_PERMISSIVE", raising=False)
        monkeypatch.setenv("RUMI_ENVIRONMENT", "dev")
        lock = tmp_path / "permissive.lock"
        lock.touch()
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        from app import _check_permissive_production_guard
        _check_permissive_production_guard()
