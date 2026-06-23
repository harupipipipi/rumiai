"""Host permission registry public API."""

from .models import HOST_PERMISSION_IDS, LEGACY_HOST_PERMISSION_ALIASES, HostPermissionDefinition
from .os_mapping import current_os_key, os_permissions_for_host_permission
from .registry import (
    get_host_permission_definition,
    host_permission_exists,
    list_host_permission_definitions,
    load_host_permission_registry,
    normalize_host_permission_id,
)

__all__ = [
    "HOST_PERMISSION_IDS",
    "LEGACY_HOST_PERMISSION_ALIASES",
    "HostPermissionDefinition",
    "current_os_key",
    "get_host_permission_definition",
    "host_permission_exists",
    "list_host_permission_definitions",
    "load_host_permission_registry",
    "normalize_host_permission_id",
    "os_permissions_for_host_permission",
]
