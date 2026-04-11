from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.pack_modification_manager import PackModificationManager


class _ApplyResult:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _ApprovalManager:
    def __init__(self):
        self.scanned = 0
        self.approved = []
        self.removed = []

    def scan_packs(self):
        self.scanned += 1
        return []

    def approve(self, pack_id):
        self.approved.append(pack_id)
        return None

    def remove_approval(self, pack_id):
        self.removed.append(pack_id)
        return True


class TestPackModificationManager(unittest.TestCase):
    def _write_meta(self, staging_root: Path, staging_id: str, payload: dict) -> None:
        stage = staging_root / staging_id
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "meta.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_create_and_review_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requests_root = root / "requests"
            backup_root = root / "backups"
            staging_root = root / "staging"
            self._write_meta(
                staging_root,
                "abc123",
                {
                    "staging_id": "abc123",
                    "detected_pack_ids": ["targetpack"],
                    "proposal_info": {
                        "target_pack_id": "targetpack",
                        "changed_paths": ["ecosystem.json"],
                    },
                },
            )
            manager = PackModificationManager(
                requests_root=requests_root,
                ecosystem_dir=root / "ecosystem",
                backup_root=backup_root,
            )

            with patch(
                "core_runtime.pack_modification_manager.get_pack_importer"
            ) as importer:
                importer.return_value.get_staging_meta.return_value = json.loads(
                    (staging_root / "abc123" / "meta.json").read_text(encoding="utf-8")
                )
                created = manager.create_request(
                    mode="request_extension",
                    staging_id="abc123",
                    notes="please extend",
                )

            self.assertEqual(created["status"], "pending")

            fake_approval = _ApprovalManager()
            with patch(
                "core_runtime.pack_modification_manager.get_pack_applier",
                return_value=type("A", (), {
                    "apply": lambda self, staging_id, actor="api_user": _ApplyResult(
                        {
                            "success": True,
                            "applied_pack_ids": ["targetpack"],
                            "backup_paths": {"targetpack": str(backup_root / "targetpack" / "ts")},
                        }
                    )
                })(),
            ), patch(
                "core_runtime.pack_modification_manager.get_approval_manager",
                return_value=fake_approval,
            ):
                approved = manager.approve_request(created["request_id"])

            self.assertEqual(approved["status"], "applied")
            self.assertEqual(fake_approval.approved, ["targetpack"])

    def test_create_request_rejects_fullscreen_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requests_root = root / "requests"
            staging_root = root / "staging"
            self._write_meta(
                staging_root,
                "fullscreen1",
                {
                    "staging_id": "fullscreen1",
                    "detected_pack_ids": ["frontpack"],
                    "proposal_info": {"target_pack_id": "frontpack"},
                },
            )
            self._write_meta(
                staging_root,
                "fullscreen2",
                {
                    "staging_id": "fullscreen2",
                    "detected_pack_ids": ["otherpack"],
                    "proposal_info": {"target_pack_id": "otherpack"},
                },
            )
            manager = PackModificationManager(
                requests_root=requests_root,
                ecosystem_dir=root / "ecosystem",
                backup_root=root / "backups",
            )

            with patch("core_runtime.pack_modification_manager.get_pack_importer") as importer:
                importer.return_value.get_staging_meta.side_effect = lambda staging_id: json.loads(
                    (staging_root / staging_id / "meta.json").read_text(encoding="utf-8")
                )
                created = manager.create_request(
                    mode="request_extension",
                    staging_id="fullscreen1",
                    slot="fullscreen",
                    fullscreen=True,
                )
                blocked = manager.create_request(
                    mode="forced_patch",
                    staging_id="fullscreen2",
                    slot="main",
                )

            self.assertEqual(created["status"], "pending")
            self.assertEqual(blocked["status_code"], 409)
            self.assertEqual(blocked["conflicts"][0]["reason"], "fullscreen_exclusive")

    def test_create_request_marks_same_slot_multi_frontend_for_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requests_root = root / "requests"
            staging_root = root / "staging"
            self._write_meta(
                staging_root,
                "slot1",
                {
                    "staging_id": "slot1",
                    "detected_pack_ids": ["frontpack"],
                    "proposal_info": {"target_pack_id": "frontpack"},
                },
            )
            self._write_meta(
                staging_root,
                "slot2",
                {
                    "staging_id": "slot2",
                    "detected_pack_ids": ["otherpack"],
                    "proposal_info": {"target_pack_id": "otherpack"},
                },
            )
            manager = PackModificationManager(
                requests_root=requests_root,
                ecosystem_dir=root / "ecosystem",
                backup_root=root / "backups",
            )

            with patch("core_runtime.pack_modification_manager.get_pack_importer") as importer:
                importer.return_value.get_staging_meta.side_effect = lambda staging_id: json.loads(
                    (staging_root / staging_id / "meta.json").read_text(encoding="utf-8")
                )
                first = manager.create_request(
                    mode="request_extension",
                    staging_id="slot1",
                    slot="sidebar.right",
                )
                second = manager.create_request(
                    mode="request_extension",
                    staging_id="slot2",
                    slot="sidebar.right",
                )

            self.assertEqual(first["status"], "pending")
            self.assertEqual(second["status"], "pending")
            self.assertTrue(second["selection_required"])
            self.assertEqual(second["selection_candidates"][0]["request_id"], first["request_id"])

    def test_rollback_restores_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requests_root = root / "requests"
            ecosystem = root / "ecosystem"
            backup_root = root / "backups"
            backup_dir = backup_root / "targetpack" / "ts"
            backup_dir.mkdir(parents=True)
            (backup_dir / "ecosystem.json").write_text('{"pack_id":"targetpack"}\n', encoding="utf-8")

            manager = PackModificationManager(
                requests_root=requests_root,
                ecosystem_dir=ecosystem,
                backup_root=backup_root,
            )
            request_file = requests_root / "req1.json"
            request_file.parent.mkdir(parents=True, exist_ok=True)
            request_file.write_text(
                json.dumps(
                    {
                        "request_id": "req1",
                        "mode": "forced_patch",
                        "status": "applied",
                        "staging_id": "stage1",
                        "target_pack_id": "targetpack",
                        "actor": "defaultspack",
                        "created_at": "2026-01-01T00:00:00Z",
                        "backup_paths": {"targetpack": str(backup_dir)},
                        "applied_pack_ids": ["targetpack"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            fake_approval = _ApprovalManager()
            with patch(
                "core_runtime.pack_modification_manager.get_approval_manager",
                return_value=fake_approval,
            ):
                rolled_back = manager.rollback_request("req1")

            self.assertEqual(rolled_back["status"], "rolled_back")
            self.assertTrue((ecosystem / "targetpack" / "ecosystem.json").is_file())

    def test_rollback_removes_newly_created_pack_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requests_root = root / "requests"
            ecosystem = root / "ecosystem"
            created_pack = ecosystem / "newpack"
            created_pack.mkdir(parents=True, exist_ok=True)
            (created_pack / "ecosystem.json").write_text(
                '{"pack_id":"newpack"}\n',
                encoding="utf-8",
            )

            manager = PackModificationManager(
                requests_root=requests_root,
                ecosystem_dir=ecosystem,
                backup_root=root / "backups",
            )
            request_file = requests_root / "req2.json"
            request_file.parent.mkdir(parents=True, exist_ok=True)
            request_file.write_text(
                json.dumps(
                    {
                        "request_id": "req2",
                        "mode": "forced_patch",
                        "status": "applied",
                        "staging_id": "stage2",
                        "target_pack_id": "newpack",
                        "actor": "defaultspack",
                        "created_at": "2026-01-01T00:00:00Z",
                        "backup_paths": {},
                        "applied_pack_ids": ["newpack"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            fake_approval = _ApprovalManager()
            with patch(
                "core_runtime.pack_modification_manager.get_approval_manager",
                return_value=fake_approval,
            ):
                rolled_back = manager.rollback_request("req2")

            self.assertEqual(rolled_back["status"], "rolled_back")
            self.assertFalse(created_pack.exists())
            self.assertEqual(fake_approval.removed, ["newpack"])


if __name__ == "__main__":
    unittest.main()
