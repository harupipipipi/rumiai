"""Tests for pack_modifier.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ecosystem.defaultspack.pack_modifier import (
    PackModifier, ModifyMode, ApprovalStatus,
)


class TestPackModifier:
    def test_request_extension(self):
        pm = PackModifier()
        req = pm.request_extension("pack1", "sidebar", "Add widget", "user1")
        assert req.mode == ModifyMode.REQUEST_EXTENSION
        assert req.status == ApprovalStatus.PENDING

    def test_forced_patch(self):
        pm = PackModifier()
        req = pm.forced_patch("pack1", "sidebar", "Override widget", "admin")
        assert req.mode == ModifyMode.FORCED_PATCH

    def test_approve_request(self):
        pm = PackModifier()
        req = pm.request_extension("pack1", "sidebar", "Add widget", "user1")
        assert pm.approve(req.request_id, "admin")
        assert req.status == ApprovalStatus.APPROVED
        assert pm.get_active_slots()["sidebar"] == "pack1"

    def test_reject_request(self):
        pm = PackModifier()
        req = pm.request_extension("pack1", "sidebar", "Add", "user1")
        assert pm.reject(req.request_id, "admin")
        assert req.status == ApprovalStatus.REJECTED

    def test_slot_conflict_extension(self):
        pm = PackModifier()
        req1 = pm.request_extension("pack1", "sidebar", "w1", "u1")
        pm.approve(req1.request_id, "admin")
        req2 = pm.request_extension("pack2", "sidebar", "w2", "u2")
        assert not pm.approve(req2.request_id, "admin")

    def test_forced_patch_overrides_slot(self):
        pm = PackModifier()
        req1 = pm.request_extension("pack1", "sidebar", "w1", "u1")
        pm.approve(req1.request_id, "admin")
        req2 = pm.forced_patch("pack2", "sidebar", "override", "admin")
        assert pm.approve(req2.request_id, "admin")
        assert pm.get_active_slots()["sidebar"] == "pack2"

    def test_rollback(self):
        pm = PackModifier()
        req1 = pm.request_extension("pack1", "sidebar", "w1", "u1")
        pm.approve(req1.request_id, "admin")
        req2 = pm.forced_patch("pack2", "sidebar", "override", "admin")
        pm.approve(req2.request_id, "admin")
        assert pm.rollback(req2.request_id)
        assert pm.get_active_slots()["sidebar"] == "pack1"

    def test_audit_log(self):
        pm = PackModifier()
        req = pm.request_extension("p1", "s1", "d", "u1")
        pm.approve(req.request_id, "admin")
        log = pm.get_audit_log()
        assert len(log) >= 2
