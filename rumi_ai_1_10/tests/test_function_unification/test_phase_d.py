"""test_phase_d.py - Phase D regression tests"""
import ast, sys, unittest
from pathlib import Path
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CR = _REPO_ROOT / "core_runtime"

class TestFileDeletion(unittest.TestCase):
    def test_handler_registry_deleted(self):
        self.assertFalse((_CR / "capability_handler_registry.py").exists())
    def test_handler_registry_not_importable(self):
        with self.assertRaises((ImportError, ModuleNotFoundError)):
            from core_runtime.capability_handler_registry import CapabilityHandlerRegistry
    def test_builtin_handlers_deleted(self):
        self.assertFalse((_CR / "builtin_capability_handlers").exists())
    def test_docker_handlers_deleted(self):
        self.assertFalse((_CR / "core_pack" / "core_docker_capability" / "share" / "capability_handlers").exists())

class TestSourceCleanup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_CR / "capability_executor.py", encoding="utf-8") as f: cls.src = f.read()
        with open(_CR / "function_registry.py", encoding="utf-8") as f: cls.fr_src = f.read()
    def test_no_legacy_methods(self):
        for n in ast.walk(ast.parse(self.src)):
            if isinstance(n, ast.FunctionDef) and "_legacy_" in n.name:
                self.fail(f"Legacy method: {n.name}")
    def test_no_handler_to_manifest_adapter_executor(self):
        self.assertNotIn("handler_to_manifest_adapter", self.src)
    def test_no_handler_to_manifest_adapter_registry(self):
        self.assertNotIn("handler_to_manifest_adapter", self.fr_src)
    def test_no_capability_handler_registry_import(self):
        self.assertNotIn("capability_handler_registry", self.src)
    def test_no_register_builtin(self):
        self.assertNotIn("_register_builtin_handlers", self.src)
    def test_no_strict_legacy(self):
        self.assertNotIn("RUMI_STRICT_LEGACY", self.src)
    def test_no_handler_registry_attr(self):
        self.assertNotIn("_handler_registry", self.src)
    def test_unified_execute_exists(self):
        self.assertIn("def _unified_execute", self.src)
    def test_compute_sha256_exists(self):
        self.assertIn("def compute_file_sha256", self.src)
    def test_manifest_registry_alias(self):
        self.assertIn("ManifestRegistry = FunctionRegistry", self.fr_src)

class TestBehavior(unittest.TestCase):
    def test_unknown_permission_handler_not_found(self):
        try:
            sys.path.insert(0, str(_REPO_ROOT))
            from core_runtime.capability_executor import CapabilityExecutor
            ex = CapabilityExecutor(); ex._initialized = True
            ex._function_registry = MagicMock(); ex._function_registry.resolve_by_alias.return_value = None
            r = ex.execute("p", {"permission_id": "x.y", "args": {}})
            self.assertFalse(r.success); self.assertEqual(r.error_type, "handler_not_found")
        except ImportError: self.skipTest("import failed")
        finally:
            if str(_REPO_ROOT) in sys.path: sys.path.remove(str(_REPO_ROOT))
    def test_function_call_no_registry(self):
        try:
            sys.path.insert(0, str(_REPO_ROOT))
            from core_runtime.capability_executor import CapabilityExecutor
            ex = CapabilityExecutor(); ex._initialized = True; ex._function_registry = None
            r = ex.execute("p", {"type": "function.call", "qualified_name": "a:b", "args": {}})
            self.assertFalse(r.success); self.assertEqual(r.error_type, "function_registry_unavailable")
        except ImportError: self.skipTest("import failed")
        finally:
            if str(_REPO_ROOT) in sys.path: sys.path.remove(str(_REPO_ROOT))
    def test_resolve_by_alias_called(self):
        try:
            sys.path.insert(0, str(_REPO_ROOT))
            from core_runtime.capability_executor import CapabilityExecutor
            ex = CapabilityExecutor(); ex._initialized = True
            m = MagicMock(); e = MagicMock(); e.vocab_aliases = ["t.p"]; e.qualified_name = "p:f"
            e.pack_id = "core_t"; e.main_py_path = None; e.grant_config = None
            e.calling_convention = None; e.entrypoint = "main.py:run"; e.function_dir = "/tmp/x"; e.is_builtin = False
            m.resolve_by_alias.return_value = e
            ex._function_registry = m; ex._trust_store = MagicMock(); ex._grant_manager = MagicMock()
            ex.execute("p", {"permission_id": "t.p", "args": {}})
            m.resolve_by_alias.assert_called_once_with("t.p")
        except ImportError: self.skipTest("import failed")
        finally:
            if str(_REPO_ROOT) in sys.path: sys.path.remove(str(_REPO_ROOT))

if __name__ == "__main__": unittest.main()
