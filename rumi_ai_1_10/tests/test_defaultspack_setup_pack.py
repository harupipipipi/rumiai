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
    def __init__(self, *, fail=False):
        self.batch_calls = []
        self.revocations = []
        self.fail = fail

    def batch_grant(self, grants):
        self.batch_calls.append(grants)
        if self.fail:
            return _FakeGrantResult(granted_count=0, failed_count=len(grants))
        return _FakeGrantResult(granted_count=len(grants), failed_count=0)

    def revoke_permission(self, principal_id, permission_id):
        self.revocations.append((principal_id, permission_id))
        return True


class _FakeAuditLogger:
    def __init__(self):
        self.system = []
        self.permission = []

    def log_system_event(self, event_type, success, details=None, error=None):
        self.system.append((event_type, success, details, error))

    def log_permission_event(
        self,
        pack_id,
        permission_type,
        action,
        success,
        details=None,
        rejection_reason=None,
    ):
        self.permission.append(
            (pack_id, permission_type, action, success, details, rejection_reason)
        )


class TestSetupPackManager(unittest.TestCase):
    def _write_pack(
        self,
        root: Path,
        pack_id: str,
        target_pack_id: str,
        supports_all_ok: bool,
        *,
        recommended: bool = False,
    ) -> None:
        pack_dir = root / pack_id
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "pack.json").write_text(
            json.dumps(
                {
                    "pack_id": pack_id,
                    "display_name": pack_id,
                    "description": "desc",
                    "target_pack_id": target_pack_id,
                    "recommended": recommended,
                    "risk_level": "low",
                    "supports_all_ok": supports_all_ok,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _target(self, tmp: Path, pack_id: str, identity: str) -> SimpleNamespace:
        target_json = tmp / f"{pack_id}.ecosystem.json"
        target_json.write_text(
            json.dumps({"pack_identity": identity}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(pack_id=pack_id, ecosystem_json_path=target_json)

    def _install_context(self, tmp: Path, targets, fake_grants=None):
        fake_active = SimpleNamespace(active_pack_identity=None)
        fake_approval = SimpleNamespace(_initialized=False)
        if fake_grants is None:
            fake_grants = _FakeGrantManager()
        return (
            fake_active,
            fake_grants,
            patch("core_runtime.setup_pack.discover_pack_locations", return_value=targets),
            patch(
                "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
                return_value=fake_active,
            ),
            patch(
                "core_runtime.approval_manager.get_approval_manager",
                return_value=fake_approval,
            ),
            patch(
                "core_runtime.capability_grant_manager.get_capability_grant_manager",
                return_value=fake_grants,
            ),
        )

    def test_single_install_writes_multi_shape_selection_and_marks_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(root, "defaultspack", "defaultspack", True, recommended=True)
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [self._target(base, "defaultspack", "rumi:ecosystem/defaultspack")],
            )
            fake_active, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install("defaultspack")

            self.assertTrue(result["success"])
            self.assertEqual(result["setup_pack_id"], "defaultspack")
            self.assertEqual(result["installed_setup_pack_ids"], ["defaultspack"])
            self.assertEqual(result["granted_all_ok_target_pack_ids"], ["defaultspack"])
            self.assertEqual(fake_active.active_pack_identity, "rumi:ecosystem/defaultspack")
            self.assertEqual(len(fake_grants.batch_calls), 1)

            selection = json.loads((base / "selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["setup_pack_ids"], ["defaultspack"])
            self.assertEqual(selection["active_setup_pack_id"], "defaultspack")
            listed = manager.list_packs()
            self.assertEqual(listed["selected_setup_pack_ids"], ["defaultspack"])
            self.assertTrue(listed["packs"][0]["selected"])

    def test_multiple_install_grants_all_checked_setup_packs_even_without_support_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(root, "defaultspack", "defaultspack", True, recommended=True)
            self._write_pack(root, "otherpack", "otherpack", False)
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [
                    self._target(base, "defaultspack", "rumi:ecosystem/defaultspack"),
                    self._target(base, "otherpack", "rumi:ecosystem/otherpack"),
                ],
            )
            _, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install(["otherpack", "defaultspack"])

            self.assertTrue(result["success"])
            self.assertEqual(result["installed_setup_pack_ids"], ["defaultspack", "otherpack"])
            self.assertEqual(result["active_setup_pack_id"], "defaultspack")
            self.assertEqual(result["active_target_pack_id"], "defaultspack")
            self.assertEqual(len(fake_grants.batch_calls), 2)
            principals = [call[0]["principal_id"] for call in fake_grants.batch_calls]
            self.assertEqual(principals, ["defaultspack", "otherpack"])

    def test_recommended_selected_pack_becomes_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(root, "alpha", "alpha", False)
            self._write_pack(root, "zeta", "zeta", False, recommended=True)
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [
                    self._target(base, "alpha", "rumi:ecosystem/alpha"),
                    self._target(base, "zeta", "rumi:ecosystem/zeta"),
                ],
            )
            fake_active, _, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install(["alpha", "zeta"])

            self.assertTrue(result["success"])
            self.assertEqual(result["active_setup_pack_id"], "zeta")
            self.assertEqual(fake_active.active_pack_identity, "rumi:ecosystem/zeta")

    def test_display_order_first_selected_pack_becomes_active_without_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(root, "beta", "beta", False)
            self._write_pack(root, "alpha", "alpha", False)
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [
                    self._target(base, "alpha", "rumi:ecosystem/alpha"),
                    self._target(base, "beta", "rumi:ecosystem/beta"),
                ],
            )
            fake_active, _, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install(["beta", "alpha"])

            self.assertTrue(result["success"])
            self.assertEqual(result["active_setup_pack_id"], "alpha")
            self.assertEqual(fake_active.active_pack_identity, "rumi:ecosystem/alpha")

    def test_grant_and_revoke_all_ok_are_generic_for_setup_pack_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(root, "otherpack", "otherpack", False)
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")
            fake = _FakeGrantManager()

            with patch(
                "core_runtime.capability_grant_manager.get_capability_grant_manager",
                return_value=fake,
            ):
                granted = manager.grant_all_ok("otherpack")
                revoked = manager.revoke_all_ok("otherpack")

            self.assertTrue(granted["granted"])
            self.assertEqual(granted["principal_id"], "otherpack")
            self.assertTrue(revoked["revoked"])
            self.assertGreater(revoked["revoked_count"], 0)

    def test_audit_logging_uses_supported_signatures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "setup_pack"
            self._write_pack(root, "defaultspack", "defaultspack", True)
            manager = SetupPackManager(root=root, selection_file=Path(tmp) / "selection.json")
            audit = _FakeAuditLogger()
            fake = _FakeGrantManager()

            with patch(
                "core_runtime.audit_logger.get_audit_logger",
                return_value=audit,
            ), patch(
                "core_runtime.capability_grant_manager.get_capability_grant_manager",
                return_value=fake,
            ):
                manager.grant_all_ok("defaultspack")

            self.assertEqual(len(audit.permission), 1)
            self.assertEqual(audit.permission[0][0], "defaultspack")
            self.assertEqual(audit.permission[0][1], "*")


if __name__ == "__main__":
    unittest.main()
