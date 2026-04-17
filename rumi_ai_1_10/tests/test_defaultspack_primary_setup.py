from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend_core.ecosystem.initializer import EcosystemInitializer
from rumi_setup.core.initializer import Initializer


class TestDefaultspackPrimarySetup(unittest.TestCase):
    def test_backend_initializer_leaves_active_pack_unselected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            initializer = EcosystemInitializer(
                user_data_dir=str(base / "user_data"),
                ecosystem_dir=str(base / "ecosystem"),
            )

            result = initializer.initialize()

            self.assertTrue(result["success"])
            active_path = base / "user_data" / "active_ecosystem.json"
            data = json.loads(active_path.read_text(encoding="utf-8"))
            self.assertIsNone(data["active_pack_identity"])
            self.assertEqual(data["metadata"], {})

    def test_rumi_setup_initializer_leaves_active_pack_unselected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            initializer = Initializer(base_dir=str(base))

            created = initializer._create_user_data()
            self.assertTrue(created)
            active_relpath = initializer._create_active_ecosystem_json()

            self.assertEqual(active_relpath, "user_data/active_ecosystem.json")
            active_path = base / "user_data" / "active_ecosystem.json"
            data = json.loads(active_path.read_text(encoding="utf-8"))
            self.assertIsNone(data["active_pack_identity"])
            self.assertEqual(data["metadata"], {})


if __name__ == "__main__":
    unittest.main()
