from __future__ import annotations


def choose_sandbox_mode(policy: dict, risk: str) -> str:
    requested = policy.get("sandbox_mode")
    if requested in {"none", "read_only", "workspace_write", "network", "auto"}:
        return str(requested)
    if risk in {"file_write", "file_delete", "git_write"}:
        return "workspace_write"
    if risk in {"shell", "network", "browser", "computer"}:
        return "auto"
    return "read_only"
