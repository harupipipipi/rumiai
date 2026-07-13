"""Separate clipboard read and write requests for the Viewer host broker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


_MAX_TEXT_BYTES: Final[int] = 1_048_576
_FORBIDDEN_ARGUMENTS: Final[frozenset[str]] = frozenset(
    {"approved", "approval_token", "authority_token", "viewer_host_approved", "yolo_mode"}
)


@dataclass(frozen=True)
class ClipboardHostService:
    """Build one clipboard HostIntent without directly reading or writing it."""

    access: str
    operation: str

    def invoke(
        self,
        arguments: dict[str, Any] | None = None,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a caller-bound clipboard HostIntent or typed denial."""

        normalized_arguments = dict(arguments or {})
        forbidden = sorted(_FORBIDDEN_ARGUMENTS.intersection(normalized_arguments))
        if forbidden:
            return {
                "status": "denied",
                "success": False,
                "error_type": "client_authority_material_forbidden",
                "forbidden_arguments": forbidden,
            }
        if self.access == "read" and normalized_arguments:
            return {
                "status": "denied",
                "success": False,
                "error_type": "clipboard_read_arguments_forbidden",
            }
        if self.access == "write":
            text = normalized_arguments.get("text")
            if not isinstance(text, str):
                return {
                    "status": "denied",
                    "success": False,
                    "error_type": "clipboard_text_required",
                }
            if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
                return {
                    "status": "denied",
                    "success": False,
                    "error_type": "clipboard_text_too_large",
                    "max_bytes": _MAX_TEXT_BYTES,
                }
            normalized_arguments = {"text": text, "format": "text/plain"}
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
            "operation": self.operation,
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
            "host_function_id": f"clipboard.{self.access}",
        }


def create_clipboard_reader(_context: dict[str, Any] | None = None) -> ClipboardHostService:
    """Create the clipboard read provider."""

    return ClipboardHostService(access="read", operation="host.clipboard.read")


def create_clipboard_writer(_context: dict[str, Any] | None = None) -> ClipboardHostService:
    """Create the clipboard write provider."""

    return ClipboardHostService(access="write", operation="host.clipboard.write")
