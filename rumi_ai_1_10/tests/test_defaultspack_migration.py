from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.defaultspack_migration import DefaultspackMigrationManager


class TestDefaultspackMigration(unittest.TestCase):
    def test_status_and_csv_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_defaults = root / "defaults"
            legacy_defaults.mkdir()
            user_csv = root / "user.csv"
            user_json = root / "user.json"
            user_csv.write_text("key,value\nname,Rumi\nmode,chat\n", encoding="utf-8")

            manager = DefaultspackMigrationManager(
                legacy_defaults_dir=legacy_defaults,
                legacy_user_csv=user_csv,
                user_json=user_json,
            )
            status = manager.status()
            self.assertTrue(status["legacy_defaults_present"])
            self.assertTrue(status["needs_user_migration"])

            migrated = manager.migrate_user_csv()
            self.assertTrue(migrated["migrated"])
            payload = json.loads(user_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["name"], "Rumi")
            self.assertEqual(payload["mode"], "chat")


if __name__ == "__main__":
    unittest.main()
