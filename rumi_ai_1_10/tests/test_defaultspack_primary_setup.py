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

    def test_prepare_setup_pack_targets_requests_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            setup_pack_dir = base / "ecosystem" / "setup_pack" / "defaultspack"
            setup_pack_dir.mkdir(parents=True, exist_ok=True)
            (setup_pack_dir / "pack.json").write_text(
                json.dumps(
                    {
                        "pack_id": "defaultspack",
                        "target_pack_id": "defaultspack",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (base / "ecosystem" / "defaultspack").mkdir(parents=True, exist_ok=True)
            initializer = Initializer(base_dir=str(base))
            prompts = []

            def _deny(message: str) -> bool:
                prompts.append(message)
                return False

            result = initializer._prepare_setup_pack_targets(confirm_callback=_deny)

            self.assertTrue(prompts)
            self.assertTrue(result["skipped"])
            self.assertEqual(result["available_setup_pack_ids"], ["defaultspack"])

    def test_prepare_setup_pack_targets_returns_available_when_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            setup_pack_dir = base / "ecosystem" / "setup_pack" / "defaultspack"
            setup_pack_dir.mkdir(parents=True, exist_ok=True)
            (setup_pack_dir / "pack.json").write_text(
                json.dumps(
                    {
                        "pack_id": "defaultspack",
                        "target_pack_id": "defaultspack",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (base / "ecosystem" / "defaultspack").mkdir(parents=True, exist_ok=True)
            initializer = Initializer(base_dir=str(base))

            result = initializer._prepare_setup_pack_targets(confirm_callback=lambda _: True)

            self.assertFalse(result["skipped"])
            self.assertEqual(result["available_setup_pack_ids"], ["defaultspack"])
            self.assertEqual(result["available"], ["ecosystem/defaultspack"])


if __name__ == "__main__":
    unittest.main()
