"""Execution boundary policy primitives."""

from __future__ import annotations

import hashlib
from enum import Enum


class ExecutionBoundary(str, Enum):
    CORE_IN_PROCESS = "core_in_process"
    MANAGED_SANDBOX = "managed_sandbox"
    HOST_BROKER = "host_broker"
    DEVELOPMENT_HOST = "development_host"


SANDBOX_RUNTIME_UNAVAILABLE = "SANDBOX_RUNTIME_UNAVAILABLE"
SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE = "SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE"


def profile_runtime_name(profile_id: str) -> str:
    digest = hashlib.sha256(str(profile_id or "").strip().encode("utf-8")).hexdigest()[:16]
    return f"rumi-profile-{digest}"
