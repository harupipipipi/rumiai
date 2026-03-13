"""
test_fix_registration.py - FIX-A テスト

FAIL-4+2: core_pack function の FunctionRegistry 登録パスの検証
FAIL-3: calling_convention 分岐の検証
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# テスト対象のパスを追加
_test_dir = Path(__file__).resolve().parent
_project_root = _test_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


class TestRegisterBuiltinHandlers(unittest.TestCase):
    """FIX-A1: _register_builtin_handlers() のテスト"""

    def _make_executor_with_mock_registry(self):
        """テスト用に CapabilityExecutor + Mock FunctionRegistry を構築"""
        from core_runtime.capability_executor import CapabilityExecutor
        from core_runtime.function_registry import FunctionRegistry

        executor = CapabilityExecutor()
        fr = FunctionRegistry()
        executor._function_registry = fr
        return executor, fr

    def test_register_builtin_handlers_returns_positive_count(self):
        """core_pack function が少なくとも1つ登録される"""
        executor, fr = self._make_executor_with_mock_registry()
        count = executor._register_builtin_handlers()
        self.assertGreater(count, 0, "At least one core_pack function should be registered")

    def test_register_builtin_handlers_registers_expected_functions(self):
        """既知の core_pack function が登録される"""
        executor, fr = self._make_executor_with_mock_registry()
        executor._register_builtin_handlers()

        # core_docker_capability の functions
        expected_docker = [
            "core_docker_capability:run",
            "core_docker_capability:exec",
            "core_docker_capability:stop",
            "core_docker_capability:logs",
            "core_docker_capability:list",
        ]
        for qname in expected_docker:
            entry = fr.get(qname)
            self.assertIsNotNone(entry, f"{qname} should be registered")

        # core_store_capability の functions
        expected_store = [
            "core_store_capability:get",
            "core_store_capability:set",
            "core_store_capability:list",
            "core_store_capability:delete",
            "core_store_capability:batch_get",
            "core_store_capability:cas",
        ]
        for qname in expected_store:
            entry = fr.get(qname)
            self.assertIsNotNone(entry, f"{qname} should be registered")

        # core_secrets_capability
        entry = fr.get("core_secrets_capability:get")
        self.assertIsNotNone(entry, "core_secrets_capability:get should be registered")

        # core_flow_capability
        entry = fr.get("core_flow_capability:run")
        self.assertIsNotNone(entry, "core_flow_capability:run should be registered")

        # core_communication_capability
        entry = fr.get("core_communication_capability:send")
        self.assertIsNotNone(entry, "core_communication_capability:send should be registered")
        entry = fr.get("core_communication_capability:propose_patch")
        self.assertIsNotNone(entry, "core_communication_capability:propose_patch should be registered")

    def test_registered_entries_have_calling_convention_block(self):
        """登録された FunctionEntry が calling_convention='block' を持つ"""
        executor, fr = self._make_executor_with_mock_registry()
        executor._register_builtin_handlers()

        for entry in fr.list_all():
            self.assertEqual(
                entry.calling_convention, "block",
                f"{entry.qualified_name} should have calling_convention='block', "
                f"got '{entry.calling_convention}'",
            )

    def test_registered_entries_have_is_builtin_true(self):
        """登録された FunctionEntry が is_builtin=True を持つ"""
        executor, fr = self._make_executor_with_mock_registry()
        executor._register_builtin_handlers()

        for entry in fr.list_all():
            self.assertTrue(
                entry.is_builtin,
                f"{entry.qualified_name} should have is_builtin=True",
            )

    def test_registered_entries_have_vocab_aliases(self):
        """登録された FunctionEntry の一部が vocab_aliases を持つ（resolve_by_alias 経由で取得可能）"""
        executor, fr = self._make_executor_with_mock_registry()
        executor._register_builtin_handlers()

        # store.get は vocab_aliases に入っているはず
        entry = fr.resolve_by_alias("store.get")
        self.assertIsNotNone(entry, "store.get should be resolvable by alias")
        self.assertEqual(entry.pack_id, "core_store_capability")

        # docker.run は vocab_aliases が manifest にない（旧形式）のでスキップ可能
        # flow.run
        entry = fr.resolve_by_alias("flow.run")
        self.assertIsNotNone(entry, "flow.run should be resolvable by alias")
        self.assertEqual(entry.pack_id, "core_flow_capability")

    def test_idempotent_registration(self):
        """_register_builtin_handlers() は二度呼んでも重複登録しない"""
        executor, fr = self._make_executor_with_mock_registry()
        count1 = executor._register_builtin_handlers()
        count2 = executor._register_builtin_handlers()
        self.assertGreater(count1, 0)
        self.assertEqual(count2, 0, "Second call should register 0 (idempotent)")

    def test_no_function_registry_returns_zero(self):
        """FunctionRegistry が None のとき 0 を返す"""
        from core_runtime.capability_executor import CapabilityExecutor
        executor = CapabilityExecutor()
        executor._function_registry = None
        count = executor._register_builtin_handlers()
        self.assertEqual(count, 0)


class TestCallingConventionDispatch(unittest.TestCase):
    """FIX-A2: _unified_execute() の calling_convention 分岐テスト"""

    def test_kernel_convention_returns_error(self):
        """calling_convention='kernel' は capability_executor 経由ではエラー"""
        from core_runtime.capability_executor import CapabilityExecutor
        import time

        executor = CapabilityExecutor()
        resp = executor._dispatch_by_calling_convention(
            calling_convention="kernel",
            entry=MagicMock(),
            principal_id="test",
            effective_permission_id="test.perm",
            grant_config={},
            args={},
            timeout_seconds=30.0,
            request_id="",
            start_time=time.time(),
        )
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_type, "invalid_calling_convention")

    def test_block_convention_calls_dispatch_core(self):
        """calling_convention='block' は _dispatch_core_function を呼ぶ"""
        from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse
        import time

        executor = CapabilityExecutor()
        mock_entry = MagicMock()
        mock_entry.qualified_name = "core_test:func"

        expected_resp = CapabilityResponse(success=True, output={"ok": True})
        executor._dispatch_core_function = MagicMock(return_value=expected_resp)

        resp = executor._dispatch_by_calling_convention(
            calling_convention="block",
            entry=mock_entry,
            principal_id="test",
            effective_permission_id="test.perm",
            grant_config={},
            args={"key": "val"},
            timeout_seconds=30.0,
            request_id="req1",
            start_time=time.time(),
        )

        executor._dispatch_core_function.assert_called_once()
        self.assertTrue(resp.success)

    def test_subprocess_convention_calls_handler_subprocess(self):
        """calling_convention='subprocess' は _execute_handler_subprocess を呼ぶ"""
        from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse
        import time

        executor = CapabilityExecutor()
        mock_entry = MagicMock()
        mock_entry.qualified_name = "test_pack:func"
        mock_entry.entrypoint = "main.py:run"
        mock_entry.function_dir = "/tmp/test"
        mock_entry.is_builtin = False

        expected_resp = CapabilityResponse(success=True, output={"ok": True})
        executor._execute_handler_subprocess = MagicMock(return_value=expected_resp)

        resp = executor._dispatch_by_calling_convention(
            calling_convention="subprocess",
            entry=mock_entry,
            principal_id="test",
            effective_permission_id="test.perm",
            grant_config={},
            args={},
            timeout_seconds=30.0,
            request_id="",
            start_time=time.time(),
        )

        executor._execute_handler_subprocess.assert_called_once()
        self.assertTrue(resp.success)

    def test_all_valid_conventions_handled(self):
        """全7つの calling_convention 値がハンドリングされる（エラーでない応答を返す）"""
        from core_runtime.capability_executor import (
            CapabilityExecutor, CapabilityResponse, _VALID_CALLING_CONVENTIONS,
        )
        import time

        self.assertEqual(
            len(_VALID_CALLING_CONVENTIONS), 7,
            "There should be exactly 7 valid calling_conventions",
        )

        executor = CapabilityExecutor()
        mock_entry = MagicMock()
        mock_entry.qualified_name = "test:func"
        mock_entry.entrypoint = "main.py:run"
        mock_entry.function_dir = "/tmp/test"
        mock_entry.is_builtin = False

        # Mock all dispatch methods to return success
        mock_resp = CapabilityResponse(success=True, output={})
        executor._dispatch_core_function = MagicMock(return_value=mock_resp)
        executor._execute_handler_subprocess = MagicMock(return_value=mock_resp)
        executor._execute_host_function = MagicMock(return_value=mock_resp)
        executor._execute_user_function = MagicMock(return_value=mock_resp)
        executor._execute_binary_function = MagicMock(return_value=mock_resp)
        executor._execute_command_function = MagicMock(return_value=mock_resp)

        for cc in _VALID_CALLING_CONVENTIONS:
            resp = executor._dispatch_by_calling_convention(
                calling_convention=cc,
                entry=mock_entry,
                principal_id="test",
                effective_permission_id="test.perm",
                grant_config={},
                args={},
                timeout_seconds=30.0,
                request_id="",
                start_time=time.time(),
            )
            # "kernel" returns error (by design), others should succeed
            if cc == "kernel":
                self.assertFalse(resp.success, f"kernel should return error")
            else:
                self.assertTrue(resp.success, f"{cc} should be handled successfully")


class TestManifestCallingConvention(unittest.TestCase):
    """manifest.json に calling_convention が正しく設定されているか"""

    def test_all_core_pack_manifests_have_calling_convention_block(self):
        """全 core_pack manifest.json に calling_convention='block' が設定されている"""
        core_pack_dir = Path(__file__).resolve().parent.parent.parent / "core_runtime" / "core_pack"
        if not core_pack_dir.is_dir():
            self.skipTest(f"core_pack dir not found: {core_pack_dir}")

        manifests_checked = 0
        for manifest_path in sorted(core_pack_dir.rglob("functions/*/manifest.json")):
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn(
                "calling_convention", data,
                f"{manifest_path} missing calling_convention",
            )
            self.assertEqual(
                data["calling_convention"], "block",
                f"{manifest_path} has wrong calling_convention: {data.get('calling_convention')}",
            )
            manifests_checked += 1

        self.assertGreaterEqual(manifests_checked, 15, "Expected at least 15 manifest.json files")


if __name__ == "__main__":
    unittest.main()
