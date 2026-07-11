"""ComputerSeat architecture – domain layer.

This package provides the abstraction for controlling desktop applications
through multiple driver strategies (accessibility APIs, CGEvent injection,
Apple Events, foreground fallback, etc.) with automatic fallback chains,
permission checks, and audit logging.
"""

from .models import (
    ActionResult,
    AXElement,
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)
from .service import ComputerSeatService
from .registry import DriverRegistry
from .audit import AuditLogger
from .permissions import requires_approval, risk_level
from .factory import (
    create_default_computer_host,
    create_default_computer_seat_service,
    create_default_computer_tool_service,
    create_default_driver_registry,
)
from .host_adapter import ComputerSeatHostAdapter
from .tool_service import ComputerToolService

__all__ = [
    "ActionResult",
    "AXElement",
    "ComputerCapabilities",
    "ComputerSeatService",
    "ComputerSeatHostAdapter",
    "ComputerToolService",
    "ComputerTarget",
    "DriverRegistry",
    "AuditLogger",
    "ObserveResult",
    "requires_approval",
    "risk_level",
    "create_default_driver_registry",
    "create_default_computer_host",
    "create_default_computer_seat_service",
    "create_default_computer_tool_service",
]
