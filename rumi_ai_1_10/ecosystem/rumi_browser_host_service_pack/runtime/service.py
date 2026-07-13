"""Typed browser observe/control requests for the Viewer host broker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


OBSERVE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "browser.session.get",
        "browser.sessions.list",
        "browser.profiles.list",
        "browser.tabs.list",
        "browser.cookies.list",
        "browser.capture.page",
        "browser.downloads.list",
    }
)
CONTROL_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "browser.session.create",
        "browser.session.close",
        "browser.profile.create",
        "browser.profile.set_active",
        "browser.profile.delete",
        "browser.profile.clear_cache",
        "browser.profile.clear_cookies",
        "browser.tab.select",
        "browser.navigate",
        "browser.cookies.import",
        "browser.cookies.delete",
        "browser.download.collect",
    }
)
_FORBIDDEN_ARGUMENTS: Final[frozenset[str]] = frozenset(
    {"approved", "approval_token", "authority_token", "yolo_mode"}
)


@dataclass(frozen=True)
class BrowserHostService:
    """Build fail-closed browser requests without executing host operations."""

    access: str
    operations: frozenset[str]

    def invoke(
        self,
        operation: str,
        arguments: dict[str, Any] | None = None,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a HostIntent accepted by the core Authority mediation path."""

        normalized_operation = str(operation or "").strip()
        if normalized_operation not in self.operations:
            return {
                "status": "denied",
                "success": False,
                "error_type": "operation_outside_browser_contract",
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
            "host_function_id": f"browser.{self.access}",
        }


def create_browser_observer(_context: dict[str, Any] | None = None) -> BrowserHostService:
    """Create the read-only browser observation contract provider."""

    return BrowserHostService(access="observe", operations=OBSERVE_OPERATIONS)


def create_browser_control(_context: dict[str, Any] | None = None) -> BrowserHostService:
    """Create the browser mutation contract provider."""

    return BrowserHostService(access="control", operations=CONTROL_OPERATIONS)
