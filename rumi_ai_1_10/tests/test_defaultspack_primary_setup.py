from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            self.assertEqual(result["selected_setup_pack_ids"], [])

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
            self.assertEqual(result["selected_setup_pack_ids"], ["defaultspack"])
            self.assertEqual(result["available"], ["ecosystem/defaultspack"])

    def test_prepare_setup_pack_targets_supports_per_pack_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for setup_pack_id in ("defaultspack", "otherpack"):
                setup_pack_dir = base / "ecosystem" / "setup_pack" / setup_pack_id
                setup_pack_dir.mkdir(parents=True, exist_ok=True)
                (setup_pack_dir / "pack.json").write_text(
                    json.dumps(
                        {
                            "pack_id": setup_pack_id,
                            "target_pack_id": setup_pack_id,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (base / "ecosystem" / setup_pack_id).mkdir(parents=True, exist_ok=True)

            initializer = Initializer(base_dir=str(base))

            def _confirm(message: str) -> bool:
                return "defaultspack" in message

            result = initializer._prepare_setup_pack_targets(confirm_callback=_confirm)

            self.assertFalse(result["skipped"])
            self.assertEqual(result["available_setup_pack_ids"], ["defaultspack", "otherpack"])
            self.assertEqual(result["selected_setup_pack_ids"], ["defaultspack"])

    def test_initialize_installs_only_selected_setup_packs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for setup_pack_id in ("defaultspack", "otherpack"):
                setup_pack_dir = base / "ecosystem" / "setup_pack" / setup_pack_id
                setup_pack_dir.mkdir(parents=True, exist_ok=True)
                (setup_pack_dir / "pack.json").write_text(
                    json.dumps(
                        {
                            "pack_id": setup_pack_id,
                            "target_pack_id": setup_pack_id,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (base / "ecosystem" / setup_pack_id).mkdir(parents=True, exist_ok=True)

            initializer = Initializer(base_dir=str(base))

            with patch("rumi_setup.core.initializer.get_setup_pack_manager") as mocked:
                mocked.return_value.install.return_value = {
                    "installed": True,
                    "success": True,
                    "installed_setup_pack_ids": ["defaultspack"],
                }
                summary = initializer.initialize(
                    install_default=True,
                    confirm_callback=lambda message: "defaultspack" in message,
                )

            mocked.return_value.install.assert_called_once_with(["defaultspack"])
            self.assertTrue(summary["success"])

    def test_initialize_skips_install_when_all_setup_packs_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for setup_pack_id in ("defaultspack", "otherpack"):
                setup_pack_dir = base / "ecosystem" / "setup_pack" / setup_pack_id
                setup_pack_dir.mkdir(parents=True, exist_ok=True)
                (setup_pack_dir / "pack.json").write_text(
                    json.dumps(
                        {
                            "pack_id": setup_pack_id,
                            "target_pack_id": setup_pack_id,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (base / "ecosystem" / setup_pack_id).mkdir(parents=True, exist_ok=True)

            initializer = Initializer(base_dir=str(base))
            with patch("rumi_setup.core.initializer.get_setup_pack_manager") as mocked:
                summary = initializer.initialize(
                    install_default=True,
                    confirm_callback=lambda _message: False,
                )

            mocked.return_value.install.assert_not_called()
            self.assertTrue(summary["success"])


if __name__ == "__main__":
    unittest.main()
