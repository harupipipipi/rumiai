"""Safe binding handler resolution for Capability Graph compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .interface_registry import InterfaceRegistry


BindingHandler = Callable[..., Any]


@dataclass(frozen=True)
class BindingHandlerResolution:
    handler_id: str
    handler: Optional[BindingHandler]
    diagnostics: List[Dict[str, Any]]

    @property
    def ok(self) -> bool:
        return self.handler is not None and not any(
            item.get("level") == "error" for item in self.diagnostics
        )


class BindingHandlerResolver:
    """Resolve binding handlers from explicit registries, never from imports."""

    def __init__(self, *, interface_registry: Optional[InterfaceRegistry] = None) -> None:
        self.interface_registry = interface_registry

    def resolve(self, handler_id: str) -> BindingHandlerResolution:
        diagnostics: List[Dict[str, Any]] = []
        if not isinstance(handler_id, str) or not handler_id:
            return BindingHandlerResolution(
                handler_id=str(handler_id),
                handler=None,
                diagnostics=[
                    _diagnostic(
                        "error",
                        "invalid_binding_handler_id",
                        "Binding handler id must be a non-empty string",
                        handler_id=handler_id,
                    )
                ],
            )
        if self._looks_like_import_path(handler_id):
            return BindingHandlerResolution(
                handler_id=handler_id,
                handler=None,
                diagnostics=[
                    _diagnostic(
                        "error",
                        "binding_handler_import_path_rejected",
                        "Binding handlers must be registered explicitly, not imported by path",
                        handler_id=handler_id,
                    )
                ],
            )
        if self.interface_registry is None:
            return BindingHandlerResolution(
                handler_id=handler_id,
                handler=None,
                diagnostics=[
                    _diagnostic(
                        "error",
                        "binding_handler_registry_unavailable",
                        "No InterfaceRegistry is available for binding handler resolution",
                        handler_id=handler_id,
                    )
                ],
            )

        handler = self.interface_registry.get(handler_id)
        if handler is None and handler_id.startswith("ir:"):
            handler = self.interface_registry.get(handler_id[3:])
        if handler is None:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "binding_handler_not_found",
                    f"Binding handler '{handler_id}' was not found",
                    handler_id=handler_id,
                )
            )
        elif not callable(handler):
            diagnostics.append(
                _diagnostic(
                    "error",
                    "binding_handler_not_callable",
                    f"Binding handler '{handler_id}' is not callable",
                    handler_id=handler_id,
                )
            )
            handler = None

        return BindingHandlerResolution(
            handler_id=handler_id,
            handler=handler,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _looks_like_import_path(handler_id: str) -> bool:
        if ":" in handler_id:
            return False
        if "/" in handler_id or "\\" in handler_id:
            return True
        parts = handler_id.rsplit(".", 1)
        return len(parts) == 2 and all(parts)


def _diagnostic(
    level: str,
    code: str,
    message: str,
    **meta: Any,
) -> Dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        **meta,
    }
