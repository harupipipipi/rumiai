from __future__ import annotations

import shutil
from typing import Any

from ..errors import SANDBOX_RUNTIME_UNAVAILABLE


class ManagedSandboxSupervisor:
    """Fail-closed supervisor placeholder for managed sandbox execution."""

    def __init__(self, provider_registry: Any | None = None) -> None:
        self.provider_registry = provider_registry

    def available(self) -> bool:
        return shutil.which("bwrap") is not None and shutil.which("systemd-run") is not None

    def execute_capability(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.available():
            return {
                "success": False,
                "ok": False,
                "error": "Managed Bubblewrap/cgroup sandbox runtime is unavailable",
                "error_type": SANDBOX_RUNTIME_UNAVAILABLE,
                "execution_boundary": "managed_sandbox",
                "request": {
                    "profile_runtime": request.get("profile_runtime"),
                    "pack_id": request.get("pack_id"),
                    "function_id": request.get("function_id"),
                    "calling_convention": request.get("calling_convention"),
                },
            }
        raise RuntimeError("managed sandbox guest execution is not connected")
