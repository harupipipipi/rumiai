"""tests/test_security_guards.py — セキュリティガード強化テスト

Wave 1-1: restart 保護（レート制限 + graceful flag）
Wave 1-2: --permissive ガード強化（lockfile チェック）
"""
import time
from pathlib import Path

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
        mod.clear_kernel_restart_request()
        obj = _make_mixin()
        result = obj._panel_restart_kernel()
        assert result.get("restarting") is True
        assert mod.is_kernel_restart_requested() is True

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
        mod.clear_kernel_restart_request()
        obj = _make_mixin()
        result = obj._panel_restart_kernel()
        assert result.get("restarting") is True
        assert mod.is_kernel_restart_requested() is True


# ======================================================================
# Wave 1-2: retired permissive guard boundary tests
# ======================================================================


def _assert_permissive_surface_is_retired() -> None:
    """The production root has no legacy guard or permissive switch."""
    import app

    source = Path(app.__file__).read_text(encoding="utf-8")
    assert not hasattr(app, "_check_permissive_production_guard")
    assert "RUMI_ALLOW_PERMISSIVE" not in source
    assert "permissive.lock" not in source
    with pytest.raises(SystemExit):
        app._parser().parse_args(["--permissive"])


class TestPermissiveGuard:
    """The removed permissive API stays absent under every old env shape."""

    def test_no_env_exits(self, monkeypatch):
        """No environment variables can restore the retired switch."""
        monkeypatch.delenv("RUMI_ALLOW_PERMISSIVE", raising=False)
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        monkeypatch.delenv("RUMI_USER_DATA", raising=False)
        _assert_permissive_surface_is_retired()

    def test_env_ok_but_no_lockfile_exits(self, monkeypatch, tmp_path):
        """An old allow env without a lockfile remains non-authoritative."""
        monkeypatch.setenv("RUMI_ALLOW_PERMISSIVE", "true")
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        _assert_permissive_surface_is_retired()

    def test_lockfile_ok_but_no_env_exits(self, monkeypatch, tmp_path):
        """A stale lockfile without an allow env remains non-authoritative."""
        monkeypatch.delenv("RUMI_ALLOW_PERMISSIVE", raising=False)
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        lock = tmp_path / "permissive.lock"
        lock.touch()
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        _assert_permissive_surface_is_retired()

    def test_both_ok_returns(self, monkeypatch, tmp_path):
        """Even both stale opt-in inputs cannot add a parser surface."""
        monkeypatch.setenv("RUMI_ALLOW_PERMISSIVE", "true")
        lock = tmp_path / "permissive.lock"
        lock.touch()
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        _assert_permissive_surface_is_retired()
        import app

        assert app._parser().parse_args(["--headless"]).headless is True

    def test_dev_environment_with_lockfile_returns(self, monkeypatch, tmp_path):
        """Development labels cannot reintroduce the retired production flag."""
        monkeypatch.delenv("RUMI_ALLOW_PERMISSIVE", raising=False)
        monkeypatch.setenv("RUMI_ENVIRONMENT", "dev")
        lock = tmp_path / "permissive.lock"
        lock.touch()
        monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
        _assert_permissive_surface_is_retired()
