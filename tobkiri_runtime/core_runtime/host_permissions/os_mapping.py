"""OS permission mapping for host.* permissions."""

from __future__ import annotations

import sys

from .registry import get_host_permission_definition, normalize_host_permission_id


def current_os_key() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def os_permissions_for_host_permission(permission_id: str, platform: str | None = None) -> list[str]:
    definition = get_host_permission_definition(normalize_host_permission_id(permission_id))
    if definition is None:
        return []
    key = platform or current_os_key()
    return list(definition.os_permissions.get(key) or [])
