"""
test_phase_c.py — Phase C: core_pack Structure & Function Protocol Tests

Tests:
 1. core_store_capability/ exists with ecosystem.json
 2. core_secrets_capability/ exists with ecosystem.json
 3. core_flow_capability/ exists with ecosystem.json
 4. core_communication_capability/ exists with ecosystem.json
 5. core_store_capability has 6 function dirs (get, set, delete, list, batch_get, cas)
 6. core_secrets_capability has 1 function dir (get)
 7. core_flow_capability has 1 function dir (run)
 8. core_communication_capability has 2 function dirs (send, propose_patch)
 9. Each function dir contains manifest.json and main.py
10. Each ecosystem.json is valid JSON with pack_id
11. Each manifest.json is valid JSON with function_id and description
12. Each manifest.json has requires list (permission equivalent)
13. Each manifest.json has host_execution == true (calling_convention equivalent)

Design note (Policy B):
  manifest.json does NOT contain 'permission_id' or 'calling_convention' directly.
  - 'requires' list serves as the permission declaration (equivalent to permission_id).
  - 'host_execution: true' serves as the execution mode (equivalent to calling_convention: "subprocess").
  These are mapped to FunctionEntry-level fields during pack loading.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

CORE_PACK_ROOT = _PROJECT_ROOT / "core_runtime" / "core_pack"

# ---------------------------------------------------------------------------
# Expected structure
# ---------------------------------------------------------------------------
EXPECTED_PACKS = {
    "core_store_capability": {
        "functions": ["get", "set", "delete", "list", "batch_get", "cas"],
    },
    "core_secrets_capability": {
        "functions": ["get"],
    },
    "core_flow_capability": {
        "functions": ["run"],
    },
    "core_communication_capability": {
        "functions": ["send", "propose_patch"],
    },
}


def _all_function_dirs():
    """Yield (pack_name, func_name, func_path) for every expected function."""
    for pack_name, info in EXPECTED_PACKS.items():
        for func_name in info["functions"]:
            func_path = CORE_PACK_ROOT / pack_name / "functions" / func_name
            yield pack_name, func_name, func_path


# ===================================================================
# Test 1-4: Directory structure — each core_pack exists with ecosystem.json
# ===================================================================
class TestCorePackDirectoryStructure(unittest.TestCase):
    """Tests 1-4: Each core_pack directory exists and contains ecosystem.json."""

    def test_01_core_store_capability_exists(self):
        pack_dir = CORE_PACK_ROOT / "core_store_capability"
        self.assertTrue(pack_dir.is_dir(), f"Directory not found: {pack_dir}")
        eco = pack_dir / "ecosystem.json"
        self.assertTrue(eco.is_file(), f"ecosystem.json not found: {eco}")

    def test_02_core_secrets_capability_exists(self):
        pack_dir = CORE_PACK_ROOT / "core_secrets_capability"
        self.assertTrue(pack_dir.is_dir(), f"Directory not found: {pack_dir}")
        eco = pack_dir / "ecosystem.json"
        self.assertTrue(eco.is_file(), f"ecosystem.json not found: {eco}")

    def test_03_core_flow_capability_exists(self):
        pack_dir = CORE_PACK_ROOT / "core_flow_capability"
        self.assertTrue(pack_dir.is_dir(), f"Directory not found: {pack_dir}")
        eco = pack_dir / "ecosystem.json"
        self.assertTrue(eco.is_file(), f"ecosystem.json not found: {eco}")

    def test_04_core_communication_capability_exists(self):
        pack_dir = CORE_PACK_ROOT / "core_communication_capability"
        self.assertTrue(pack_dir.is_dir(), f"Directory not found: {pack_dir}")
        eco = pack_dir / "ecosystem.json"
        self.assertTrue(eco.is_file(), f"ecosystem.json not found: {eco}")


# ===================================================================
# Test 5-8: Function directory counts
# ===================================================================
class TestFunctionDirectoryCounts(unittest.TestCase):
    """Tests 5-8: Each core_pack has the expected number of function directories."""

    def _assert_function_dirs(self, pack_name, expected_names):
        funcs_dir = CORE_PACK_ROOT / pack_name / "functions"
        self.assertTrue(funcs_dir.is_dir(), f"functions/ not found: {funcs_dir}")
        actual = sorted(
            d.name for d in funcs_dir.iterdir() if d.is_dir()
        )
        expected = sorted(expected_names)
        self.assertEqual(
            actual, expected,
            f"{pack_name}: expected {expected}, got {actual}",
        )

    def test_05_store_has_6_functions(self):
        self._assert_function_dirs(
            "core_store_capability",
            ["get", "set", "delete", "list", "batch_get", "cas"],
        )

    def test_06_secrets_has_1_function(self):
        self._assert_function_dirs(
            "core_secrets_capability",
            ["get"],
        )

    def test_07_flow_has_1_function(self):
        self._assert_function_dirs(
            "core_flow_capability",
            ["run"],
        )

    def test_08_communication_has_2_functions(self):
        self._assert_function_dirs(
            "core_communication_capability",
            ["send", "propose_patch"],
        )


# ===================================================================
# Test 9: Each function directory contains manifest.json and main.py
# ===================================================================
class TestFunctionFilesExist(unittest.TestCase):
    """Test 9: Every function directory has manifest.json and main.py."""

    def test_09_each_function_has_manifest_and_main(self):
        for pack_name, func_name, func_path in _all_function_dirs():
            with self.subTest(pack=pack_name, function=func_name):
                self.assertTrue(
                    func_path.is_dir(),
                    f"Function dir missing: {func_path}",
                )
                manifest = func_path / "manifest.json"
                self.assertTrue(
                    manifest.is_file(),
                    f"manifest.json missing: {manifest}",
                )
                main_py = func_path / "main.py"
                self.assertTrue(
                    main_py.is_file(),
                    f"main.py missing: {main_py}",
                )


# ===================================================================
# Test 10: ecosystem.json schema — valid JSON with pack_id
# ===================================================================
class TestEcosystemJsonSchema(unittest.TestCase):
    """Test 10: Each ecosystem.json is valid JSON and contains pack_id."""

    def test_10_ecosystem_valid_json_with_pack_id(self):
        for pack_name in EXPECTED_PACKS:
            eco_path = CORE_PACK_ROOT / pack_name / "ecosystem.json"
            with self.subTest(pack=pack_name):
                self.assertTrue(eco_path.is_file(), f"Not found: {eco_path}")
                with open(eco_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.assertIsInstance(data, dict, "ecosystem.json is not a JSON object")
                self.assertIn("pack_id", data, "Missing pack_id")
                self.assertEqual(
                    data["pack_id"], pack_name,
                    f"pack_id mismatch: expected '{pack_name}', got '{data['pack_id']}'",
                )


# ===================================================================
# Test 11-13: manifest.json schema
# ===================================================================
class TestManifestJsonSchema(unittest.TestCase):
    """Tests 11-13: manifest.json schema validation."""

    def _load_manifest(self, func_path):
        manifest_path = func_path / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_11_manifest_has_function_id_and_description(self):
        for pack_name, func_name, func_path in _all_function_dirs():
            with self.subTest(pack=pack_name, function=func_name):
                data = self._load_manifest(func_path)
                self.assertIn("function_id", data, "Missing function_id")
                self.assertIsInstance(data["function_id"], str)
                self.assertTrue(len(data["function_id"]) > 0, "function_id is empty")
                self.assertIn("description", data, "Missing description")
                self.assertIsInstance(data["description"], str)
                self.assertTrue(len(data["description"]) > 0, "description is empty")

    def test_12_manifest_has_requires_permission(self):
        """Each manifest.json has a non-empty 'requires' list (permission equivalent).

        Design note (Policy B): manifest.json uses 'requires' instead of
        'permission_id'.  The permission_id concept from handler.json is
        mapped at FunctionEntry level during pack loading, not stored in
        the manifest directly.
        """
        for pack_name, func_name, func_path in _all_function_dirs():
            with self.subTest(pack=pack_name, function=func_name):
                data = self._load_manifest(func_path)
                self.assertIn("requires", data, "Missing 'requires'")
                self.assertIsInstance(data["requires"], list, "'requires' is not a list")
                self.assertGreater(
                    len(data["requires"]), 0,
                    "'requires' is empty — at least one permission must be declared",
                )
                for perm in data["requires"]:
                    self.assertIsInstance(perm, str, f"Permission entry is not a string: {perm}")

    def test_13_manifest_has_host_execution_true(self):
        """Each manifest.json has host_execution == true (subprocess equivalent).

        Design note (Policy B): manifest.json uses 'host_execution: true'
        instead of 'calling_convention: "subprocess"'.  The calling_convention
        is inferred at FunctionEntry level during pack loading.
        """
        for pack_name, func_name, func_path in _all_function_dirs():
            with self.subTest(pack=pack_name, function=func_name):
                data = self._load_manifest(func_path)
                self.assertIn("host_execution", data, "Missing 'host_execution'")
                self.assertTrue(
                    data["host_execution"] is True,
                    f"host_execution should be true, got {data['host_execution']}",
                )


if __name__ == "__main__":
    unittest.main()
