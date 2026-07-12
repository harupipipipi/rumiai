"""Platform-separated Computer Use driver registration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .registry import DriverRegistry


class ComputerUsePlatformAdapter(Protocol):
    platform_id: str
    display_name: str

    def register_drivers(self, registry: DriverRegistry) -> None:
        """Register platform-native drivers into ``registry``."""


@dataclass(frozen=True)
class MacComputerUseAdapter:
    platform_id: str = "darwin"
    display_name: str = "macOS Swift Computer Use"

    def register_drivers(self, registry: DriverRegistry) -> None:
        from .drivers.mac_accessibility import MacAccessibilityDriver
        from .drivers.mac_apple_events import MacAppleEventsDriver
        from .drivers.mac_cgevent_pid import MacCGEventPidDriver
        from .drivers.mac_foreground import MacForegroundFallbackDriver
        from .drivers.mac_screen_capture import MacScreenCaptureDriver
        from .drivers.mac_swift_host import MacSwiftHostDriver

        registry.register(MacSwiftHostDriver())
        registry.register(MacAccessibilityDriver())
        registry.register(MacAppleEventsDriver())
        registry.register(MacCGEventPidDriver())
        registry.register(MacScreenCaptureDriver())
        registry.register(MacForegroundFallbackDriver())


@dataclass(frozen=True)
class WindowsComputerUseAdapter:
    platform_id: str = "win32"
    display_name: str = "Windows Computer Use"

    def register_drivers(self, registry: DriverRegistry) -> None:
        from .drivers.windows_postmessage import WindowsPostMessageDriver
        from .drivers.windows_uia import WindowsUIADriver

        registry.register(WindowsUIADriver())
        registry.register(WindowsPostMessageDriver())


@dataclass(frozen=True)
class LinuxComputerUseAdapter:
    platform_id: str = "linux"
    display_name: str = "Linux Virtual/Visible Computer Use"

    def register_drivers(self, registry: DriverRegistry) -> None:
        from .drivers.linux_x11_virtual import LinuxX11VirtualDriver
        from .drivers.linux_visible import LinuxVisibleDesktopDriver

        registry.register(LinuxX11VirtualDriver())
        registry.register(LinuxVisibleDesktopDriver())


@dataclass(frozen=True)
class GenericComputerUseAdapter:
    platform_id: str = "generic"
    display_name: str = "Generic Visible Computer Use"

    def register_drivers(self, registry: DriverRegistry) -> None:
        return None


def adapter_for_sys_platform(platform_id: str) -> ComputerUsePlatformAdapter:
    normalized = str(platform_id or "").lower()
    if normalized == "darwin":
        return MacComputerUseAdapter()
    if normalized == "win32":
        return WindowsComputerUseAdapter()
    if normalized.startswith("linux"):
        return LinuxComputerUseAdapter()
    return GenericComputerUseAdapter(platform_id=normalized or "generic")
