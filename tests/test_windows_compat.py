"""
test_windows_compat.py - Windows 互換性テスト

compat.py の機能テスト + 各モジュールのインポートテスト。
macOS/Linux でも実行可能（プラットフォーム検出の正常動作を確認）。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# テスト対象のモジュールをインポートできるようにパスを追加
_this_dir = Path(__file__).resolve().parent
_repo_dir = _this_dir.parent / "rumi_ai_1_10"
if str(_repo_dir) not in sys.path:
    sys.path.insert(0, str(_repo_dir))


class TestIsWindowsDetection(unittest.TestCase):
    """IS_WINDOWS フラグのテスト"""

    def tearDown(self):
        import importlib
        import core_runtime.compat as compat_mod

        importlib.reload(compat_mod)

    def test_is_windows_matches_platform(self):
        from core_runtime.compat import IS_WINDOWS
        expected = sys.platform == "win32"
        self.assertEqual(IS_WINDOWS, expected)

    @patch("sys.platform", "win32")
    def test_is_windows_true_on_win32(self):
        import importlib
        import core_runtime.compat as compat_mod
        importlib.reload(compat_mod)
        self.assertTrue(compat_mod.IS_WINDOWS)
        # 元に戻す
        importlib.reload(compat_mod)

    @patch("sys.platform", "darwin")
    def test_is_windows_false_on_darwin(self):
        import importlib
        import core_runtime.compat as compat_mod
        importlib.reload(compat_mod)
        self.assertFalse(compat_mod.IS_WINDOWS)
        importlib.reload(compat_mod)


class TestSafeChmod(unittest.TestCase):
    """safe_chmod のテスト"""

    def test_safe_chmod_no_error_on_current_platform(self):
        from core_runtime.compat import safe_chmod
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp = f.name
        try:
            safe_chmod(tmp, 0o600)
        finally:
            os.unlink(tmp)

    @patch("core_runtime.compat.IS_WINDOWS", True)
    def test_safe_chmod_skips_on_windows(self):
        from core_runtime.compat import safe_chmod
        # Windows モックでは os.chmod が呼ばれないので
        # 存在しないパスでもエラーにならない
        safe_chmod("/nonexistent/path", 0o600)


class TestSafeChown(unittest.TestCase):
    """safe_chown のテスト"""

    @patch("core_runtime.compat.IS_WINDOWS", True)
    def test_safe_chown_skips_on_windows(self):
        from core_runtime.compat import safe_chown
        safe_chown("/nonexistent/path", 0, 0)


class TestGetDockerSocketPath(unittest.TestCase):
    """get_docker_socket_path のテスト"""

    @patch("core_runtime.compat.IS_WINDOWS", True)
    def test_windows_docker_socket(self):
        from core_runtime.compat import get_docker_socket_path
        self.assertEqual(get_docker_socket_path(), "//./pipe/docker_engine")

    @patch("core_runtime.compat.IS_WINDOWS", False)
    def test_unix_docker_socket(self):
        from core_runtime.compat import get_docker_socket_path
        self.assertEqual(get_docker_socket_path(), "/var/run/docker.sock")


class TestModuleImports(unittest.TestCase):
    """各モジュールがインポート時にクラッシュしないことを確認"""

    def test_import_capability_proxy(self):
        """capability_proxy.py がインポートできること"""
        try:
            import core_runtime.capability_proxy
        except ImportError:
            # 依存モジュールがない場合は OK（クラス定義でクラッシュしないことが重要）
            pass
        except AttributeError as e:
            self.fail(f"capability_proxy import crashed with AttributeError: {e}")

    def test_import_egress_proxy(self):
        """egress_proxy.py がインポートできること"""
        try:
            import core_runtime.egress_proxy
        except ImportError:
            pass
        except AttributeError as e:
            self.fail(f"egress_proxy import crashed with AttributeError: {e}")

    def test_import_compat(self):
        """compat.py がインポートできること"""
        import core_runtime.compat
        self.assertTrue(hasattr(core_runtime.compat, "IS_WINDOWS"))
        self.assertTrue(hasattr(core_runtime.compat, "safe_chmod"))
        self.assertTrue(hasattr(core_runtime.compat, "safe_chown"))
        self.assertTrue(hasattr(core_runtime.compat, "get_docker_socket_path"))


if __name__ == "__main__":
    unittest.main()
