"""
Test: BUG-20260305-01 flow fallback error visibility and dependency check
12 test cases covering all requirements.
"""
import sys
import os
import json
import types
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO
from pathlib import Path as _Path


def _make_kernel_core_module():
    """Import kernel_core in isolation by stubbing heavy dependencies."""
    stubs = {}
    stub_names = [
        "core_runtime", "core_runtime.types", "core_runtime.diagnostics",
        "core_runtime.install_journal", "core_runtime.interface_registry",
        "core_runtime.event_bus", "core_runtime.component_lifecycle",
        "core_runtime.capability_proxy", "core_runtime.paths",
        "core_runtime.kernel_variable_resolver", "core_runtime.kernel_context_builder",
        "core_runtime.kernel_flow_converter", "core_runtime.kernel_flow_execution",
        "core_runtime.deprecation", "core_runtime.logging_utils",
        "core_runtime.di_container", "core_runtime.audit_logger",
    ]
    for name in stub_names:
        stubs[name] = types.ModuleType(name)

    stubs["core_runtime.types"].FlowId = str
    stubs["core_runtime.diagnostics"].Diagnostics = MagicMock
    stubs["core_runtime.install_journal"].InstallJournal = MagicMock
    stubs["core_runtime.interface_registry"].InterfaceRegistry = MagicMock
    stubs["core_runtime.event_bus"].EventBus = MagicMock
    stubs["core_runtime.component_lifecycle"].ComponentLifecycleExecutor = MagicMock
    stubs["core_runtime.capability_proxy"].get_capability_proxy = MagicMock()
    stubs["core_runtime.paths"].BASE_DIR = _Path("/tmp/fake_rumi")
    stubs["core_runtime.paths"].OFFICIAL_FLOWS_DIR = str(_Path("/tmp/fake_rumi/flows"))
    stubs["core_runtime.paths"].ECOSYSTEM_DIR = str(_Path("/tmp/fake_rumi/ecosystem"))
    stubs["core_runtime.paths"].GRANTS_DIR = str(_Path("/tmp/fake_rumi/grants"))

    class _FakeResolver:
        def __init__(self, **kw):
            pass
        def resolve_value(self, v, c, d=0):
            return v
        def resolve_args(self, a, c):
            return a
    stubs["core_runtime.kernel_variable_resolver"].VariableResolver = _FakeResolver
    stubs["core_runtime.kernel_variable_resolver"].MAX_RESOLVE_DEPTH = 10
    stubs["core_runtime.kernel_context_builder"].KernelContextBuilder = MagicMock
    stubs["core_runtime.kernel_flow_converter"].FlowConverter = MagicMock
    stubs["core_runtime.kernel_flow_execution"].MAX_FLOW_CHAIN_DEPTH = 10

    def _deprecated(**kw):
        def decorator(fn):
            return fn
        return decorator
    stubs["core_runtime.deprecation"].deprecated = _deprecated
    stubs["core_runtime.logging_utils"].get_structured_logger = lambda name: MagicMock()

    _fake_container = MagicMock()
    _fake_container.get = MagicMock(return_value=MagicMock())
    stubs["core_runtime.di_container"].get_container = lambda: _fake_container

    saved = {}
    for name, mod in stubs.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = mod

    try:
        sys.modules.pop("core_runtime.kernel_core", None)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "core_runtime.kernel_core",
            str(_Path(__file__).resolve().parent.parent / "core_runtime" / "kernel_core.py"),
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["core_runtime.kernel_core"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, orig in saved.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig


def _make_kernel(mod):
    KernelCore = mod.KernelCore
    k = object.__new__(KernelCore)
    k.diagnostics = MagicMock()
    k.config = MagicMock()
    k._flow = None
    k._flow_degraded = False
    k.interface_registry = MagicMock()
    k.install_journal = MagicMock()
    k.event_bus = MagicMock()
    k.lifecycle = MagicMock()
    k._kernel_handlers = {}
    k._shutdown_handlers = []
    k._flow_converter = MagicMock()
    return k


def _real_import():
    """Get the real __import__ safely."""
    if isinstance(__builtins__, dict):
        return __builtins__["__import__"]
    return __builtins__.__import__


class TestParseFlowText(unittest.TestCase):
    """Tests for _parse_flow_text()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _make_kernel_core_module()

    def test_import_error_chains_cause(self):
        """Req1: ImportError -> ValueError with __cause__ == ImportError."""
        k = _make_kernel(self.mod)
        yaml_content = "key: value\nlist:\n  - item1\n"
        ri = _real_import()
        def fake_import(name, *a, **kw):
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return ri(name, *a, **kw)
        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(ValueError) as ctx:
                k._parse_flow_text(yaml_content)
            self.assertIsInstance(ctx.exception.__cause__, ImportError)
            self.assertIn("PyYAML is not installed", str(ctx.exception))

    def test_yaml_not_dict_no_import_cause(self):
        """Req1: YAML that returns non-dict -> ValueError, __cause__ is NOT ImportError."""
        k = _make_kernel(self.mod)
        bad_content = "- just\n- a\n- list\n"
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        with self.assertRaises(ValueError) as ctx:
            k._parse_flow_text(bad_content)
        self.assertNotIsInstance(ctx.exception.__cause__, ImportError)

    def test_normal_yaml_dict(self):
        """Normal YAML dict should parse successfully."""
        k = _make_kernel(self.mod)
        content = "flow_id: test\nsteps: []\n"
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        result, parser, meta = k._parse_flow_text(content)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["flow_id"], "test")
        self.assertEqual(parser, "yaml_pyyaml")


class TestLoadFlowStderr(unittest.TestCase):
    """Tests for load_flow() stderr output."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _make_kernel_core_module()

    def _run_load_flow_with_error(self, exc):
        k = _make_kernel(self.mod)
        k._log_fallback_warning = MagicMock()
        k._load_legacy_flow = MagicMock(return_value={"pipelines": {}})
        captured = StringIO()
        with patch.object(k, "_load_single_flow", side_effect=exc), \
             patch.object(_Path, "exists", return_value=True), \
             patch.object(self.mod, "OFFICIAL_FLOWS_DIR", "/tmp/fake_rumi/flows"), \
             patch("sys.stderr", captured):
            k.load_flow()
        return k, captured.getvalue()

    def test_import_error_stderr(self):
        """Req2: ImportError cause -> stderr mentions PyYAML."""
        ie = ImportError("No module named yaml")
        ve = ValueError("Unable to parse Flow: PyYAML is not installed")
        ve.__cause__ = ie
        _, output = self._run_load_flow_with_error(ve)
        self.assertIn("PyYAML is not installed", output)
        self.assertIn("pip install -r requirements.txt", output)

    def test_value_error_stderr(self):
        """Req2: ValueError (no ImportError cause) -> stderr mentions syntax."""
        ve = ValueError("Unable to parse Flow as YAML or JSON")
        _, output = self._run_load_flow_with_error(ve)
        self.assertIn("Check YAML syntax", output)

    def test_generic_error_stderr(self):
        """Req2: Generic exception -> stderr shows generic message."""
        _, output = self._run_load_flow_with_error(RuntimeError("disk error"))
        self.assertIn("unexpected error", output)

    def test_flow_degraded_after_fallback(self):
        """Req5: _flow_degraded is True after fallback."""
        k, _ = self._run_load_flow_with_error(ValueError("parse fail"))
        self.assertTrue(k._flow_degraded)


class TestLogFallbackWarning(unittest.TestCase):
    """Req3: _log_fallback_warning outputs to stderr only."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _make_kernel_core_module()

    def test_stderr_only(self):
        k = _make_kernel(self.mod)
        stdout_cap = StringIO()
        stderr_cap = StringIO()
        with patch("sys.stdout", stdout_cap), patch("sys.stderr", stderr_cap):
            k._log_fallback_warning()
        self.assertEqual(stdout_cap.getvalue(), "")
        self.assertIn("WARNING", stderr_cap.getvalue())


class TestCheckCriticalDependencies(unittest.TestCase):
    """Req4: _check_critical_dependencies() in app.py."""

    def _get_func(self):
        import importlib.util
        app_path = str(_Path(__file__).resolve().parent.parent / "app.py")
        spec = importlib.util.spec_from_file_location("app_under_test", app_path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            pass
        func = getattr(mod, "_check_critical_dependencies", None)
        self.assertIsNotNone(func, "_check_critical_dependencies not found")
        return func

    def test_yaml_missing(self):
        func = self._get_func()
        ri = _real_import()
        def fake(name, *a, **kw):
            if name == "yaml":
                raise ImportError("no yaml")
            return ri(name, *a, **kw)
        with patch("builtins.__import__", side_effect=fake), \
             patch("builtins.print"):
            with self.assertRaises(SystemExit):
                func()

    def test_cryptography_missing(self):
        func = self._get_func()
        ri = _real_import()
        def fake(name, *a, **kw):
            if name == "cryptography":
                raise ImportError("no cryptography")
            return ri(name, *a, **kw)
        with patch("builtins.__import__", side_effect=fake), \
             patch("builtins.print"):
            with self.assertRaises(SystemExit):
                func()

    def test_all_present(self):
        func = self._get_func()
        ri = _real_import()
        def allow_all(name, *a, **kw):
            if name in ("yaml", "cryptography"):
                return types.ModuleType(name)
            return ri(name, *a, **kw)
        with patch("builtins.__import__", side_effect=allow_all):
            func()  # should not raise


class TestMinimalFallbackFlow(unittest.TestCase):
    """Constraint1: _minimal_fallback_flow unchanged (3 steps)."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _make_kernel_core_module()

    def test_three_steps_only(self):
        k = _make_kernel(self.mod)
        flow = k._minimal_fallback_flow()
        steps = flow["pipelines"]["startup"]
        self.assertEqual(len(steps), 3)
        ids = [s["id"] for s in steps]
        self.assertEqual(ids, ["fallback.mounts", "fallback.registry", "fallback.active"])


if __name__ == "__main__":
    unittest.main()
