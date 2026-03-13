"""
test_phase_b1.py - Phase B-1 テスト

テスト対象:
- _KERNEL_HANDLER_MANIFESTS が dict であること
- _KERNEL_HANDLER_MANIFESTS のキー数がハンドラ数と一致すること
- 各 manifest dict に必須フィールドが含まれること
- _register_kernel_functions() が正しく動作すること
- _EXPECTED_HANDLER_KEYS が _KERNEL_HANDLER_MANIFESTS.keys() と一致すること
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# テスト対象のインポートパスを設定
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


class TestKernelHandlerManifests:
    """_KERNEL_HANDLER_MANIFESTS の構造テスト"""

    def _get_manifests(self):
        from core_runtime.kernel import _KERNEL_HANDLER_MANIFESTS
        return _KERNEL_HANDLER_MANIFESTS

    def test_manifests_is_dict(self):
        """_KERNEL_HANDLER_MANIFESTS が dict であること"""
        manifests = self._get_manifests()
        assert isinstance(manifests, dict), \
            f"Expected dict, got {type(manifests).__name__}"

    def test_manifests_not_empty(self):
        """_KERNEL_HANDLER_MANIFESTS が空でないこと"""
        manifests = self._get_manifests()
        assert len(manifests) > 0, "Manifests should not be empty"

    def test_manifests_key_count_matches_handlers(self):
        """
        _KERNEL_HANDLER_MANIFESTS のキー数が
        _register_system_handlers + _register_runtime_handlers のハンドラ数と一致すること
        """
        manifests = self._get_manifests()

        from core_runtime.kernel_handlers_system import KernelSystemHandlersMixin
        from core_runtime.kernel_handlers_runtime import KernelRuntimeHandlersMixin

        mock_self = MagicMock()
        system_handlers = KernelSystemHandlersMixin._register_system_handlers(mock_self)
        runtime_handlers = KernelRuntimeHandlersMixin._register_runtime_handlers(mock_self)

        expected_count = len(system_handlers) + len(runtime_handlers)
        actual_count = len(manifests)

        handler_keys = set(system_handlers.keys()) | set(runtime_handlers.keys())
        manifest_keys = set(manifests.keys())

        missing_in_manifests = handler_keys - manifest_keys
        missing_in_handlers = manifest_keys - handler_keys

        assert actual_count == expected_count, (
            f"Manifest count ({actual_count}) != handler count ({expected_count}). "
            f"Missing in manifests: {sorted(missing_in_manifests)}. "
            f"Missing in handlers: {sorted(missing_in_handlers)}."
        )

    def test_each_manifest_has_description(self):
        """各 manifest dict に 'description' が含まれること"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            assert "description" in manifest, \
                f"Manifest '{key}' is missing 'description'"
            assert isinstance(manifest["description"], str), \
                f"Manifest '{key}' description is not a string"
            assert len(manifest["description"]) > 0, \
                f"Manifest '{key}' has empty description"

    def test_each_manifest_has_permission_id(self):
        """各 manifest dict に 'permission_id' が含まれること (Phase B-1)"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            assert "permission_id" in manifest, \
                f"Manifest '{key}' is missing 'permission_id'"
            assert manifest["permission_id"] == key, \
                f"Manifest '{key}' permission_id mismatch: {manifest['permission_id']} != {key}"

    def test_each_manifest_has_risk(self):
        """各 manifest dict に 'risk' が含まれること (Phase B-1)"""
        manifests = self._get_manifests()
        valid_risk_levels = {"low", "medium", "high"}
        for key, manifest in manifests.items():
            assert "risk" in manifest, \
                f"Manifest '{key}' is missing 'risk'"
            assert manifest["risk"] in valid_risk_levels, \
                f"Manifest '{key}' has invalid risk level: {manifest['risk']}"

    def test_each_manifest_has_requires(self):
        """各 manifest dict に 'requires' が含まれること (Phase B-1)"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            assert "requires" in manifest, \
                f"Manifest '{key}' is missing 'requires'"
            assert isinstance(manifest["requires"], list), \
                f"Manifest '{key}' requires is not a list"

    def test_each_manifest_has_tags(self):
        """各 manifest dict に 'tags' が含まれること"""
        manifests = self._get_manifests()
        for key, manifest in manifests.items():
            assert "tags" in manifest, \
                f"Manifest '{key}' is missing 'tags'"
            assert isinstance(manifest["tags"], list), \
                f"Manifest '{key}' tags is not a list"

    def test_all_keys_have_kernel_prefix(self):
        """全キーが 'kernel:' プレフィックスを持つこと"""
        manifests = self._get_manifests()
        for key in manifests:
            assert key.startswith("kernel:"), \
                f"Handler key '{key}' does not start with 'kernel:'"


