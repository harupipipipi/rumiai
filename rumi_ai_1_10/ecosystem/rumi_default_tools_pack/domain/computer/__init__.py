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
from .factory import create_default_driver_registry, create_default_computer_seat_service

__all__ = [
    "ActionResult",
    "AXElement",
    "ComputerCapabilities",
    "ComputerSeatService",
    "ComputerTarget",
    "DriverRegistry",
    "AuditLogger",
    "ObserveResult",
    "requires_approval",
    "risk_level",
    "create_default_driver_registry",
    "create_default_computer_seat_service",
]
