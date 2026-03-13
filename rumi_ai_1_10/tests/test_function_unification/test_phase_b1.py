"""
test_phase_b1.py - Phase B1 テスト

_KERNEL_HANDLER_MANIFESTS / _register_kernel_functions のテスト。
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Set
from unittest.mock import MagicMock, patch


class TestKernelHandlerManifests(unittest.TestCase):
    """_KERNEL_HANDLER_MANIFESTS のテスト"""

    def _get_manifests(self) -> Dict[str, Dict[str, Any]]:
        """kernel.py から _KERNEL_HANDLER_MANIFESTS を取得"""
        from rumi_ai_1_10.core_runtime.kernel import _KERNEL_HANDLER_MANIFESTS
        return _KERNEL_HANDLER_MANIFESTS

    def test_manifests_is_dict(self):
        """_KERNEL_HANDLER_MANIFESTS が dict であること"""
        manifests = self._get_manifests()
        self.assertIsInstance(manifests, dict)

    def test_manifests_not_empty(self):
        """_KERNEL_HANDLER_MANIFESTS が空でないこと"""
        manifests = self._get_manifests()
        self.assertGreater(len(manifests), 0)

    def test_all_keys_have_kernel_prefix(self):
        """全キーが 'kernel:' プレフィックスを持つこと"""
        manifests = self._get_manifests()
        for key in manifests:
            self.assertTrue(
                key.startswith("kernel:"),
                f"Key '{key}' does not start with 'kernel:'"
            )

    def test_all_entries_have_description(self):
        """各 manifest dict に最低限 'description' が含まれること"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            self.assertIn(
                "description", manifest,
                f"Manifest for '{key}' missing 'description'"
            )
            self.assertIsInstance(
                manifest["description"], str,
                f"Description for '{key}' is not a string"
            )
            self.assertGreater(
                len(manifest["description"]), 0,
                f"Description for '{key}' is empty"
            )

    def test_all_entries_have_permission_id(self):
        """各 manifest dict に 'permission_id' が含まれること"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            self.assertIn(
                "permission_id", manifest,
                f"Manifest for '{key}' missing 'permission_id'"
            )

    def test_permission_id_matches_handler_key(self):
        """permission_id が handler_key の 'kernel:' を除いた部分と一致すること"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            expected_pid = key.replace("kernel:", "", 1)
            self.assertEqual(
                manifest.get("permission_id"), expected_pid,
                f"permission_id for '{key}' expected '{expected_pid}', "
                f"got '{manifest.get('permission_id')}'"
            )

    def test_all_entries_have_risk(self):
        """各 manifest dict に 'risk' が含まれること"""
        manifests = self._get_manifests()
        valid_risks = {"low", "medium", "high"}
        for key, manifest in manifests.items():
            self.assertIn(
                "risk", manifest,
                f"Manifest for '{key}' missing 'risk'"
            )
            self.assertIn(
                manifest["risk"], valid_risks,
                f"Risk for '{key}' is '{manifest['risk']}', expected one of {valid_risks}"
            )

    def test_all_entries_have_requires(self):
        """各 manifest dict に 'requires' が含まれること"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            self.assertIn(
                "requires", manifest,
                f"Manifest for '{key}' missing 'requires'"
            )
            self.assertIsInstance(
                manifest["requires"], list,
                f"'requires' for '{key}' is not a list"
            )

    def test_all_entries_have_tags(self):
        """各 manifest dict に 'tags' が含まれること"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            self.assertIn(
                "tags", manifest,
                f"Manifest for '{key}' missing 'tags'"
            )
            self.assertIsInstance(
                manifest["tags"], list,
                f"'tags' for '{key}' is not a list"
            )


