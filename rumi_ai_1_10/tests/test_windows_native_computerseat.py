"""Opt-in native Windows probes for ComputerSeat helpers.

Run with:
    RUMI_RUN_WINDOWS_NATIVE_TESTS=1 pytest rumi_ai_1_10/tests/test_windows_native_computerseat.py
"""

from __future__ import annotations

import os
import sys

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.windows_postmessage import (
    WindowsPostMessageDriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.drivers.windows_uia import (
    WindowsUIADriver,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import ComputerTarget
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.windows.hwnd import (
    get_window_info,
    list_windows,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.windows.integrity import (
    describe_environment,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("RUMI_RUN_WINDOWS_NATIVE_TESTS") != "1",
    reason="native Windows tests require win32 and RUMI_RUN_WINDOWS_NATIVE_TESTS=1",
)


def test_native_window_enumeration_returns_normalized_records():
    windows = list_windows()
    assert isinstance(windows, list)
    if not windows:
        pytest.skip("No visible windows to inspect")
    first = windows[0]
    assert first["hwnd"]
    assert first["window_id"] == first["hwnd"]
    assert isinstance(first.get("title"), str)
    assert get_window_info(first["hwnd"]) is not None


def test_native_drivers_observe_visible_window_gracefully():
    windows = list_windows()
    if not windows:
        pytest.skip("No visible windows to inspect")
    target = ComputerTarget(window_id=windows[0]["hwnd"])

    uia_result = WindowsUIADriver().observe(target)
    post_result = WindowsPostMessageDriver().observe(target)

    assert uia_result.platform == "win32"
    assert post_result.platform == "win32"
    assert post_result.target_window.get("hwnd") == windows[0]["hwnd"]


def test_native_integrity_environment_reports_windows():
    env = describe_environment()
    assert env["is_windows"] is True
    assert env["user32"] is True
