"""ComputerSeat drivers package.

Each driver implements the ComputerDriver abstract base class and provides
a specific strategy for interacting with desktop applications.
"""

from .base import ComputerDriver
from .local_visible import LocalVisibleDesktopDriver
from .browser_cdp import BrowserCDPDriver
from .mac_accessibility import MacAccessibilityDriver
from .mac_apple_events import MacAppleEventsDriver
from .mac_cgevent_pid import MacCGEventPidDriver
from .mac_foreground import MacForegroundFallbackDriver
from .mac_screen_capture import MacScreenCaptureDriver
from .mac_swift_host import MacSwiftHostDriver
from .linux_visible import LinuxVisibleDesktopDriver
from .linux_x11_virtual import LinuxX11VirtualDriver

__all__ = [
    "ComputerDriver",
    "LocalVisibleDesktopDriver",
    "BrowserCDPDriver",
    "MacAccessibilityDriver",
    "MacAppleEventsDriver",
    "MacCGEventPidDriver",
    "MacForegroundFallbackDriver",
    "MacScreenCaptureDriver",
    "MacSwiftHostDriver",
    "LinuxVisibleDesktopDriver",
    "LinuxX11VirtualDriver",
]
