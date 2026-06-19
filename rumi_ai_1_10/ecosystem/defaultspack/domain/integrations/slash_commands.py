from __future__ import annotations

from typing import Any


def slash_command_execution_action(command_name: str) -> str:
    command_token = str(command_name or "").strip().lower().lstrip("/")
    if not command_token:
        return ""
    try:
        from domain.frontend.command_registry import SlashCommandRegistry

        command = SlashCommandRegistry().find_command(command_token)
    except Exception:
        return ""
    if not isinstance(command, dict):
        return ""
    execution = command.get("execution") if isinstance(command.get("execution"), dict) else {}
    return str(execution.get("action") or "").strip()


def command_execution_action(command: dict[str, Any]) -> str:
    execution = command.get("execution") if isinstance(command.get("execution"), dict) else {}
    return str(execution.get("action") or "").strip()
