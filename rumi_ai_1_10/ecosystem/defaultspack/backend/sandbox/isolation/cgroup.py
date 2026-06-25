from __future__ import annotations

import shutil

from .spec import CgroupLimits


def systemd_resource_controller_available() -> bool:
    return shutil.which("systemd-run") is not None


def build_systemd_run_argv(unit_name: str, limits: CgroupLimits, command: list[str]) -> list[str]:
    if not systemd_resource_controller_available():
        raise RuntimeError("SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE")
    safe_unit = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in unit_name)[:80]
    return [
        "systemd-run",
        "--user",
        "--wait",
        "--collect",
        f"--unit={safe_unit}",
        f"--property=MemoryMax={limits.memory_max}",
        f"--property=MemorySwapMax={limits.memory_swap_max}",
        f"--property=CPUQuota={limits.cpu_quota}",
        f"--property=TasksMax={int(limits.tasks_max)}",
        f"--property=RuntimeMaxSec={int(limits.runtime_max_sec)}",
        *command,
    ]
