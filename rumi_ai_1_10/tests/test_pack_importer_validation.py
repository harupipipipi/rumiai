"""
test_pack_importer_validation.py - Tests for ecosystem.json validation
and build.command recording in PackImporter.

BUG-2-1: ecosystem.json schema validation
BUG-1-1: runtime.build.command recording
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure rumi_ai_1_10/ is on sys.path so 'core_runtime' is importable
_THIS_DIR = Path(__file__).resolve().parent          # tests/
_REPO_DIR = _THIS_DIR.parent                         # rumi_ai_1_10/
if str(_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_DIR))

from core_runtime.pack_importer import PackImporter


# ======================================================================
# Helpers
# ======================================================================

def _make_ecosystem(
    base_dir: Path,
    data: dict,
    filename: str = "ecosystem.json",
) -> Path:
    """Write ecosystem.json to base_dir and return its path."""
    eco_path = base_dir / filename
    with open(eco_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return eco_path


def _valid_ecosystem(**overrides) -> dict:
    """Return a minimal valid ecosystem.json dict."""
    base = {
        "pack_id": "test_pack",
        "version": "1.0.0",
        "metadata": {
            "name": "Test Pack",
            "description": "A test pack",
        },
    }
    base.update(overrides)
    return base


# ======================================================================
# BUG-2-1: _validate_ecosystem_json tests
# ======================================================================

class TestValidateEcosystemJson(unittest.TestCase):
    """Test _validate_ecosystem_json directly."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.importer = PackImporter(staging_root=self._tmpdir)

    def test_valid_ecosystem_json(self):
        """Valid ecosystem.json passes validation."""
        with tempfile.TemporaryDirectory() as td:
            eco_path = _make_ecosystem(Path(td), _valid_ecosystem())
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertTrue(valid)
            self.assertIsNone(err)
            self.assertIsNotNone(data)
            self.assertEqual(data["pack_id"], "test_pack")

    def test_missing_pack_id(self):
        """Missing pack_id fails validation."""
        eco = _valid_ecosystem()
        del eco["pack_id"]
        with tempfile.TemporaryDirectory() as td:
            eco_path = _make_ecosystem(Path(td), eco)
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("pack_id", err)
            self.assertIsNone(data)

    def test_missing_version(self):
        """Missing version fails validation."""
        eco = _valid_ecosystem()
        del eco["version"]
        with tempfile.TemporaryDirectory() as td:
            eco_path = _make_ecosystem(Path(td), eco)
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("version", err)
            self.assertIsNone(data)

    def test_missing_metadata_name(self):
        """Missing metadata.name fails validation."""
        eco = _valid_ecosystem()
        del eco["metadata"]["name"]
        with tempfile.TemporaryDirectory() as td:
            eco_path = _make_ecosystem(Path(td), eco)
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("metadata.name", err)
            self.assertIsNone(data)

    def test_missing_metadata_entirely(self):
        """Missing metadata dict fails validation."""
        eco = _valid_ecosystem()
        del eco["metadata"]
        with tempfile.TemporaryDirectory() as td:
            eco_path = _make_ecosystem(Path(td), eco)
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("metadata.name", err)
            self.assertIsNone(data)

    def test_invalid_field_type_version_int(self):
        """version as integer fails validation."""
        eco = _valid_ecosystem(version=100)
        with tempfile.TemporaryDirectory() as td:
            eco_path = _make_ecosystem(Path(td), eco)
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("version", err)
            self.assertIn("string", err)
            self.assertIsNone(data)

    def test_invalid_field_type_pack_id_int(self):
        """pack_id as integer fails validation."""
        eco = _valid_ecosystem(pack_id=123)
        with tempfile.TemporaryDirectory() as td:
            eco_path = _make_ecosystem(Path(td), eco)
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("pack_id", err)
            self.assertIsNone(data)

    def test_invalid_json(self):
        """Non-JSON content fails validation."""
        with tempfile.TemporaryDirectory() as td:
            eco_path = Path(td) / "ecosystem.json"
            eco_path.write_text("not json {{{", encoding="utf-8")
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("not valid JSON", err)
            self.assertIsNone(data)

    def test_json_array_root(self):
        """JSON array root fails validation."""
        with tempfile.TemporaryDirectory() as td:
            eco_path = Path(td) / "ecosystem.json"
            eco_path.write_text("[1, 2, 3]", encoding="utf-8")
            valid, err, data = self.importer._validate_ecosystem_json(eco_path)
            self.assertFalse(valid)
            self.assertIn("object", err)
            self.assertIsNone(data)


