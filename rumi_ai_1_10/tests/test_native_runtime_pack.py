"""
test_native_runtime_pack.py - native_runtime_pack ユニットテスト

対象:
- core_runtime/core_pack/native_runtime_pack/backend/ecosystem.json
- core_runtime/core_pack/native_runtime_pack/backend/blocks/binary_call.py
- core_runtime/core_pack/native_runtime_pack/backend/blocks/command_call.py
- core_runtime/core_pack/native_runtime_pack/backend/blocks/health_check.py

全テストは mock ベースで外部依存なし。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

_pack_blocks_dir = (
    _project_root
    / "core_runtime"
    / "core_pack"
    / "native_runtime_pack"
    / "backend"
    / "blocks"
)
if str(_pack_blocks_dir) not in sys.path:
    sys.path.insert(0, str(_pack_blocks_dir))

# --- ecosystem.json パスの解決 ---
_ecosystem_path = (
    _project_root
    / "core_runtime"
    / "core_pack"
    / "native_runtime_pack"
    / "backend"
    / "ecosystem.json"
)


# ====================================================================
# ecosystem.json テスト
# ====================================================================

class TestEcosystemJson(unittest.TestCase):
    """ecosystem.json のスキーマ検証。"""

    def setUp(self):
        with open(_ecosystem_path, "r", encoding="utf-8") as f:
            self.eco = json.load(f)

    def test_pack_id(self):
        self.assertEqual(self.eco["pack_id"], "native_runtime_pack")

    def test_pack_type_is_rule(self):
        self.assertEqual(self.eco["pack_type"], "rule")

    def test_provides_runtime_exists(self):
        self.assertIn("provides_runtime", self.eco)
        self.assertIsInstance(self.eco["provides_runtime"], list)
        self.assertIn("binary", self.eco["provides_runtime"])
        self.assertIn("command", self.eco["provides_runtime"])

    def test_version(self):
        self.assertEqual(self.eco["version"], "1.0.0")

    def test_connectivity_provides(self):
        provides = self.eco.get("connectivity", {}).get("provides", [])
        self.assertIn("native.runtime", provides)
        self.assertIn("native.binary_call", provides)
        self.assertIn("native.command_call", provides)

    def test_host_execution(self):
        self.assertTrue(
            self.eco.get("connectivity", {}).get("host_execution", False)
        )

    def test_network_false(self):
        self.assertFalse(
            self.eco.get("connectivity", {}).get("network", True)
        )

    def test_metadata_is_core_pack(self):
        self.assertTrue(
            self.eco.get("metadata", {}).get("is_core_pack", False)
        )

    def test_required_fields_exist(self):
        for field in ["pack_id", "pack_identity", "version", "metadata"]:
            self.assertIn(field, self.eco, f"Missing field: {field}")


# ====================================================================
# binary_call.py テスト
# ====================================================================

class TestBinaryCallPathTraversal(unittest.TestCase):
    """binary_call.py のパストラバーサル防止テスト。"""

    def _import_binary_call(self):
        import binary_call
        return binary_call

    def test_dotdot_in_pack_id(self):
        bc = self._import_binary_call()
        result = bc.run(
            {"pack_id": "../etc", "binary": "passwd", "args": {}},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "security_violation")

    def test_slash_in_pack_id(self):
        bc = self._import_binary_call()
        result = bc.run(
            {"pack_id": "foo/bar", "binary": "test", "args": {}},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "security_violation")

    def test_dotdot_in_binary_path(self):
        bc = self._import_binary_call()
        result = bc.run(
            {"pack_id": "safe_pack", "binary": "../../etc/passwd", "args": {}},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertIn(
            result["error_type"],
            ["security_violation", "binary_not_found"],
        )

    def test_empty_pack_id(self):
        bc = self._import_binary_call()
        result = bc.run(
            {"pack_id": "", "binary": "test", "args": {}},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "security_violation")

    def test_empty_binary(self):
        bc = self._import_binary_call()
        result = bc.run(
            {"pack_id": "test_pack", "binary": "", "args": {}},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "binary_not_found")


class TestBinaryCallExecution(unittest.TestCase):
    """binary_call.py の正常実行テスト（モック subprocess）。"""

    def _import_binary_call(self):
        import binary_call
        return binary_call

    @patch("binary_call.subprocess.run")
    @patch("binary_call.os.access", return_value=True)
    @patch("binary_call.Path.is_file", return_value=True)
    @patch("binary_call.Path.resolve")
    def test_successful_execution(
        self, mock_resolve, mock_is_file, mock_access, mock_run
    ):
        bc = self._import_binary_call()

        # resolve() がパス検証を通過するよう設定
        base_resolved = Path("/resolved/ecosystem/test_pack/backend")
        binary_resolved = Path(
            "/resolved/ecosystem/test_pack/backend/my_binary"
        )

        call_count = [0]

        def resolve_side_effect():
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return base_resolved
            return binary_resolved

        mock_resolve.side_effect = resolve_side_effect

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"result": "hello"}'
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = bc.run(
            {
                "pack_id": "test_pack",
                "binary": "my_binary",
                "args": {"key": "value"},
            },
            {"principal_id": "test_principal"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["output"], {"result": "hello"})

    @patch("binary_call.subprocess.run")
    @patch("binary_call.os.access", return_value=True)
    @patch("binary_call.Path.is_file", return_value=True)
    @patch("binary_call.Path.resolve")
    def test_timeout(
        self, mock_resolve, mock_is_file, mock_access, mock_run
    ):
        bc = self._import_binary_call()

        base_resolved = Path("/resolved/ecosystem/test_pack/backend")
        binary_resolved = Path(
            "/resolved/ecosystem/test_pack/backend/my_binary"
        )

        call_count = [0]

        def resolve_side_effect():
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return base_resolved
            return binary_resolved

        mock_resolve.side_effect = resolve_side_effect
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="test", timeout=30
        )

        result = bc.run(
            {
                "pack_id": "test_pack",
                "binary": "my_binary",
                "args": {},
                "timeout": 30,
            },
            {"principal_id": "test_principal"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "timeout")

    @patch("binary_call.subprocess.run")
    @patch("binary_call.os.access", return_value=True)
    @patch("binary_call.Path.is_file", return_value=True)
    @patch("binary_call.Path.resolve")
    def test_output_size_limit(
        self, mock_resolve, mock_is_file, mock_access, mock_run
    ):
        bc = self._import_binary_call()

        base_resolved = Path("/resolved/ecosystem/test_pack/backend")
        binary_resolved = Path(
            "/resolved/ecosystem/test_pack/backend/my_binary"
        )

        call_count = [0]

        def resolve_side_effect():
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return base_resolved
            return binary_resolved

        mock_resolve.side_effect = resolve_side_effect

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "x" * (1024 * 1024 + 1)  # 1MB + 1 byte
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = bc.run(
            {"pack_id": "test_pack", "binary": "my_binary", "args": {}},
            {"principal_id": "test_principal"},
        )
        self.assertFalse(result["success"])
        self.assertIn("size limit", result["error"])

    @patch("binary_call.subprocess.run")
    @patch("binary_call.os.access", return_value=True)
    @patch("binary_call.Path.is_file", return_value=True)
    @patch("binary_call.Path.resolve")
    def test_invalid_json_output(
        self, mock_resolve, mock_is_file, mock_access, mock_run
    ):
        bc = self._import_binary_call()

        base_resolved = Path("/resolved/ecosystem/test_pack/backend")
        binary_resolved = Path(
            "/resolved/ecosystem/test_pack/backend/my_binary"
        )

        call_count = [0]

        def resolve_side_effect():
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return base_resolved
            return binary_resolved

        mock_resolve.side_effect = resolve_side_effect

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "this is not json"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = bc.run(
            {"pack_id": "test_pack", "binary": "my_binary", "args": {}},
            {"principal_id": "test_principal"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "invalid_json_output")


# ====================================================================
# command_call.py テスト
# ====================================================================

class TestCommandCallExecution(unittest.TestCase):
    """command_call.py の正常実行テスト。"""

    def _import_command_call(self):
        import command_call
        return command_call

    @patch("command_call.subprocess.run")
    @patch("command_call.shutil.which", return_value="/usr/bin/echo")
    def test_successful_execution(self, mock_which, mock_run):
        cc = self._import_command_call()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '{"status": "ok"}'
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = cc.run(
            {"command": "echo", "args": ["hello"], "timeout": 10},
            {"principal_id": "test"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["output"], {"status": "ok"})

    def test_missing_command(self):
        cc = self._import_command_call()
        result = cc.run(
            {"command": "", "args": []},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "command_not_found")

    @patch("command_call.shutil.which", return_value=None)
    def test_command_not_found(self, mock_which):
        cc = self._import_command_call()
        result = cc.run(
            {"command": "nonexistent_command_xyz", "args": []},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "command_not_found")

    @patch("command_call.subprocess.run")
    @patch("command_call.shutil.which", return_value="/usr/bin/test")
    def test_timeout(self, mock_which, mock_run):
        cc = self._import_command_call()
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="test", timeout=5
        )

        result = cc.run(
            {"command": "test", "args": [], "timeout": 5},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "timeout")

    @patch("command_call.subprocess.run")
    @patch("command_call.shutil.which", return_value="/usr/bin/test")
    def test_invalid_json_output(self, mock_which, mock_run):
        cc = self._import_command_call()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "not json at all"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = cc.run(
            {"command": "test", "args": []},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "invalid_json_output")

    def test_args_must_be_list(self):
        cc = self._import_command_call()
        result = cc.run(
            {"command": "echo", "args": "not a list"},
            {"principal_id": "test"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "execution_error")


# ====================================================================
# health_check.py テスト
# ====================================================================

class TestHealthCheck(unittest.TestCase):
    """health_check.py の実行テスト。"""

    def _import_health_check(self):
        import health_check
        return health_check

    @patch("health_check.subprocess.run")
    @patch("health_check.shutil.which", return_value="/usr/bin/docker")
    def test_all_checks_pass(self, mock_which, mock_run):
        hc = self._import_health_check()

        def run_side_effect(cmd, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if cmd == ["echo", "health_check"]:
                mock_proc.stdout = "health_check\n"
            elif cmd == ["docker", "info"]:
                mock_proc.stdout = "Docker info output"
            mock_proc.stderr = ""
            return mock_proc

        mock_run.side_effect = run_side_effect

        with patch(
            "health_check.tempfile.NamedTemporaryFile"
        ) as mock_tmp, \
             patch("health_check.os.stat") as mock_stat, \
             patch("health_check.os.chmod") as mock_chmod, \
             patch(
                 "health_check.os.access", return_value=True
             ) as mock_access, \
             patch("health_check.os.unlink"):
            mock_file = MagicMock()
            mock_file.name = "/tmp/test_health.sh"
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_tmp.return_value = mock_file
            mock_stat.return_value = MagicMock(st_mode=0o644)

            result = hc.run({}, {"principal_id": "test"})

        self.assertTrue(result["success"])
        self.assertEqual(result["output"]["status"], "healthy")
        self.assertEqual(result["output"]["summary"]["passed"], 3)

    @patch("health_check.subprocess.run")
    @patch("health_check.shutil.which", return_value=None)
    def test_docker_unavailable_still_healthy(self, mock_which, mock_run):
        hc = self._import_health_check()

        def run_side_effect(cmd, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if cmd == ["echo", "health_check"]:
                mock_proc.stdout = "health_check\n"
            mock_proc.stderr = ""
            return mock_proc

        mock_run.side_effect = run_side_effect

        with patch(
            "health_check.tempfile.NamedTemporaryFile"
        ) as mock_tmp, \
             patch("health_check.os.stat") as mock_stat, \
             patch("health_check.os.chmod") as mock_chmod, \
             patch(
                 "health_check.os.access", return_value=True
             ) as mock_access, \
             patch("health_check.os.unlink"):
            mock_file = MagicMock()
            mock_file.name = "/tmp/test_health.sh"
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_tmp.return_value = mock_file
            mock_stat.return_value = MagicMock(st_mode=0o644)

            result = hc.run({}, {"principal_id": "test"})

        self.assertTrue(result["success"])
        # Docker unavailable でも required checks が pass なら healthy
        self.assertEqual(result["output"]["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
