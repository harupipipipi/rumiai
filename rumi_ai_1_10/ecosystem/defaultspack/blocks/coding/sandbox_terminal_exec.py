from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from blocks.coding.sandbox_common import sandbox_manager
from backend.sandbox.isolation import ManagedSandboxSupervisor


def run(input_data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    command = input_data.get("command")
    argv = input_data.get("argv")
    if not command and not argv:
        return error("'command' or 'argv' is required", code="INVALID_INPUT")
    if input_data.get("network") or input_data.get("network_enabled"):
        return ok(
            {
                "requires_approval": True,
                "approval_required": True,
                "operation": "sandbox.network.request",
                "message": "Sandbox network access requires a separate approval path.",
                "sandbox_only": True,
            }
        )
    try:
        manager = sandbox_manager(context)
        workspace = manager.prepare(input_data, context or {})
        supervisor = _supervisor(context)
        result = supervisor.execute_coding_terminal(
            {
                "sandbox_id": workspace.sandbox_id,
                "workspace_root": str(workspace.work_root),
                "command": command,
                "argv": argv,
                "cwd": input_data.get("cwd") or ".",
                "timeout_seconds": input_data.get("timeout") or input_data.get("timeout_seconds") or 30,
                "network_enabled": False,
                "provider_id": input_data.get("provider_id"),
                "lima_instance": input_data.get("lima_instance"),
            }
        )
        if not result.get("success", result.get("ok", False)):
            return error(
                str(result.get("error") or "sandbox terminal failed"),
                code=str(result.get("error_type") or result.get("code") or "SANDBOX_ERROR"),
            )
        preview = manager.diff_preview(workspace, max_chars=input_data.get("max_diff_chars"))
        return ok(
            {
                **result,
                "host_modified": False,
                "sandbox_only": True,
                "changed_files": preview.get("changed_files", []),
                "changed_file_count": preview.get("changed_file_count", 0),
                "diff_summary": preview.get("diff_summary", ""),
                **workspace.to_public_dict(),
            }
        )
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="SANDBOX_ERROR")


def _supervisor(context: dict[str, Any] | None) -> ManagedSandboxSupervisor:
    injected = (context or {}).get("managed_sandbox_supervisor") if isinstance(context, dict) else None
    if isinstance(injected, ManagedSandboxSupervisor):
        return injected
    return ManagedSandboxSupervisor()
