"""
tests/test_wave21c_permissive_guard_cleanup.py

W21-C: permissive guard 整理のテスト
- 重複チェック削除の確認
- 大文字小文字統一の確認
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# app.py を importlib で安全にロード（副作用回避）
# ---------------------------------------------------------------------------
_APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _load_app():
    spec = importlib.util.spec_from_file_location("_app_under_test", str(_APP_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_app = _load_app()


# =========================================================================
# Group A: _check_permissive_production_guard() 直接テスト
# =========================================================================
class TestCheckPermissiveProductionGuard:
    """_check_permissive_production_guard() の単体テスト"""

    def test_production_exact_exits(self, monkeypatch):
        """テスト1: RUMI_ENVIRONMENT=production → sys.exit(1)"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "production")
        with pytest.raises(SystemExit) as exc_info:
            _app._check_permissive_production_guard()
        assert exc_info.value.code == 1

    def test_production_mixed_case_exits(self, monkeypatch):
        """テスト2: RUMI_ENVIRONMENT=Production (大文字混在) → sys.exit(1)"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "Production")
        with pytest.raises(SystemExit) as exc_info:
            _app._check_permissive_production_guard()
        assert exc_info.value.code == 1

    def test_production_upper_exits(self, monkeypatch):
        """テスト3: RUMI_ENVIRONMENT=PRODUCTION (全大文字) → sys.exit(1)"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "PRODUCTION")
        with pytest.raises(SystemExit) as exc_info:
            _app._check_permissive_production_guard()
        assert exc_info.value.code == 1

    def test_development_does_not_exit(self, monkeypatch):
        """テスト4: RUMI_ENVIRONMENT=development → exit しない"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "development")
        _app._check_permissive_production_guard()

    def test_unset_does_not_exit(self, monkeypatch):
        """テスト5: RUMI_ENVIRONMENT 未設定 → exit しない"""
        monkeypatch.delenv("RUMI_ENVIRONMENT", raising=False)
        _app._check_permissive_production_guard()

    def test_guard_calls_sys_exit_1(self, monkeypatch):
        """テスト7: sys.exit(1) が呼ばれることの直接テスト"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "production")
        with pytest.raises(SystemExit) as exc_info:
            _app._check_permissive_production_guard()
        assert exc_info.value.code == 1
        assert exc_info.value.code != 0

    def test_guard_prints_fatal_to_stderr(self, monkeypatch, capsys):
        """テスト8: stderr に FATAL メッセージが出力される"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "production")
        with pytest.raises(SystemExit):
            _app._check_permissive_production_guard()
        captured = capsys.readouterr()
        assert "FATAL" in captured.err
        assert "--permissive" in captured.err
        assert "production" in captured.err.lower()


# =========================================================================
# Group B: main() フローおよびソースコード検査
# =========================================================================
class TestMainPermissiveFlow:
    """main() 経由の統合テストおよびコード検査"""

    @pytest.fixture(autouse=True)
    def _mock_logging(self, monkeypatch):
        """main() を呼ぶ際に必要な core_runtime.logging_utils のスタブ"""
        stub = types.ModuleType("core_runtime.logging_utils")
        stub.configure_logging = lambda **kw: None
        monkeypatch.setitem(sys.modules, "core_runtime.logging_utils", stub)
        yield

    def test_no_permissive_production_sets_strict(self, monkeypatch):
        """テスト6: --permissive なし + production → strict モード"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "production")
        monkeypatch.delenv("RUMI_SECURITY_MODE", raising=False)
        monkeypatch.setattr(sys, "argv", ["app.py"])
        try:
            _app.main()
        except SystemExit:
            pass
        except Exception:
            pass
        assert os.environ.get("RUMI_SECURITY_MODE") == "strict"

    def test_no_duplicate_env_check_in_main(self):
        """テスト9: main() 内に RUMI_ENVIRONMENT の重複チェックがないこと"""
        source = inspect.getsource(_app.main)
        lines = source.split("\n")
        env_check_lines = [
            line.strip()
            for line in lines
            if "RUMI_ENVIRONMENT" in line
            and "_check_permissive_production_guard" not in line
            and not line.strip().startswith("#")
        ]
        assert len(env_check_lines) == 0, (
            f"main() 内に重複した RUMI_ENVIRONMENT チェックがあります: "
            f"{env_check_lines}"
        )

    def test_permissive_sets_security_mode(self, monkeypatch):
        """テスト10: permissive + 非 production → RUMI_SECURITY_MODE=permissive"""
        monkeypatch.setenv("RUMI_ENVIRONMENT", "development")
        monkeypatch.delenv("RUMI_SECURITY_MODE", raising=False)
        monkeypatch.setattr(sys, "argv", ["app.py", "--permissive"])
        try:
            _app.main()
        except SystemExit:
            pass
        except Exception:
            pass
        assert os.environ.get("RUMI_SECURITY_MODE") == "permissive"
