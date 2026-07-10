"""Safe Kiro CLI coding-backend discovery scaffold.

This module does not execute coding prompts. It exposes read-only installation,
authentication, and account-scoped model discovery plus a least-privilege
headless command planner. Interactive execution belongs in the ACP backend.
"""

from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from domain.kiro.cli import (
    KiroCliError,
    build_kiro_headless_command,
    kiro_cli_status,
    list_kiro_models,
)


class KiroCliBackend:
    backend_id = "kiro-cli"

    def status(self, **kwargs: Any) -> dict[str, Any]:
        return kiro_cli_status(**kwargs)

    def list_models(self, **kwargs: Any) -> list[dict[str, Any]]:
        return list_kiro_models(**kwargs)

    def build_headless_command(self, prompt: str, **kwargs: Any) -> list[str]:
        return build_kiro_headless_command(prompt, **kwargs)


def run(input_data, context):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    action = str(payload.get("action") or "status").strip().lower()
    command = str(payload.get("command") or "kiro-cli").strip() or "kiro-cli"
    try:
        timeout_seconds = max(1, min(60, int(payload.get("timeout_seconds") or 12)))
    except (TypeError, ValueError):
        timeout_seconds = 12
    connection_id = str(payload.get("connection_id") or "default").strip() or "default"

    try:
        if action == "status":
            result = kiro_cli_status(
                command=command,
                timeout_seconds=timeout_seconds,
                include_models=bool(payload.get("include_models", True)),
                connection_id=connection_id,
            )
            return ok(result)
        if action == "list_models":
            models = list_kiro_models(
                command=command,
                timeout_seconds=timeout_seconds,
                connection_id=connection_id,
            )
            return ok({"provider_id": "kiro-cli", "models": models, "count": len(models)})
        if action == "build_headless_command":
            argv = build_kiro_headless_command(
                str(payload.get("prompt") or ""),
                command=command,
                trusted_tools=(
                    payload.get("trusted_tools")
                    if isinstance(payload.get("trusted_tools"), list)
                    else []
                ),
                effort=str(payload.get("effort") or ""),
                agent=str(payload.get("agent") or ""),
            )
            return ok({"provider_id": "kiro-cli", "argv": argv, "executed": False})
    except (KiroCliError, ValueError) as exc:
        return error(str(exc), "KIRO_CLI_BACKEND_ERROR")

    return error(f"unsupported Kiro CLI action: {action}", "METHOD_NOT_ALLOWED")
