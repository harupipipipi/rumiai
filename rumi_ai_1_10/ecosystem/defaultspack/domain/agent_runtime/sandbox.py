from __future__ import annotations

from typing import Any


def sandbox_mode_for(context: dict[str, Any] | None, risk: str = "read_only") -> str:
    context = context if isinstance(context, dict) else {}
    policy = context.get("profile_policy") if isinstance(context.get("profile_policy"), dict) else {}
    requested = policy.get("sandbox_mode") or context.get("sandbox_mode")
    if requested in {"none", "read_only", "workspace_write", "network", "auto"}:
        return str(requested)
    if risk in {"shell", "network", "browser", "computer"}:
        return "auto"
    if risk in {"file_write", "file_delete", "git_write"}:
        return "workspace_write"
    return "read_only"