# ======================================================================
# BUG-1-1: build.command recording tests
# ======================================================================

class TestBuildCommandRecording(unittest.TestCase):
    """Test build.command recording via _detect_packs."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.importer = PackImporter(staging_root=self._tmpdir)

    def _make_payload(self, eco_data: dict, pack_name: str = "my_pack") -> Path:
        """Create payload_dir/pack_name/ecosystem.json structure."""
        payload_dir = Path(self._tmpdir) / "test_payload"
        pack_dir = payload_dir / pack_name
        pack_dir.mkdir(parents=True, exist_ok=True)
        _make_ecosystem(pack_dir, eco_data)
        return payload_dir

    def test_build_command_recorded(self):
        """runtime.build.command is recorded in build_commands."""
        eco = _valid_ecosystem()
        eco["runtime"] = {
            "build": {
                "command": "npm install && npm run build",
            },
        }
        payload_dir = self._make_payload(eco)
        pack_ids, is_multi, warnings, build_commands = \
            self.importer._detect_packs(payload_dir)
        self.assertEqual(pack_ids, ["my_pack"])
        self.assertFalse(is_multi)
        self.assertEqual(len(build_commands), 1)
        self.assertEqual(build_commands[0]["pack_id"], "my_pack")
        self.assertEqual(
            build_commands[0]["command"], "npm install && npm run build",
        )

    def test_no_build_command(self):
        """No runtime.build -> build_commands is empty."""
        eco = _valid_ecosystem()
        payload_dir = self._make_payload(eco)
        pack_ids, is_multi, warnings, build_commands = \
            self.importer._detect_packs(payload_dir)
        self.assertEqual(pack_ids, ["my_pack"])
        self.assertEqual(build_commands, [])

    def test_build_command_empty_string_ignored(self):
        """Empty build.command string is ignored."""
        eco = _valid_ecosystem()
        eco["runtime"] = {"build": {"command": "   "}}
        payload_dir = self._make_payload(eco)
        _, _, _, build_commands = self.importer._detect_packs(payload_dir)
        self.assertEqual(build_commands, [])

    def test_build_command_non_string_ignored(self):
        """Non-string build.command is ignored."""
        eco = _valid_ecosystem()
        eco["runtime"] = {"build": {"command": 123}}
        payload_dir = self._make_payload(eco)
        _, _, _, build_commands = self.importer._detect_packs(payload_dir)
        self.assertEqual(build_commands, [])

    def test_validation_failure_skips_in_multipack(self):
        """In multi-pack, invalid ecosystem.json Pack is skipped with warning."""
        payload_dir = Path(self._tmpdir) / "test_payload2"
        top_dir = payload_dir / "bundle"
        packs_dir = top_dir / "packs"

        # valid pack
        valid_dir = packs_dir / "good_pack"
        valid_dir.mkdir(parents=True, exist_ok=True)
        _make_ecosystem(valid_dir, _valid_ecosystem(pack_id="good_pack"))

        # invalid pack (missing version)
        invalid_dir = packs_dir / "bad_pack"
        invalid_dir.mkdir(parents=True, exist_ok=True)
        bad_eco = _valid_ecosystem()
        del bad_eco["version"]
        _make_ecosystem(invalid_dir, bad_eco)

        pack_ids, is_multi, warnings, build_commands = \
            self.importer._detect_packs(payload_dir)
        self.assertTrue(is_multi)
        self.assertEqual(pack_ids, ["good_pack"])
        self.assertNotIn("bad_pack", pack_ids)
        self.assertTrue(any("bad_pack" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
