"""Typed desktop observe/control requests for the Viewer host broker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


OBSERVE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "desktop.state",
        "desktop.applications.list",
        "desktop.windows.list",
        "desktop.accessibility.snapshot",
        "desktop.capture.frame",
    }
)
CONTROL_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "desktop.application.select",
        "desktop.application.activate",
        "desktop.window.select",
        "desktop.pointer.move",
        "desktop.pointer.click",
        "desktop.pointer.drag",
        "desktop.keyboard.type",
        "desktop.keyboard.key",
        "desktop.scroll",
        "desktop.accessibility.action",
    }
)
_FORBIDDEN_ARGUMENTS: Final[frozenset[str]] = frozenset(
    {"approved", "approval_token", "authority_token", "viewer_host_approved", "yolo_mode"}
)


@dataclass(frozen=True)
class DesktopHostService:
    """Build desktop HostIntents while retaining Authority outside the pack."""

    access: str
    operations: frozenset[str]

    def invoke(
        self,
        operation: str,
        arguments: dict[str, Any] | None = None,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a caller-bound HostIntent or a typed denial."""

        normalized_operation = str(operation or "").strip()
        if normalized_operation not in self.operations:
            return {
                "status": "denied",
                "success": False,
                "error_type": "operation_outside_desktop_contract",
                "operation": normalized_operation,
                "access": self.access,
            }
        normalized_arguments = dict(arguments or {})
        forbidden = sorted(_FORBIDDEN_ARGUMENTS.intersection(normalized_arguments))
        if forbidden:
            return {
                "status": "denied",
                "success": False,
                "error_type": "client_authority_material_forbidden",
                "forbidden_arguments": forbidden,
            }
        caller_context = dict(context or {})
        caller_pack_id = str(
            caller_context.get("_contract_consumer_pack_id")
            or caller_context.get("caller_pack_id")
            or ""
        ).strip()
        caller_function_id = str(
            caller_context.get("_contract_consumer_function_id")
            or caller_context.get("caller_function_id")
            or ""
        ).strip()
        if not caller_pack_id or not caller_function_id:
            return {
                "status": "denied",
                "success": False,
                "error_type": "missing_contract_caller_identity",
            }
        return {
            "type": "host_intent",
            "version": 1,
            "operation": normalized_operation,
            "args": normalized_arguments,
            "stream": {"enabled": False},
            "reason": str(caller_context.get("reason") or "").strip(),
            "caller": {
                "pack_id": caller_pack_id,
                "function_id": caller_function_id,
            },
            "conversation_id": str(
                caller_context.get("conversation_id") or ""
            ).strip(),
            "host_function_id": f"desktop.{self.access}",
        }


def create_desktop_observer(_context: dict[str, Any] | None = None) -> DesktopHostService:
    """Create the desktop observation provider."""

    return DesktopHostService(access="observe", operations=OBSERVE_OPERATIONS)


def create_desktop_control(_context: dict[str, Any] | None = None) -> DesktopHostService:
    """Create the desktop control provider."""

    return DesktopHostService(access="control", operations=CONTROL_OPERATIONS)
