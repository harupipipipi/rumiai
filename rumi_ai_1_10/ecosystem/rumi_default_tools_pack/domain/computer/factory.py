"""Factory functions for creating a fully-configured ComputerSeatService.

These replace the pattern of ``ComputerSeatService(DriverRegistry())`` with
a registry that has all platform-appropriate drivers pre-registered.
"""

from __future__ import annotations

import sys

from .audit import AuditLogger
from .host_adapter import ComputerSeatHostAdapter
from .platform_adapters import adapter_for_sys_platform
from .registry import DriverRegistry
from .service import ComputerSeatService
from .tool_service import ComputerToolService


def create_default_driver_registry() -> DriverRegistry:
    """Create a DriverRegistry with all platform-appropriate drivers registered."""
    registry = DriverRegistry()

    from .drivers.browser_cdp import BrowserCDPDriver

    registry.register(BrowserCDPDriver())
    adapter_for_sys_platform(sys.platform).register_drivers(registry)

    # Always register local_visible as a universal fallback
    from .drivers.local_visible import LocalVisibleDesktopDriver

    registry.register(LocalVisibleDesktopDriver())

    return registry


def create_default_computer_seat_service(
    audit_logger: AuditLogger | None = None,
) -> ComputerSeatService:
    """Create a ComputerSeatService with all default drivers registered."""
    registry = create_default_driver_registry()
    return ComputerSeatService(registry, audit_logger=audit_logger)


def create_default_computer_host(
    audit_logger: AuditLogger | None = None,
) -> ComputerSeatHostAdapter:
    """Create the model-agnostic host adapter over the default native drivers."""
    return ComputerSeatHostAdapter(create_default_computer_seat_service(audit_logger=audit_logger))


def create_default_computer_tool_service(
    audit_logger: AuditLogger | None = None,
) -> ComputerToolService:
    """Create the pack-owned service over the canonical native host boundary."""
    return ComputerToolService(create_default_computer_host(audit_logger=audit_logger))
