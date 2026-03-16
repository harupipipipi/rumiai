"""
test_app1_permissive_guard.py - APP-1: permissive ガード強化 + _w19d_* リネーム検証

テスト対象:
  - _check_permissive_production_guard のホワイトリスト方式ガード
  - _w19d_* プレフィックスの除去確認

依存モジュール (core_runtime 等) は全てモック化して実行する。
"""
import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# core_runtime 等の外部依存を一括モック
# ---------------------------------------------------------------------------
_MOCK_MODULES = [
    "core_runtime",
    "core_runtime.logging_utils",
    "core_runtime.lang",
    "core_runtime.kernel_facade",
    "core_runtime.health",
    "core_runtime.pack_validator",
    "core_runtime.paths",
    "backend_core",
    "backend_core.ecosystem",
    "backend_core.ecosystem.compat",
    "backend_core.ecosystem.active_ecosystem",
]


@pytest.fixture(autouse=True)
def _mock_deps():
    """各テスト前にモックモジュールを仕込み、テスト後に除去する。"""
    saved = {n: sys.modules.get(n) for n in _MOCK_MODULES}
    saved["app"] = sys.modules.get("app")

    for name in _MOCK_MODULES:
        mod = types.ModuleType(name)
        if name == "core_runtime.logging_utils":
            mod.configure_logging = MagicMock()
        elif name == "core_runtime":
            ki = MagicMock()
            ki.interface_registry.get.return_value = None
            mod.Kernel = MagicMock(return_value=ki)
        elif name == "core_runtime.lang":
            mod.L = lambda key, **kw: key
            mod.load_system_lang = MagicMock()
        elif name == "core_runtime.kernel_facade":
            mod.KernelFacade = MagicMock()
        elif name == "core_runtime.pack_validator":
            mod.validate_host_execution = MagicMock()
            mod.validate_host_execution_single = MagicMock(
                return_value=(True, ""),
            )
        elif name == "core_runtime.paths":
            mod.discover_pack_locations = MagicMock(return_value=[])
        elif name == "backend_core.ecosystem.compat":
            mod.mark_ecosystem_initialized = MagicMock()
        elif name == "backend_core.ecosystem.active_ecosystem":
            mod.get_active_ecosystem_manager = MagicMock()
        sys.modules[name] = mod

    sys.modules.pop("app", None)

    yield

    sys.modules.pop("app", None)
    for name in _MOCK_MODULES:
        if saved[name] is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved[name]


# main() が副作用で設定する環境変数のクリーンアップリスト
_SIDE_EFFECT_VARS = ["RUMI_SECURITY_MODE"]


def _run_main(*argv, env=None):
    """app.main() をカスタム argv / 環境変数で呼び出すヘルパー。"""
    old_argv = sys.argv[:]
    old_env = {}
    try:
        sys.argv = ["app.py"] + list(argv)
        if env:
            for k, v in env.items():
                old_env[k] = os.environ.get(k)
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        # main() の副作用で設定される変数も保存
        for k in _SIDE_EFFECT_VARS:
            if k not in old_env:
                old_env[k] = os.environ.get(k)
        import app
        importlib.reload(app)
        app.main()
    finally:
        sys.argv = old_argv
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ===================================================================
# テストケース: ホワイトリスト方式 permissive ガード
# ===================================================================

class TestPermissiveGuardStrengthened:
    """ホワイトリスト方式の permissive ガードテスト。"""

    def test_permissive_blocked_by_default(self):
        """RUMI_ENVIRONMENT 未設定 + RUMI_ALLOW_PERMISSIVE 未設定 → 拒否"""
        with pytest.raises(SystemExit) as exc:
            _run_main("--permissive", env={
                "RUMI_ENVIRONMENT": None,
                "RUMI_ALLOW_PERMISSIVE": None,
            })
        assert exc.value.code == 1

    def test_permissive_blocked_in_production(self):
        """RUMI_ENVIRONMENT=production → 拒否"""
        with pytest.raises(SystemExit) as exc:
            _run_main("--permissive", env={
                "RUMI_ENVIRONMENT": "production",
                "RUMI_ALLOW_PERMISSIVE": None,
            })
        assert exc.value.code == 1

    def test_permissive_allowed_with_explicit_flag(self):
        """RUMI_ALLOW_PERMISSIVE=true → 許可"""
        _run_main("--permissive", "--headless", env={
            "RUMI_ALLOW_PERMISSIVE": "true",
        })

    def test_permissive_allowed_in_dev_environment(self):
        """RUMI_ENVIRONMENT=development → 許可"""
        _run_main("--permissive", "--headless", env={
            "RUMI_ENVIRONMENT": "development",
            "RUMI_ALLOW_PERMISSIVE": None,
        })

    def test_permissive_allowed_in_dev_short(self):
        """RUMI_ENVIRONMENT=dev → 許可"""
        _run_main("--permissive", "--headless", env={
            "RUMI_ENVIRONMENT": "dev",
            "RUMI_ALLOW_PERMISSIVE": None,
        })


# ===================================================================
# テストケース: _w19d_* 変数リネーム検証
# ===================================================================

class TestW19dVariablesRenamed:
    """_w19d_* プレフィックスが除去されていることの検証。"""

    def test_w19d_variables_renamed(self):
        """app.py 内に _w19d_ が存在しないこと。"""
        app_path = Path(__file__).resolve().parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "_w19d_" not in content, (
            "app.py still contains _w19d_ prefix"
        )
