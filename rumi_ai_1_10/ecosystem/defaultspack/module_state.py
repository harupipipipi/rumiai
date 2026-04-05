"""
module_state.py - Module lifecycle state machine.

Every module in defaultspack has one of:
  enabled, disabled, degraded, error_disabled, experimental

Transitions are governed by explicit actions and automatic error
detection (failure containment / auto-off).
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModuleStatus(str, enum.Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    ERROR_DISABLED = "error_disabled"
    EXPERIMENTAL = "experimental"


# Valid transitions map
_TRANSITIONS: Dict[ModuleStatus, set] = {
    ModuleStatus.ENABLED: {
        ModuleStatus.DISABLED,
        ModuleStatus.DEGRADED,
        ModuleStatus.ERROR_DISABLED,
    },
    ModuleStatus.DISABLED: {
        ModuleStatus.ENABLED,
        ModuleStatus.EXPERIMENTAL,
    },
    ModuleStatus.DEGRADED: {
        ModuleStatus.ENABLED,
        ModuleStatus.ERROR_DISABLED,
        ModuleStatus.DISABLED,
    },
    ModuleStatus.ERROR_DISABLED: {
        ModuleStatus.DISABLED,
        ModuleStatus.ENABLED,  # manual retry
    },
    ModuleStatus.EXPERIMENTAL: {
        ModuleStatus.ENABLED,
        ModuleStatus.DISABLED,
        ModuleStatus.ERROR_DISABLED,
    },
}


@dataclass
class ErrorRecord:
    """Single error occurrence."""
    timestamp: float
    error_type: str
    message: str
    traceback: Optional[str] = None


@dataclass
class ModuleHealth:
    """Health tracking for a single module."""
    module_id: str
    status: ModuleStatus = ModuleStatus.DISABLED
    error_count: int = 0
    consecutive_failures: int = 0
    last_error: Optional[ErrorRecord] = None
    error_history: List[ErrorRecord] = field(default_factory=list)
    last_status_change: float = field(default_factory=time.time)
    cooldown_until: float = 0.0
    disable_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Thresholds
    max_consecutive_failures: int = 3
    cooldown_seconds: float = 60.0
    max_error_history: int = 50

    def record_error(self, error: Exception, tb: Optional[str] = None) -> None:
        record = ErrorRecord(
            timestamp=time.time(),
            error_type=type(error).__name__,
            message=str(error),
            traceback=tb,
        )
        self.error_count += 1
        self.consecutive_failures += 1
        self.last_error = record
        self.error_history.append(record)
        if len(self.error_history) > self.max_error_history:
            self.error_history = self.error_history[-self.max_error_history:]

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def should_auto_disable(self) -> bool:
        return self.consecutive_failures >= self.max_consecutive_failures

    def is_in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def start_cooldown(self) -> None:
        self.cooldown_until = time.time() + self.cooldown_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "status": self.status.value,
            "error_count": self.error_count,
            "consecutive_failures": self.consecutive_failures,
            "last_error": {
                "type": self.last_error.error_type,
                "message": self.last_error.message,
                "timestamp": self.last_error.timestamp,
            } if self.last_error else None,
            "last_status_change": self.last_status_change,
            "cooldown_until": self.cooldown_until,
            "disable_reason": self.disable_reason,
        }


class ModuleStateManager:
    """
    Central manager for all module health states.

    Thread-safe. Emits events via callback on state changes.
    Supports auto-disable on repeated failures, cooldown, manual retry.
    """

    def __init__(self, event_callback: Optional[Callable] = None):
        self._lock = threading.RLock()
        self._modules: Dict[str, ModuleHealth] = {}
        self._event_callback = event_callback

    def register_module(
        self,
        module_id: str,
        initial_status: ModuleStatus = ModuleStatus.DISABLED,
        max_failures: int = 3,
        cooldown_seconds: float = 60.0,
    ) -> ModuleHealth:
        with self._lock:
            if module_id in self._modules:
                return self._modules[module_id]
            health = ModuleHealth(
                module_id=module_id,
                status=initial_status,
                max_consecutive_failures=max_failures,
                cooldown_seconds=cooldown_seconds,
            )
            self._modules[module_id] = health
            return health

    def get_health(self, module_id: str) -> Optional[ModuleHealth]:
        with self._lock:
            return self._modules.get(module_id)

    def get_status(self, module_id: str) -> Optional[ModuleStatus]:
        with self._lock:
            h = self._modules.get(module_id)
            return h.status if h else None

    def is_enabled(self, module_id: str) -> bool:
        s = self.get_status(module_id)
        return s in (ModuleStatus.ENABLED, ModuleStatus.DEGRADED, ModuleStatus.EXPERIMENTAL)

    def transition(
        self,
        module_id: str,
        new_status: ModuleStatus,
        reason: str = "",
    ) -> bool:
        with self._lock:
            health = self._modules.get(module_id)
            if health is None:
                logger.warning("Module '%s' not registered", module_id)
                return False

            old = health.status
            if new_status not in _TRANSITIONS.get(old, set()):
                logger.warning(
                    "Invalid transition for '%s': %s -> %s",
                    module_id, old.value, new_status.value,
                )
                return False

            health.status = new_status
            health.last_status_change = time.time()
            if reason:
                health.disable_reason = reason
            if new_status == ModuleStatus.ENABLED:
                health.consecutive_failures = 0
                health.disable_reason = ""

            logger.info(
                "Module '%s' transitioned: %s -> %s (reason=%s)",
                module_id, old.value, new_status.value, reason,
            )
            self._emit_event(module_id, old, new_status, reason)
            return True

    def enable(self, module_id: str) -> bool:
        return self.transition(module_id, ModuleStatus.ENABLED, "manual enable")

    def disable(self, module_id: str, reason: str = "manual") -> bool:
        return self.transition(module_id, ModuleStatus.DISABLED, reason)

    def record_error(
        self,
        module_id: str,
        error: Exception,
        tb: Optional[str] = None,
    ) -> ModuleStatus:
        with self._lock:
            health = self._modules.get(module_id)
            if health is None:
                logger.warning("Module '%s' not registered", module_id)
                return ModuleStatus.DISABLED

            health.record_error(error, tb)

            if health.should_auto_disable():
                health.start_cooldown()
                self.transition(
                    module_id,
                    ModuleStatus.ERROR_DISABLED,
                    f"Auto-disabled after {health.consecutive_failures} consecutive failures: {error}",
                )
            elif health.status == ModuleStatus.ENABLED:
                self.transition(
                    module_id,
                    ModuleStatus.DEGRADED,
                    f"Degraded due to error: {error}",
                )
            return health.status

    def record_success(self, module_id: str) -> None:
        with self._lock:
            health = self._modules.get(module_id)
            if health is None:
                return
            health.record_success()
            if health.status == ModuleStatus.DEGRADED:
                self.transition(module_id, ModuleStatus.ENABLED, "recovered")

    def retry(self, module_id: str) -> bool:
        with self._lock:
            health = self._modules.get(module_id)
            if health is None:
                return False
            if health.is_in_cooldown():
                logger.info("Module '%s' in cooldown, retry denied", module_id)
                return False
            if health.status == ModuleStatus.ERROR_DISABLED:
                return self.transition(module_id, ModuleStatus.ENABLED, "manual retry")
            return False

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {mid: h.to_dict() for mid, h in self._modules.items()}

    def list_by_status(self, status: ModuleStatus) -> List[str]:
        with self._lock:
            return [mid for mid, h in self._modules.items() if h.status == status]

    def _emit_event(
        self,
        module_id: str,
        old_status: ModuleStatus,
        new_status: ModuleStatus,
        reason: str,
    ) -> None:
        if self._event_callback is None:
            return
        event_type_map = {
            ModuleStatus.ENABLED: "module.enabled",
            ModuleStatus.DISABLED: "module.disabled",
            ModuleStatus.DEGRADED: "module.degraded",
            ModuleStatus.ERROR_DISABLED: "module.error_disabled",
        }
        if old_status in (ModuleStatus.DEGRADED, ModuleStatus.ERROR_DISABLED) and \
                new_status == ModuleStatus.ENABLED:
            event_name = "module.recovered"
        else:
            event_name = event_type_map.get(new_status, f"module.{new_status.value}")

        try:
            self._event_callback(event_name, {
                "module_id": module_id,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "reason": reason,
                "timestamp": time.time(),
            })
        except Exception as exc:
            logger.warning("Event callback error: %s", exc)
