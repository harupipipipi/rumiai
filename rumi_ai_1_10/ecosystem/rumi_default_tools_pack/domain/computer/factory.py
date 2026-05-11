"""Factory functions for creating a fully-configured ComputerSeatService.

These replace the pattern of ``ComputerSeatService(DriverRegistry())`` with
a registry that has all platform-appropriate drivers pre-registered.
"""

from __future__ import annotations

import sys

from .audit import AuditLogger
from .registry import DriverRegistry
from .service import ComputerSeatService


def create_default_driver_registry() -> DriverRegistry:
    """Create a DriverRegistry with all platform-appropriate drivers registered."""
    registry = DriverRegistry()

    if sys.platform == "darwin":
        from .drivers.mac_accessibility import MacAccessibilityDriver
        from .drivers.mac_apple_events import MacAppleEventsDriver
        from .drivers.mac_cgevent_pid import MacCGEventPidDriver
        from .drivers.mac_screen_capture import MacScreenCaptureDriver
        from .drivers.mac_foreground import MacForegroundFallbackDriver

        registry.register(MacAccessibilityDriver())
        registry.register(MacAppleEventsDriver())
        registry.register(MacCGEventPidDriver())
        registry.register(MacScreenCaptureDriver())
        registry.register(MacForegroundFallbackDriver())
    elif sys.platform == "win32":
        from .drivers.windows_uia import WindowsUIADriver
        from .drivers.windows_postmessage import WindowsPostMessageDriver

        registry.register(WindowsUIADriver())
        registry.register(WindowsPostMessageDriver())

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
