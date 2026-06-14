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
        version: str = "1.0.0",
        compatibility: dict | None = None,
        depends_on: list | None = None,
        conflicts_with: list | None = None,
        overlap_policy: dict | None = None,
        defaultspack_promotion: dict | None = None,
        marketplace: dict | None = None,
        signing: dict | None = None,
    ) -> None:
        pack_dir = root / pack_id
        pack_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "pack_id": pack_id,
            "display_name": pack_id,
            "description": "desc",
            "target_pack_id": target_pack_id,
            "version": version,
            "recommended": recommended,
            "risk_level": "low",
            "supports_all_ok": supports_all_ok,
        }
        if compatibility is not None:
            payload["compatibility"] = compatibility
        if depends_on is not None:
            payload["depends_on"] = depends_on
        if conflicts_with is not None:
            payload["conflicts_with"] = conflicts_with
        if overlap_policy is not None:
            payload["overlap_policy"] = overlap_policy
        if defaultspack_promotion is not None:
            payload["defaultspack_promotion"] = defaultspack_promotion
        if marketplace is not None:
            payload["marketplace"] = marketplace
        if signing is not None:
            payload["signing"] = signing
        (pack_dir / "pack.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

    def _target(
        self,
        tmp: Path,
        pack_id: str,
        identity: str,
        *,
        version: str = "1.0.0",
    ) -> SimpleNamespace:
        target_json = tmp / f"{pack_id}.ecosystem.json"
        target_json.write_text(
            json.dumps({"pack_identity": identity, "version": version}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(pack_id=pack_id, ecosystem_json_path=target_json)

    def _install_context(self, tmp: Path, targets, fake_grants=None):
        fake_active = SimpleNamespace(active_pack_identity=None)
        fake_approval = SimpleNamespace(_initialized=False)
        if fake_grants is None:
            fake_grants = _FakeGrantManager()
        setup_pack_module = sys.modules[SetupPackManager.__module__]
        return (
            fake_active,
            fake_grants,
            patch.object(setup_pack_module, "discover_pack_locations", return_value=targets),
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
            self.assertEqual(result["active_setup_pack_id"], "defaultspack")
            self.assertEqual(result["installed_setup_pack_ids"], ["defaultspack"])
            self.assertEqual(result["installed_target_pack_ids"], ["defaultspack"])
            self.assertEqual(result["installed_setup_target_map"], {"defaultspack": "defaultspack"})
            self.assertEqual(result["granted_all_ok_target_pack_ids"], ["defaultspack"])
            self.assertEqual(result["skipped_all_ok_setup_pack_ids"], [])
            self.assertEqual(fake_active.active_pack_identity, "rumi:ecosystem/defaultspack")
            self.assertEqual(len(fake_grants.batch_calls), 1)

            selection = json.loads((base / "selection.json").read_text(encoding="utf-8"))
            self.assertEqual(selection["setup_pack_ids"], ["defaultspack"])
            self.assertEqual(selection["active_setup_pack_id"], "defaultspack")
            listed = manager.list_packs()
            self.assertEqual(listed["selected_setup_pack_ids"], ["defaultspack"])
            self.assertTrue(listed["packs"][0]["selected"])

    def test_multiple_install_skips_all_ok_for_unsupported_setup_pack(self):
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
            self.assertEqual(result["installed_setup_pack_ids"], ["otherpack", "defaultspack"])
            self.assertEqual(result["installed_target_pack_ids"], ["otherpack", "defaultspack"])
            self.assertEqual(result["active_setup_pack_id"], "defaultspack")
            self.assertEqual(result["active_target_pack_id"], "defaultspack")
            self.assertEqual(result["granted_all_ok_target_pack_ids"], ["defaultspack"])
            self.assertEqual(result["skipped_all_ok_setup_pack_ids"], ["otherpack"])
            self.assertEqual(len(fake_grants.batch_calls), 1)
            principals = [call[0]["principal_id"] for call in fake_grants.batch_calls]
            self.assertEqual(principals, ["defaultspack"])

    def test_install_auto_includes_declared_setup_pack_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(root, "defaultspack", "defaultspack", True, recommended=True)
            self._write_pack(root, "tools", "tools", True)
            self._write_pack(
                root,
                "codepack",
                "codepack",
                False,
                depends_on=[
                    {"pack_id": "defaultspack", "version": ">=1.0.0"},
                    {"pack_id": "tools", "version": ">=1.0.0"},
                ],
            )
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [
                    self._target(base, "defaultspack", "rumi:ecosystem/defaultspack"),
                    self._target(base, "tools", "rumi:ecosystem/tools"),
                    self._target(base, "codepack", "rumi:ecosystem/codepack"),
                ],
            )
            fake_active, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install("codepack")

            self.assertTrue(result["success"])
            self.assertEqual(
                result["installed_setup_pack_ids"],
                ["defaultspack", "tools", "codepack"],
            )
            self.assertEqual(
                result["installed_target_pack_ids"],
                ["defaultspack", "tools", "codepack"],
            )
            self.assertEqual(result["active_setup_pack_id"], "defaultspack")
            self.assertEqual(result["active_target_pack_id"], "defaultspack")
            self.assertEqual(result["granted_all_ok_target_pack_ids"], ["defaultspack", "tools"])
            self.assertEqual(result["skipped_all_ok_setup_pack_ids"], ["codepack"])
            self.assertEqual(fake_active.active_pack_identity, "rumi:ecosystem/defaultspack")
            principals = [call[0]["principal_id"] for call in fake_grants.batch_calls]
            self.assertEqual(principals, ["defaultspack", "tools"])

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
            listed = manager.list_packs()
            self.assertEqual(listed["selected_setup_pack_ids"], ["alpha", "zeta"])
            self.assertEqual(listed["active_setup_pack_id"], "zeta")
            self.assertEqual(listed["active_target_pack_id"], "zeta")

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
            self.assertEqual(result["active_setup_pack_id"], "beta")
            self.assertEqual(fake_active.active_pack_identity, "rumi:ecosystem/beta")
            listed = manager.list_packs()
            self.assertEqual(listed["selected_setup_pack_ids"], ["beta", "alpha"])
            self.assertEqual(listed["active_setup_pack_id"], "beta")
            self.assertEqual(listed["active_target_pack_id"], "beta")

    def test_list_packs_exposes_overlap_and_promotion_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(
                root,
                "workspace",
                "workspace",
                True,
                conflicts_with=[
                    {
                        "pack_id": "legacy_workspace",
                        "reason": "Both own slide and sheet recipes.",
                        "resolution": "prefer_workspace",
                    }
                ],
                overlap_policy={"tool_aliases": "prefer_explicit_pack_namespace"},
                defaultspack_promotion={"eligible": True, "criteria": ["local_first", "tests_pass"]},
            )
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            listed = manager.list_packs()
            pack = listed["packs"][0]

            self.assertEqual(pack["conflicts_with"][0]["pack_id"], "legacy_workspace")
            self.assertEqual(pack["overlap_policy"]["tool_aliases"], "prefer_explicit_pack_namespace")
            self.assertTrue(pack["defaultspack_promotion"]["eligible"])

    def test_install_rejects_declared_setup_pack_conflict_before_grants(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(
                root,
                "workspace_a",
                "workspace_a",
                True,
                conflicts_with=[
                    {
                        "pack_id": "workspace_b",
                        "reason": "Both register the same workspace surface.",
                        "resolution": "choose_one_pack",
                    }
                ],
            )
            self._write_pack(root, "workspace_b", "workspace_b", True)
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [
                    self._target(base, "workspace_a", "rumi:ecosystem/workspace_a"),
                    self._target(base, "workspace_b", "rumi:ecosystem/workspace_b"),
                ],
            )
            _, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install(["workspace_a", "workspace_b"])

            self.assertFalse(result["success"])
            self.assertEqual(result["status_code"], 400)
            self.assertEqual(result["errors"][0]["reason"], "setup_pack_conflict")
            self.assertEqual(result["errors"][0]["resolution"], "choose_one_pack")
            self.assertEqual(fake_grants.batch_calls, [])

    def test_install_rejects_invalid_setup_pack_metadata_schema_before_grants(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            pack_dir = root / "workspace"
            pack_dir.mkdir(parents=True)
            (pack_dir / "pack.json").write_text(
                json.dumps(
                    {
                        "pack_id": "workspace",
                        "target_pack_id": "workspace",
                        "supports_all_ok": True,
                        "conflicts_with": [
                            {
                                "reason": "Missing conflicting pack id.",
                                "resolution": "choose_one_pack",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [self._target(base, "workspace", "rumi:ecosystem/workspace")],
            )
            _, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install("workspace")

            self.assertFalse(result["success"])
            self.assertEqual(result["status_code"], 400)
            self.assertEqual(result["errors"][0]["reason"], "invalid_setup_pack_schema")
            self.assertEqual(result["errors"][0]["field"], "conflicts_with[0]")
            self.assertEqual(fake_grants.batch_calls, [])

    def test_grant_and_revoke_all_ok_reject_unsupported_setup_pack_entries(self):
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

            self.assertEqual(granted["status_code"], 400)
            self.assertEqual(granted["reason"], "unsupported_all_ok")
            self.assertEqual(revoked["status_code"], 400)
            self.assertEqual(revoked["reason"], "unsupported_all_ok")
            self.assertEqual(fake.batch_calls, [])
            self.assertEqual(fake.revocations, [])

    def test_install_rejects_missing_setup_pack_dependency_before_grants(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(
                root,
                "addon",
                "addon",
                True,
                depends_on=[{"pack_id": "defaultspack", "version": ">=2.0.0"}],
            )
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [self._target(base, "addon", "rumi:ecosystem/addon")],
            )
            _, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install("addon")

            self.assertFalse(result["success"])
            self.assertEqual(result["status_code"], 400)
            self.assertEqual(result["errors"][0]["reason"], "dependency_missing")
            self.assertEqual(fake_grants.batch_calls, [])

    def test_install_rejects_target_version_mismatch_before_grants(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(
                root,
                "defaultspack",
                "defaultspack",
                True,
                compatibility={"target_pack_version": ">=2.0.0"},
            )
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [self._target(base, "defaultspack", "rumi:ecosystem/defaultspack", version="1.9.0")],
            )
            _, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install("defaultspack")

            self.assertFalse(result["success"])
            self.assertEqual(result["status_code"], 400)
            self.assertEqual(result["errors"][0]["reason"], "target_version_mismatch")
            self.assertEqual(fake_grants.batch_calls, [])

    def test_install_rejects_blacklisted_marketplace_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "setup_pack"
            self._write_pack(
                root,
                "risky",
                "risky",
                True,
                marketplace={"status": "blacklisted", "registry": "test"},
            )
            manager = SetupPackManager(root=root, selection_file=base / "selection.json")

            ctx = self._install_context(
                base,
                [self._target(base, "risky", "rumi:ecosystem/risky")],
            )
            _, fake_grants, *patches = ctx
            with patches[0], patches[1], patches[2], patches[3]:
                result = manager.install("risky")

            self.assertFalse(result["success"])
            self.assertEqual(result["errors"][0]["reason"], "marketplace_blacklisted")
            self.assertEqual(fake_grants.batch_calls, [])

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

    def test_audit_logging_marks_unsupported_all_ok_rejection_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "setup_pack"
            self._write_pack(root, "otherpack", "otherpack", False)
            manager = SetupPackManager(root=root, selection_file=Path(tmp) / "selection.json")
            audit = _FakeAuditLogger()

            with patch(
                "core_runtime.audit_logger.get_audit_logger",
                return_value=audit,
            ):
                manager.grant_all_ok("otherpack")
                manager.revoke_all_ok("otherpack")

            self.assertEqual(len(audit.permission), 2)
            self.assertEqual(audit.permission[0][5], "unsupported_all_ok")
            self.assertEqual(audit.permission[1][5], "unsupported_all_ok")


if __name__ == "__main__":
    unittest.main()
