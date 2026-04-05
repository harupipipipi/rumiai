"""Tests for module_state.py - Module lifecycle state machine."""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ecosystem.defaultspack.module_state import (
    ModuleStateManager, ModuleStatus, ModuleHealth,
)


class TestModuleHealth:
    def test_initial_state(self):
        h = ModuleHealth(module_id="test")
        assert h.status == ModuleStatus.DISABLED
        assert h.error_count == 0
        assert h.consecutive_failures == 0

    def test_record_error(self):
        h = ModuleHealth(module_id="test")
        h.record_error(ValueError("test error"))
        assert h.error_count == 1
        assert h.consecutive_failures == 1
        assert h.last_error is not None
        assert h.last_error.error_type == "ValueError"

    def test_record_success_resets_consecutive(self):
        h = ModuleHealth(module_id="test")
        h.record_error(ValueError("e1"))
        h.record_error(ValueError("e2"))
        assert h.consecutive_failures == 2
        h.record_success()
        assert h.consecutive_failures == 0
        assert h.error_count == 2  # total doesn't reset

    def test_should_auto_disable(self):
        h = ModuleHealth(module_id="test", max_consecutive_failures=3)
        for i in range(2):
            h.record_error(ValueError(f"e{i}"))
        assert not h.should_auto_disable()
        h.record_error(ValueError("e3"))
        assert h.should_auto_disable()

    def test_to_dict(self):
        h = ModuleHealth(module_id="test")
        d = h.to_dict()
        assert d["module_id"] == "test"
        assert d["status"] == "disabled"


class TestModuleStateManager:
    def test_register_module(self):
        mgr = ModuleStateManager()
        h = mgr.register_module("mod1")
        assert h.module_id == "mod1"
        assert h.status == ModuleStatus.DISABLED

    def test_enable_disable(self):
        mgr = ModuleStateManager()
        mgr.register_module("mod1")
        assert mgr.enable("mod1")
        assert mgr.get_status("mod1") == ModuleStatus.ENABLED
        assert mgr.is_enabled("mod1")
        assert mgr.disable("mod1")
        assert mgr.get_status("mod1") == ModuleStatus.DISABLED
        assert not mgr.is_enabled("mod1")

    def test_invalid_transition(self):
        mgr = ModuleStateManager()
        mgr.register_module("mod1")
        # DISABLED -> DEGRADED is not valid
        assert not mgr.transition("mod1", ModuleStatus.DEGRADED)

    def test_auto_disable_on_errors(self):
        events = []
        def cb(name, payload):
            events.append(name)
        mgr = ModuleStateManager(event_callback=cb)
        mgr.register_module("mod1", ModuleStatus.DISABLED, max_failures=2)
        mgr.enable("mod1")
        mgr.record_error("mod1", ValueError("e1"))
        assert mgr.get_status("mod1") == ModuleStatus.DEGRADED
        mgr.record_error("mod1", ValueError("e2"))
        assert mgr.get_status("mod1") == ModuleStatus.ERROR_DISABLED
        assert "module.error_disabled" in events

    def test_recovery_on_success(self):
        mgr = ModuleStateManager()
        mgr.register_module("mod1")
        mgr.enable("mod1")
        mgr.record_error("mod1", ValueError("e1"))
        assert mgr.get_status("mod1") == ModuleStatus.DEGRADED
        mgr.record_success("mod1")
        assert mgr.get_status("mod1") == ModuleStatus.ENABLED

    def test_retry_after_error_disabled(self):
        mgr = ModuleStateManager()
        mgr.register_module("mod1", max_failures=1, cooldown_seconds=0)
        mgr.enable("mod1")
        mgr.record_error("mod1", ValueError("e1"))
        assert mgr.get_status("mod1") == ModuleStatus.ERROR_DISABLED
        assert mgr.retry("mod1")
        assert mgr.get_status("mod1") == ModuleStatus.ENABLED

    def test_list_by_status(self):
        mgr = ModuleStateManager()
        mgr.register_module("mod1")
        mgr.register_module("mod2")
        mgr.enable("mod1")
        assert "mod1" in mgr.list_by_status(ModuleStatus.ENABLED)
        assert "mod2" in mgr.list_by_status(ModuleStatus.DISABLED)

    def test_event_callback(self):
        events = []
        mgr = ModuleStateManager(event_callback=lambda n, p: events.append((n, p)))
        mgr.register_module("mod1")
        mgr.enable("mod1")
        assert len(events) == 1
        assert events[0][0] == "module.enabled"

    def test_list_all(self):
        mgr = ModuleStateManager()
        mgr.register_module("mod1")
        mgr.register_module("mod2")
        catalog = mgr.list_all()
        assert "mod1" in catalog
        assert "mod2" in catalog
