"""ComputerSeat drivers package.

Each driver implements the ComputerDriver abstract base class and provides
a specific strategy for interacting with desktop applications.
"""

from .base import ComputerDriver
from .local_visible import LocalVisibleDesktopDriver
from .mac_accessibility import MacAccessibilityDriver
from .mac_apple_events import MacAppleEventsDriver
from .mac_cgevent_pid import MacCGEventPidDriver
from .mac_foreground import MacForegroundFallbackDriver
from .mac_screen_capture import MacScreenCaptureDriver

__all__ = [
    "ComputerDriver",
    "LocalVisibleDesktopDriver",
    "MacAccessibilityDriver",
    "MacAppleEventsDriver",
    "MacCGEventPidDriver",
    "MacForegroundFallbackDriver",
    "MacScreenCaptureDriver",
]
