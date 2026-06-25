from __future__ import annotations

from typing import Any, Callable

from blocks._common import error, ok
from domain.coding.sandbox_workspace import SandboxWorkspaceManager


def sandbox_manager(context: dict[str, Any] | None = None) -> SandboxWorkspaceManager:
    injected = (context or {}).get("sandbox_workspace_manager") if isinstance(context, dict) else None
    if isinstance(injected, SandboxWorkspaceManager):
        return injected
    return SandboxWorkspaceManager()


def run_sandbox_action(
    input_data: dict[str, Any] | None,
    context: dict[str, Any] | None,
    action: Callable[[SandboxWorkspaceManager, Any], dict[str, Any]],
) -> dict[str, Any]:
    args = input_data or {}
    ctx = context or {}
    try:
        manager = sandbox_manager(ctx)
        workspace = manager.prepare(args, ctx)
        return ok(action(manager, workspace))
    except PermissionError as exc:
        return error(str(exc), code="PATH_RESTRICTED")
    except FileNotFoundError as exc:
        return error(str(exc), code="FILE_NOT_FOUND")
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="SANDBOX_ERROR")

