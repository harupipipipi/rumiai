"""Driver registry for ComputerSeat.

Manages registration and selection of drivers by platform and capability.
Drivers are tried in a defined priority order per platform.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .drivers.base import ComputerDriver

# Preferred driver order per platform (highest priority first)
MAC_DRIVER_ORDER: list[str] = [
    "browser_cdp",
    "browser_companion",
    "mac_accessibility",
    "mac_apple_events",
    "mac_cgevent_pid",
    "mac_screen_capture",
    "mac_foreground",
]

WINDOWS_DRIVER_ORDER: list[str] = [
    "browser_cdp",
    "browser_companion",
    "windows_uia",
    "windows_postmessage",
    "windows_foreground",
    "local_visible",
]


class DriverRegistry:
    """Registry for ComputerSeat drivers.

    Drivers are registered by name and selected based on platform
    and availability.
    """

    def __init__(self) -> None:
        self._drivers: dict[str, "ComputerDriver"] = {}

    def register(self, driver: "ComputerDriver") -> None:
        """Register a driver instance.

        Args:
            driver: A ComputerDriver instance to register.
        """
        self._drivers[driver.name] = driver

    def get_driver(self, name: str) -> "ComputerDriver | None":
        """Get a specific driver by name.

        Args:
            name: The driver name.

        Returns:
            The driver instance or None if not found.
        """
        return self._drivers.get(name)

    def get_driver_chain(self, platform: str) -> list["ComputerDriver"]:
        """Get the ordered list of available drivers for a platform.

        Drivers are returned in priority order. Only drivers that report
        themselves as available are included.

        Args:
            platform: The platform identifier ("darwin" or "win32").

        Returns:
            Ordered list of available drivers for the platform.
        """
        if platform == "darwin":
            order = MAC_DRIVER_ORDER
        elif platform == "win32":
            order = WINDOWS_DRIVER_ORDER
        else:
            order = list(self._drivers.keys())

        chain: list["ComputerDriver"] = []
        for name in order:
            driver = self._drivers.get(name)
            if driver is not None and driver.is_available():
                chain.append(driver)
        return chain

    @property
    def all_drivers(self) -> dict[str, "ComputerDriver"]:
        """Return all registered drivers."""
        return dict(self._drivers)
