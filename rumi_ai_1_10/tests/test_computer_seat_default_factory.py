"""Tests for create_default_driver_registry and create_default_computer_seat_service."""

from __future__ import annotations

import sys

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.factory import (
    create_default_driver_registry,
    create_default_computer_seat_service,
    create_default_computer_tool_service,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.registry import DriverRegistry
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.service import (
    ComputerSeatService,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.tool_service import (
    ComputerToolService,
)


def test_factory_returns_registry():
    reg = create_default_driver_registry()
    assert isinstance(reg, DriverRegistry)


def test_factory_registry_not_empty():
    reg = create_default_driver_registry()
    assert len(reg.all_drivers) > 0


@pytest.mark.skipif(sys.platform != "darwin", reason="Mac-only")
def test_factory_registers_mac_drivers():
    reg = create_default_driver_registry()
    names = set(reg.all_drivers.keys())
    assert "mac_accessibility" in names
    assert "mac_apple_events" in names
    assert "mac_cgevent_pid" in names
    assert "mac_foreground" in names
    assert "mac_screen_capture" in names


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_factory_registers_windows_drivers():
    reg = create_default_driver_registry()
    names = set(reg.all_drivers.keys())
    assert "windows_uia" in names
    assert "windows_postmessage" in names


def test_factory_always_registers_local_visible():
    reg = create_default_driver_registry()
    assert "local_visible" in reg.all_drivers


def test_create_default_service():
    svc = create_default_computer_seat_service()
    assert isinstance(svc, ComputerSeatService)


def test_service_doctor_has_drivers():
    svc = create_default_computer_seat_service()
    result = svc.doctor()
    assert "platform" in result
    assert "driver_chain_order" in result


def test_create_default_tool_service_uses_host_boundary():
    svc = create_default_computer_tool_service()
    assert isinstance(svc, ComputerToolService)
    assert svc.doctor()["driver_chain_order"]