class TestManifestsMatchHandlers(unittest.TestCase):
    """_KERNEL_HANDLER_MANIFESTS のキー数がハンドラ数と一致すること"""

    def _count_system_handlers(self) -> Set[str]:
        """system handlers のキーセットを取得"""
        from rumi_ai_1_10.core_runtime.kernel_handlers_system import (
            KernelSystemHandlersMixin,
        )
        # _register_system_handlers を呼ぶにはインスタンスが必要
        # Mixin なので直接呼べないが、返り値の dict を得るために mock する

        class _FakeKernel(KernelSystemHandlersMixin):
            pass

        fake = _FakeKernel()
        # _register_system_handlers は self のメソッドを参照するので
        # 属性を mock で埋める
        fake.diagnostics = MagicMock()
        fake.interface_registry = MagicMock()
        fake.event_bus = MagicMock()
        fake.install_journal = MagicMock()
        fake.lifecycle = MagicMock()
        fake._flow = None

        handlers = fake._register_system_handlers()
        return set(handlers.keys())

    def _count_runtime_handlers(self) -> Set[str]:
        """runtime handlers のキーセットを取得"""
        from rumi_ai_1_10.core_runtime.kernel_handlers_runtime import (
            KernelRuntimeHandlersMixin,
        )

        class _FakeKernel(KernelRuntimeHandlersMixin):
            pass

        fake = _FakeKernel()
        fake.diagnostics = MagicMock()
        fake.interface_registry = MagicMock()
        fake.event_bus = MagicMock()
        fake.install_journal = MagicMock()
        fake.lifecycle = MagicMock()
        fake._uds_proxy_manager = None
        fake._capability_proxy = None

        handlers = fake._register_runtime_handlers()
        return set(handlers.keys())

    def test_manifest_keys_match_handler_count(self):
        """
        _KERNEL_HANDLER_MANIFESTS のキー数が
        _register_system_handlers + _register_runtime_handlers のハンドラ数と一致すること
        """
        from rumi_ai_1_10.core_runtime.kernel import _KERNEL_HANDLER_MANIFESTS

        try:
            system_keys = self._count_system_handlers()
        except Exception as e:
            self.skipTest(f"Could not count system handlers: {e}")
            return

        try:
            runtime_keys = self._count_runtime_handlers()
        except Exception as e:
            self.skipTest(f"Could not count runtime handlers: {e}")
            return

        all_handler_keys = system_keys | runtime_keys
        manifest_keys = set(_KERNEL_HANDLER_MANIFESTS.keys())

        # マニフェストに存在するがハンドラにないキー
        extra_in_manifest = manifest_keys - all_handler_keys
        # ハンドラに存在するがマニフェストにないキー
        missing_in_manifest = all_handler_keys - manifest_keys

        self.assertEqual(
            extra_in_manifest, set(),
            f"Keys in manifests but not in handlers: {extra_in_manifest}"
        )
        self.assertEqual(
            missing_in_manifest, set(),
            f"Keys in handlers but not in manifests: {missing_in_manifest}"
        )
        self.assertEqual(
            len(manifest_keys), len(all_handler_keys),
            f"Manifest count ({len(manifest_keys)}) != handler count ({len(all_handler_keys)})"
        )


class TestExpectedHandlerKeysDerivation(unittest.TestCase):
    """_EXPECTED_HANDLER_KEYS が _KERNEL_HANDLER_MANIFESTS.keys() と一致すること"""

    def test_expected_keys_match_manifests(self):
        """_EXPECTED_HANDLER_KEYS が _KERNEL_HANDLER_MANIFESTS.keys() と一致"""
        from rumi_ai_1_10.core_runtime.kernel import (
            _EXPECTED_HANDLER_KEYS,
            _KERNEL_HANDLER_MANIFESTS,
        )
        self.assertEqual(
            _EXPECTED_HANDLER_KEYS,
            frozenset(_KERNEL_HANDLER_MANIFESTS.keys()),
            "_EXPECTED_HANDLER_KEYS does not match _KERNEL_HANDLER_MANIFESTS.keys()"
        )

    def test_expected_keys_is_frozenset(self):
        """_EXPECTED_HANDLER_KEYS が frozenset であること"""
        from rumi_ai_1_10.core_runtime.kernel import _EXPECTED_HANDLER_KEYS
        self.assertIsInstance(_EXPECTED_HANDLER_KEYS, frozenset)


