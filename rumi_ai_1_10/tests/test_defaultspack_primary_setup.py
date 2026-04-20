from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend_core.ecosystem.initializer import EcosystemInitializer
from core_runtime import setup_pack as setup_pack_module
from core_runtime.paths import PackLocation
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
                target_dir = base / "ecosystem" / setup_pack_id
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / "ecosystem.json").write_text(
                    json.dumps({"pack_identity": f"rumi:ecosystem/{setup_pack_id}"}) + "\n",
                    encoding="utf-8",
                )

            initializer = Initializer(base_dir=str(base))
            discover_calls = []

            def _discover(ecosystem_dir=None):
                discover_calls.append(ecosystem_dir)
                self.assertEqual(Path(ecosystem_dir), base / "ecosystem")
                return [
                    PackLocation(
                        pack_dir=base / "ecosystem" / setup_pack_id,
                        pack_id=setup_pack_id,
                        ecosystem_json_path=(
                            base / "ecosystem" / setup_pack_id / "ecosystem.json"
                        ),
                        pack_subdir=base / "ecosystem" / setup_pack_id,
                    )
                    for setup_pack_id in ("defaultspack", "otherpack")
                ]

            with patch.object(
                setup_pack_module,
                "discover_pack_locations",
                side_effect=_discover,
            ), patch(
                "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
                return_value=SimpleNamespace(active_pack_identity=None),
            ), patch(
                "core_runtime.approval_manager.get_approval_manager",
                return_value=SimpleNamespace(_initialized=False),
            ):
                summary = initializer.initialize(
                    install_default=True,
                    confirm_callback=lambda message: "defaultspack" in message,
                )

            self.assertTrue(summary["success"])
            self.assertEqual(discover_calls, [str(base / "ecosystem")])
            selection_path = base / "user_data" / "settings" / "setup_pack_selection.json"
            self.assertTrue(selection_path.is_file())
            selection = json.loads(selection_path.read_text(encoding="utf-8"))
            self.assertEqual(selection["setup_pack_ids"], ["defaultspack"])
            self.assertEqual(selection["target_pack_ids"], ["defaultspack"])
            self.assertEqual(selection["active_setup_pack_id"], "defaultspack")

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
            with patch.object(Initializer, "_create_setup_pack_manager") as mocked:
                summary = initializer.initialize(
                    install_default=True,
                    confirm_callback=lambda _message: False,
                )

            mocked.assert_not_called()
            self.assertTrue(summary["success"])


if __name__ == "__main__":
    unittest.main()
