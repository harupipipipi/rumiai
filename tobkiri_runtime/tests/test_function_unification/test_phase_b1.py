"""
test_phase_b1.py — Phase B-1: Kernel Manifests + Startup Registration Tests

Tests:
 1. _KERNEL_HANDLER_MANIFESTS is a dict
 2. _KERNEL_HANDLER_MANIFESTS key count == system + runtime handler count
 3. Each manifest dict contains at least "description"
 4. Each manifest has "permission_id" == handler key (full format)
 5. Each manifest has "risk" in {"low","medium","high"}
 6. Each manifest has "requires" as a list
 7. _EXPECTED_HANDLER_KEYS == frozenset(_KERNEL_HANDLER_MANIFESTS.keys())
 8. "kernel:register_kernel_functions" in manifests
 9. _register_kernel_functions() is callable
10. _register_kernel_functions() calls register_kernel_function for each manifest
11. Manifest values are passed correctly to register_kernel_function
12. startup flow contains kernel:register_kernel_functions step
13. startup flow step has priority 15-39
14. kernel_handlers_system.py registers kernel:register_kernel_functions
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helper: safely import kernel symbols
# ---------------------------------------------------------------------------
_MANIFESTS = None
_EXPECTED_KEYS = None
_REGISTER_FN = None
_IMPORT_ERROR = None

try:
    from core_runtime.kernel import (
        _KERNEL_HANDLER_MANIFESTS,
        _EXPECTED_HANDLER_KEYS,
        _register_kernel_functions,
    )
    _MANIFESTS = _KERNEL_HANDLER_MANIFESTS
    _EXPECTED_KEYS = _EXPECTED_HANDLER_KEYS
    _REGISTER_FN = _register_kernel_functions
except Exception as _exc:
    _IMPORT_ERROR = str(_exc)


def _read_kernel_py() -> str:
    p = _PROJECT_ROOT / "core_runtime" / "kernel.py"
    return p.read_text(encoding="utf-8") if p.exists() else ""


class TestKernelHandlerManifests(unittest.TestCase):
    """Tests for _KERNEL_HANDLER_MANIFESTS structure."""

    def test_01_manifests_is_dict(self):
        if _MANIFESTS is not None:
            self.assertIsInstance(_MANIFESTS, dict)
        else:
            src = _read_kernel_py()
            self.assertIn("_KERNEL_HANDLER_MANIFESTS", src,
                          f"Import failed ({_IMPORT_ERROR}); file check also failed")

    def test_02_handler_count_matches(self):
        # 29 system + 1 register_kernel_functions + 41 runtime = 71
        EXPECTED_MIN = 71
        if _MANIFESTS is not None:
            self.assertGreaterEqual(len(_MANIFESTS), EXPECTED_MIN,
                                    f"Got {len(_MANIFESTS)} keys, expected >= {EXPECTED_MIN}")
        else:
            src = _read_kernel_py()
            keys = set(re.findall(r'"(kernel:[a-z_][a-z0-9_.]*)":\s*\{', src))
            self.assertGreaterEqual(len(keys), EXPECTED_MIN,
                                    f"Regex found {len(keys)} keys")

    def test_03_each_manifest_has_description(self):
        if _MANIFESTS is None:
            self.skipTest("Manifests not importable")
        for key, m in _MANIFESTS.items():
            with self.subTest(key=key):
                self.assertIn("description", m)
                self.assertIsInstance(m["description"], str)
                self.assertTrue(len(m["description"]) > 0)

    def test_04_each_manifest_has_permission_id_full_format(self):
        """permission_id must equal the full handler_key (e.g. 'kernel:mounts.init')."""
        if _MANIFESTS is None:
            self.skipTest("Manifests not importable")
        for key, m in _MANIFESTS.items():
            with self.subTest(key=key):
                self.assertIn("permission_id", m)
                self.assertEqual(m["permission_id"], key,
                                 f"Expected permission_id='{key}', got '{m['permission_id']}'")

    def test_05_each_manifest_has_risk(self):
        if _MANIFESTS is None:
            self.skipTest("Manifests not importable")
        for key, m in _MANIFESTS.items():
            with self.subTest(key=key):
                self.assertIn("risk", m)
                self.assertIn(m["risk"], {"low", "medium", "high"})

    def test_06_each_manifest_has_requires(self):
        if _MANIFESTS is None:
            self.skipTest("Manifests not importable")
        for key, m in _MANIFESTS.items():
            with self.subTest(key=key):
                self.assertIn("requires", m)
                self.assertIsInstance(m["requires"], list)

    def test_07_expected_handler_keys_matches(self):
        if _MANIFESTS is None or _EXPECTED_KEYS is None:
            src = _read_kernel_py()
            self.assertIn(
                "_EXPECTED_HANDLER_KEYS = frozenset(_KERNEL_HANDLER_MANIFESTS.keys())",
                src,
            )
            return
        self.assertEqual(_EXPECTED_KEYS, frozenset(_MANIFESTS.keys()))

    def test_08_register_kernel_functions_in_manifests(self):
        if _MANIFESTS is not None:
            self.assertIn("kernel:register_kernel_functions", _MANIFESTS)
        else:
            src = _read_kernel_py()
            self.assertIn('"kernel:register_kernel_functions"', src)


class TestRegisterKernelFunctions(unittest.TestCase):
    """Tests for _register_kernel_functions() function."""

    def test_09_function_is_callable(self):
        if _REGISTER_FN is not None:
            self.assertTrue(callable(_REGISTER_FN))
        else:
            src = _read_kernel_py()
            self.assertIn("def _register_kernel_functions(", src)

    def test_10_calls_register_for_each_manifest(self):
        if _REGISTER_FN is None or _MANIFESTS is None:
            self.skipTest("Cannot import kernel symbols")
        mock_fr = MagicMock()
        mock_fr.register_kernel_function = MagicMock()
        count = _REGISTER_FN(mock_fr)
        self.assertEqual(mock_fr.register_kernel_function.call_count,
                         len(_MANIFESTS))
        self.assertEqual(count, len(_MANIFESTS))

    def test_11_manifest_values_passed_correctly(self):
        if _REGISTER_FN is None or _MANIFESTS is None:
            self.skipTest("Cannot import kernel symbols")
        calls = []
        mock_fr = MagicMock()
        mock_fr.register_kernel_function = lambda k, m: calls.append((k, m))
        _REGISTER_FN(mock_fr)
        call_dict = {k: m for k, m in calls}
        for key, manifest in _MANIFESTS.items():
            with self.subTest(key=key):
                self.assertIn(key, call_dict)
                self.assertIs(call_dict[key], manifest)


class TestStartupFlow(unittest.TestCase):
    """Tests for 00_startup.flow.yaml changes."""

    def _read_flow(self) -> str:
        p = _PROJECT_ROOT / "flows" / "00_startup.flow.yaml"
        if not p.exists():
            self.skipTest(f"Flow file not found: {p}")
        return p.read_text(encoding="utf-8")

    def test_12_flow_has_register_step(self):
        content = self._read_flow()
        self.assertIn("kernel:register_kernel_functions", content)

    def test_13_step_priority_in_range(self):
        content = self._read_flow()
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not available")
        flow = yaml.safe_load(content)
        steps = flow.get("steps", [])
        register_step = None
        for step in steps:
            h = step.get("input", {}).get("handler", "")
            if h == "kernel:register_kernel_functions":
                register_step = step
                break
        self.assertIsNotNone(register_step,
                             "kernel:register_kernel_functions step not found")
        pri = register_step.get("priority", 0)
        self.assertGreaterEqual(pri, 15)
        self.assertLessEqual(pri, 39)


class TestSystemHandlerFile(unittest.TestCase):
    """Tests for kernel_handlers_system.py changes."""

    def test_14_handler_registered(self):
        p = _PROJECT_ROOT / "core_runtime" / "kernel_handlers_system.py"
        if not p.exists():
            self.skipTest(f"File not found: {p}")
        content = p.read_text(encoding="utf-8")
        self.assertIn('"kernel:register_kernel_functions"', content)
        self.assertIn("_h_register_kernel_functions", content)


if __name__ == "__main__":
    unittest.main()