class TestExpectedHandlerKeys:
    """_EXPECTED_HANDLER_KEYS の後方互換テスト"""

    def test_expected_keys_equals_manifest_keys(self):
        """_EXPECTED_HANDLER_KEYS が _KERNEL_HANDLER_MANIFESTS.keys() と一致すること"""
        from core_runtime.kernel import _EXPECTED_HANDLER_KEYS, _KERNEL_HANDLER_MANIFESTS

        assert isinstance(_EXPECTED_HANDLER_KEYS, frozenset), \
            f"Expected frozenset, got {type(_EXPECTED_HANDLER_KEYS).__name__}"

        manifest_keys = frozenset(_KERNEL_HANDLER_MANIFESTS.keys())
        assert _EXPECTED_HANDLER_KEYS == manifest_keys, (
            f"_EXPECTED_HANDLER_KEYS does not match _KERNEL_HANDLER_MANIFESTS.keys(). "
            f"Difference: {_EXPECTED_HANDLER_KEYS.symmetric_difference(manifest_keys)}"
        )

    def test_expected_keys_is_frozenset(self):
        """_EXPECTED_HANDLER_KEYS が frozenset であること"""
        from core_runtime.kernel import _EXPECTED_HANDLER_KEYS
        assert isinstance(_EXPECTED_HANDLER_KEYS, frozenset)


class TestRegisterKernelFunctions:
    """_register_kernel_functions() のテスト"""

    def test_register_with_mock_registry(self):
        """
        _register_kernel_functions() を呼んだ後、
        FunctionRegistry に kernel function が登録されていること
        """
        from core_runtime.kernel import _register_kernel_functions, _KERNEL_HANDLER_MANIFESTS

        mock_registry = MagicMock()
        mock_registry.register_kernel_function = MagicMock()

        count = _register_kernel_functions(mock_registry)

        assert count == len(_KERNEL_HANDLER_MANIFESTS), \
            f"Expected {len(_KERNEL_HANDLER_MANIFESTS)} registrations, got {count}"
        assert mock_registry.register_kernel_function.call_count == len(_KERNEL_HANDLER_MANIFESTS)

    def test_register_with_none_registry(self):
        """function_registry が None の場合、0 を返すこと"""
        from core_runtime.kernel import _register_kernel_functions
        count = _register_kernel_functions(None)
        assert count == 0

    def test_register_passes_correct_keys(self):
        """register_kernel_function() に正しいキーとmanifestが渡されること"""
        from core_runtime.kernel import _register_kernel_functions, _KERNEL_HANDLER_MANIFESTS

        mock_registry = MagicMock()
        calls = {}

        def capture_call(key, manifest):
            calls[key] = manifest

        mock_registry.register_kernel_function = capture_call

        _register_kernel_functions(mock_registry)

        for key in _KERNEL_HANDLER_MANIFESTS:
            assert key in calls, f"Key '{key}' was not registered"
            assert calls[key] is _KERNEL_HANDLER_MANIFESTS[key], \
                f"Manifest for '{key}' does not match"

    def test_register_fallback_without_register_kernel_function(self):
        """
        register_kernel_function() が存在しない場合、
        フォールバック（汎用 register()）で登録されること
        """
        from core_runtime.kernel import _register_kernel_functions, _KERNEL_HANDLER_MANIFESTS

        mock_registry = MagicMock(spec=[])
        # getattr(..., "register_kernel_function", None) が None を返す
        mock_registry.register = MagicMock(return_value=True)

        count = _register_kernel_functions(mock_registry)

        assert count == len(_KERNEL_HANDLER_MANIFESTS), \
            f"Fallback registration count mismatch: {count}"
        assert mock_registry.register.call_count == len(_KERNEL_HANDLER_MANIFESTS)

    def test_registered_entry_properties(self):
        """
        フォールバック登録で作成された FunctionEntry が
        pack_id="kernel" であること
        """
        from core_runtime.kernel import _register_kernel_functions

        captured_entries = []
        mock_registry = MagicMock(spec=[])

        def capture_register(entry):
            captured_entries.append(entry)
            return True

        mock_registry.register = capture_register

        _register_kernel_functions(mock_registry)

        assert len(captured_entries) > 0, "No entries were registered"

        for entry in captured_entries:
            assert entry.pack_id == "kernel", \
                f"Entry {entry.qualified_name} has pack_id={entry.pack_id}, expected 'kernel'"


class TestStartupFlowIntegration:
    """startup flow との統合テスト（YAMLパース）"""

    def test_startup_flow_has_kernel_function_register_step(self):
        """00_startup.flow.yaml に kernel function 登録ステップが含まれること"""
        flow_path = Path(__file__).resolve().parent.parent.parent / "flows" / "00_startup.flow.yaml"
        if not flow_path.exists():
            pytest.skip(f"Flow file not found: {flow_path}")

        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        content = flow_path.read_text(encoding="utf-8")
        flow_def = yaml.safe_load(content)

        steps = flow_def.get("steps", [])
        step_ids = [s.get("id") for s in steps if isinstance(s, dict)]

        assert "kernel_function_register" in step_ids, \
            "Startup flow is missing 'kernel_function_register' step"

    def test_kernel_function_register_step_in_ecosystem_phase(self):
        """kernel_function_register ステップが ecosystem phase, priority 15 にあること"""
        flow_path = Path(__file__).resolve().parent.parent.parent / "flows" / "00_startup.flow.yaml"
        if not flow_path.exists():
            pytest.skip(f"Flow file not found: {flow_path}")

        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        content = flow_path.read_text(encoding="utf-8")
        flow_def = yaml.safe_load(content)

        steps = flow_def.get("steps", [])
        for step in steps:
            if isinstance(step, dict) and step.get("id") == "kernel_function_register":
                assert step.get("phase") == "ecosystem", \
                    f"Expected phase 'ecosystem', got '{step.get('phase')}'"
                assert step.get("priority") == 15, \
                    f"Expected priority 15, got {step.get('priority')}"
                return

        pytest.fail("kernel_function_register step not found")
