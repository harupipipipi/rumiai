from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.setup_pack import SetupPackManager


class _FakeGrantResult:
    def __init__(self, granted_count=0, failed_count=0):
        self.granted_count = granted_count
        self.failed_count = failed_count


class _FakeGrantManager:
    def __init__(self):
        self.batch_calls = []
        self.revocations = []

    def batch_grant(self, grants):
        self.batch_calls.append(grants)
        return _FakeGrantResult(granted_count=len(grants), failed_count=0)

    def revoke_permission(self, principal_id, permission_id):
        self.revocations.append((principal_id, permission_id))
        return True


class TestSetupPackManager(unittest.TestCase):
    def _write_pack(self, root: Path, pack_id: str, target_pack_id: str, supports_all_ok: bool) -> None:
        pack_dir = root / pack_id
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "pack.json").write_text(
            json.dumps(
                {
                    "pack_id": pack_id,
                    "display_name": pack_id,
                    "description": "desc",
                    "target_pack_id": target_pack_id,
                    "recommended": True,
                    "risk_level": "low",
                    "supports_all_ok": supports_all_ok,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_install_writes_selection_and_list_marks_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "setup_pack"
            self._write_pack(root, "defaultspack", "defaultspack", True)
            selection_file = Path(tmp) / "selection.json"
            manager = SetupPackManager(root=root, selection_file=selection_file)
            target_json = Path(tmp) / "ecosystem.json"
            target_json.write_text('{"pack_identity":"rumi:ecosystem/defaultspack"}\n', encoding="utf-8")

            with patch("core_runtime.setup_pack.discover_pack_locations", return_value=[
                SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=target_json)
            ]):
                result = manager.install("defaultspack")

            self.assertTrue(result["installed"])
            self.assertTrue(selection_file.is_file())
            listed = manager.list_packs()
            self.assertEqual(listed["selected_setup_pack_id"], "defaultspack")
            self.assertTrue(listed["packs"][0]["selected"])

    def test_all_ok_only_for_defaultspack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "setup_pack"
            self._write_pack(root, "defaultspack", "defaultspack", True)
            self._write_pack(root, "otherpack", "otherpack", False)
            manager = SetupPackManager(root=root, selection_file=Path(tmp) / "selection.json")
            fake = _FakeGrantManager()

            with patch(
                "core_runtime.capability_grant_manager.get_capability_grant_manager",
                return_value=fake,
            ):
                granted = manager.grant_all_ok("defaultspack")
                denied = manager.grant_all_ok("otherpack")
                revoked = manager.revoke_all_ok("defaultspack")

            self.assertTrue(granted["granted"])
            self.assertEqual(len(fake.batch_calls), 1)
            self.assertEqual(denied["status_code"], 403)
            self.assertTrue(revoked["revoked"])
            self.assertGreater(revoked["revoked_count"], 0)


if __name__ == "__main__":
    unittest.main()
