"""Tests for setup_pack.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ecosystem.defaultspack.setup_pack import (
    SetupPackManager, PackPermissionLevel, PackRisk,
)


class TestSetupPackManager:
    def test_enumerate_packs(self):
        mgr = SetupPackManager()
        packs = mgr.enumerate_packs()
        assert len(packs) >= 1
        assert packs[0].pack_id == "defaultspack"
        assert packs[0].is_defaults

    def test_install_defaults_gets_all_ok(self):
        mgr = SetupPackManager()
        result = mgr.install_pack("defaultspack")
        assert result.success
        assert result.permission_level == PackPermissionLevel.ALL_OK

    def test_is_all_ok(self):
        mgr = SetupPackManager()
        mgr.install_pack("defaultspack")
        assert mgr.is_all_ok("defaultspack")

    def test_install_nonexistent_pack(self):
        mgr = SetupPackManager()
        result = mgr.install_pack("nonexistent")
        assert not result.success

    def test_revoke_pack(self):
        mgr = SetupPackManager()
        mgr.install_pack("defaultspack")
        result = mgr.revoke_pack("defaultspack")
        assert result.success
        assert not mgr.is_all_ok("defaultspack")

    def test_reset_pack(self):
        mgr = SetupPackManager()
        mgr.install_pack("defaultspack")
        result = mgr.reset_pack("defaultspack")
        assert result.success
        assert mgr.is_all_ok("defaultspack")

    def test_audit_log(self):
        mgr = SetupPackManager()
        mgr.install_pack("defaultspack")
        log = mgr.get_audit_log()
        assert len(log) >= 1
        assert log[0]["action"] == "install"