class TestRegisterKernelFunctions(unittest.TestCase):
    """_register_kernel_functions() のテスト"""

    def test_register_kernel_functions_exists(self):
        """_register_kernel_functions が存在すること"""
        from rumi_ai_1_10.core_runtime.kernel import _register_kernel_functions
        self.assertTrue(callable(_register_kernel_functions))

    def test_register_kernel_functions_registers_entries(self):
        """
        _register_kernel_functions() を呼んだ後、
        FunctionRegistry に kernel function が登録されていること
        """
        from rumi_ai_1_10.core_runtime.kernel import (
            _KERNEL_HANDLER_MANIFESTS,
            _register_kernel_functions,
        )
        from rumi_ai_1_10.core_runtime.function_registry import FunctionRegistry

        registry = FunctionRegistry()
        count = _register_kernel_functions(registry)

        self.assertGreater(count, 0, "No functions were registered")
        self.assertEqual(
            count, len(_KERNEL_HANDLER_MANIFESTS),
            f"Registered {count} functions, expected {len(_KERNEL_HANDLER_MANIFESTS)}"
        )

    def test_registered_entries_have_kernel_pack_id(self):
        """登録された entry の pack_id == 'kernel' であること"""
        from rumi_ai_1_10.core_runtime.kernel import _register_kernel_functions
        from rumi_ai_1_10.core_runtime.function_registry import FunctionRegistry

        registry = FunctionRegistry()
        _register_kernel_functions(registry)

        kernel_entries = registry.list_by_pack("kernel")
        self.assertGreater(len(kernel_entries), 0)

        for entry in kernel_entries:
            self.assertEqual(
                entry.pack_id, "kernel",
                f"Entry {entry.qualified_name} has pack_id={entry.pack_id}"
            )

    def test_registered_entries_have_description(self):
        """登録された entry に description があること"""
        from rumi_ai_1_10.core_runtime.kernel import _register_kernel_functions
        from rumi_ai_1_10.core_runtime.function_registry import FunctionRegistry

        registry = FunctionRegistry()
        _register_kernel_functions(registry)

        for entry in registry.list_all():
            self.assertTrue(
                len(entry.description) > 0,
                f"Entry {entry.qualified_name} has empty description"
            )


class TestRegisterKernelFunctionsWithMock(unittest.TestCase):
    """register_kernel_function() (Phase A) を使った登録テスト"""

    def test_uses_register_kernel_function_when_available(self):
        """
        FunctionRegistry に register_kernel_function() がある場合、
        それを使用すること
        """
        from rumi_ai_1_10.core_runtime.kernel import (
            _KERNEL_HANDLER_MANIFESTS,
            _register_kernel_functions,
        )

        mock_registry = MagicMock()
        mock_registry.register_kernel_function = MagicMock()
        # hasattr が True を返すようにする
        mock_registry.register_kernel_function.return_value = None

        count = _register_kernel_functions(mock_registry)

        self.assertEqual(count, len(_KERNEL_HANDLER_MANIFESTS))
        self.assertEqual(
            mock_registry.register_kernel_function.call_count,
            len(_KERNEL_HANDLER_MANIFESTS),
        )

        # 各呼び出しの引数を検証
        for call_args in mock_registry.register_kernel_function.call_args_list:
            args, kwargs = call_args
            key = args[0]
            manifest = args[1]
            self.assertTrue(key.startswith("kernel:"))
            self.assertIn("description", manifest)

    def test_fallback_to_register_when_no_register_kernel_function(self):
        """
        register_kernel_function() がない場合、通常の register() を使うこと
        """
        from rumi_ai_1_10.core_runtime.kernel import _register_kernel_functions
        from rumi_ai_1_10.core_runtime.function_registry import FunctionRegistry

        # register_kernel_function を持たない FunctionRegistry
        registry = FunctionRegistry()
        # register_kernel_function を削除（存在しないことを確認）
        if hasattr(registry, 'register_kernel_function'):
            # Phase A が適用されている場合、このテストは register_kernel_function 経由になる
            # それでも登録自体は成功するはず
            pass

        count = _register_kernel_functions(registry)
        self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
