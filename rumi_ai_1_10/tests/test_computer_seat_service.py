"""Tests for ComputerSeatService – observe/click/type_text with mock drivers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer import (
    ComputerSeatService,
    DriverRegistry,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.base import (
    ComputerDriver,
)


class MockDriver(ComputerDriver):
    def __init__(self, name_: str = "mock", succeed: bool = True):
        self._name = name_
        self._succeed = succeed

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(can_semantic_action=True)

    def observe(self, target):
        return ObserveResult(platform="darwin", ax_tree={"mock": True})

    def click(self, target, x=0, y=0, button="left"):
        return ActionResult(action="click", driver=self._name, executed=self._succeed)

    def type_text(self, target, text=""):
        return ActionResult(action="type_text", driver=self._name, executed=self._succeed)

    def key(self, target, key_combo=""):
        return ActionResult(action="key", driver=self._name, executed=self._succeed)

    def scroll(self, target, x=0, y=0, direction="down", clicks=3):
        return ActionResult(action="scroll", driver=self._name, executed=self._succeed)

    def semantic_action(self, target, intent="", element_or_point=None):
        return ActionResult(action="semantic_action", driver=self._name, executed=self._succeed)

    def is_available(self) -> bool:
        return True


class BackgroundTypeDriver(MockDriver):
    def __init__(self, name_: str = "background", *, physical: bool = False):
        super().__init__(name_, succeed=True)
        self._physical = physical
        self.called = False

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_background_type=not self._physical,
            can_parallel_user_work=not self._physical,
            can_foreground_action=self._physical,
        )

    def type_text(self, target, text=""):
        self.called = True
        return ActionResult(
            action="type_text",
            driver=self._name,
            executed=True,
            can_parallel_user_work=not self._physical,
            uses_physical_input=self._physical,
        )


class BackgroundKeyDriver(MockDriver):
    def __init__(self, name_: str):
        super().__init__(name_, succeed=True)
        self.called = False

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_background_key=True,
            can_parallel_user_work=True,
            can_foreground_action=False,
        )

    def key(self, target, key_combo=""):
        self.called = True
        return ActionResult(
            action="key",
            driver=self._name,
            executed=True,
            confidence="experimental" if self._name == "mac_cgevent_pid" else "best_effort",
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
        )


def _make_service(drivers):
    reg = DriverRegistry()
    for d in drivers:
        reg.register(d)
    svc = ComputerSeatService(reg)
    svc._platform = "test"  # Use generic platform so all registered drivers are in chain
    return svc


def test_observe_success():
    svc = _make_service([MockDriver("mock1")])
    result = svc.observe({"app": "Test"})
    assert result["ax_tree"] == {"mock": True}


def test_click_success_not_fallback():
    svc = _make_service([MockDriver("mock1")])
    result = svc.click({"app": "Test"}, x=10, y=20)
    assert result["executed"] is True
    assert result["is_fallback"] is False


def test_click_fallback_to_next_driver():
    d1 = MockDriver("fail_driver", succeed=False)
    d2 = MockDriver("ok_driver", succeed=True)
    svc = _make_service([d1, d2])
    result = svc.click({"app": "Test"})
    # d1 returns executed=False, so chain tries d2
    assert result["executed"] is True
    assert result["driver"] == "ok_driver"


def test_type_text_success():
    svc = _make_service([MockDriver("mock1")])
    result = svc.type_text({"app": "Test"}, text="hello")
    assert result["executed"] is True


def test_background_action_skips_foreground_only_driver():
    foreground = BackgroundTypeDriver("mac_swift_host", physical=True)
    background = BackgroundTypeDriver("mac_cgevent_pid", physical=False)
    svc = _make_service([foreground, background])

    result = svc.background_action("type_text", {"app": "Test"}, {"text": "hello"})

    assert result["executed"] is True
    assert result["driver"] == "mac_cgevent_pid"
    assert foreground.called is False
    assert background.called is True


@pytest.mark.parametrize("driver_name", ["mac_cgevent_pid", "windows_postmessage"])
def test_post_only_transports_are_explicit_background_only(driver_name):
    driver = BackgroundKeyDriver(driver_name)
    svc = _make_service([driver])

    normal = svc.key({"app": "Unknown", "pid": 123}, key_combo="return")
    assert normal["executed"] is False
    assert driver.called is False

    background = svc.background_action("key", {"app": "Unknown", "pid": 123}, {"key_combo": "return"})

    assert background["executed"] is True
    assert background["driver"] == driver_name
    assert driver.called is True

    driver.called = False
    verified = svc.background_action(
        "key",
        {"app": "Unknown", "pid": 123},
        {"key_combo": "return"},
        verified_only=True,
    )

    assert verified["executed"] is False
    assert driver.called is False


def test_mac_accessibility_skips_ax_set_value_for_vivaldi():
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.mac_accessibility import (
        MacAccessibilityDriver,
    )

    driver = MacAccessibilityDriver()
    result = driver.type_text(
        ComputerTarget(app="Vivaldi", pid=1234, bundle_id="com.vivaldi.Vivaldi"),
        text="hello",
    )

    assert result.executed is False
    assert result.uses_physical_input is False
    assert "Skipping AXSetValue" in result.notes[0]


def test_mac_accessibility_chromium_detection_uses_exact_names_and_bundles():
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.mac_accessibility import (
        MacAccessibilityDriver,
    )

    positives = [
        ComputerTarget(app="Vivaldi", bundle_id="com.vivaldi.Vivaldi"),
        ComputerTarget(app="Google Chrome", bundle_id="com.google.Chrome"),
        ComputerTarget(app="Microsoft Edge", bundle_id="com.microsoft.edgemac"),
        ComputerTarget(app="Arc", bundle_id="company.thebrowser.Browser"),
    ]
    negatives = [
        ComputerTarget(app="Archive Utility", bundle_id="com.apple.archiveutility"),
        ComputerTarget(app="Ledger Live", bundle_id="com.ledger.live"),
    ]

    assert all(MacAccessibilityDriver._target_avoids_ax_set_value(target) for target in positives)
    assert not any(MacAccessibilityDriver._target_avoids_ax_set_value(target) for target in negatives)


def test_macos_cgevent_keycodes_and_modifier_validation():
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.mac import cgevent

    expected_f_keys = {
        "f1": 122,
        "f2": 120,
        "f3": 99,
        "f4": 118,
        "f5": 96,
        "f6": 97,
        "f7": 98,
        "f8": 100,
        "f9": 101,
        "f10": 109,
        "f11": 103,
        "f12": 111,
        "f13": 105,
        "f14": 107,
        "f15": 113,
        "f16": 106,
        "f17": 64,
        "f18": 79,
        "f19": 80,
        "f20": 90,
    }
    for key, code in expected_f_keys.items():
        assert cgevent._key_code(key) == code
    assert cgevent._key_code("left") == 123
    assert cgevent._key_code("right") == 124
    assert cgevent._key_code("down") == 125
    assert cgevent._key_code("up") == 126
    assert cgevent._key_combo_parts("cmd+ctrl+option+shift+delete")[0] == 51
    assert cgevent._key_combo_parts("fn+delete") == (None, 0)
    assert cgevent._key_combo_parts("typo+delete") == (None, 0)


def test_audit_logger_called():
    from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.audit import AuditLogger

    logger = AuditLogger(log_path="/dev/null")
    logger.record = MagicMock(return_value=None)
    reg = DriverRegistry()
    reg.register(MockDriver("mock1"))
    svc = ComputerSeatService(reg, audit_logger=logger)
    svc._platform = "darwin"
    svc.click({"app": "Test"})
    assert logger.record.called
