from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from .spec import CgroupLimits


@dataclass(frozen=True)
class SystemdUserScopeProbe:
    ok: bool
    path: str | None
    message: str
    returncode: int | None = None
    stderr: str = ""


def probe_systemd_user_scope(*, timeout_seconds: float = 3.0) -> SystemdUserScopeProbe:
    path = shutil.which("systemd-run")
    if path is None:
        return SystemdUserScopeProbe(
            ok=False,
            path=None,
            message="systemd-run is not installed",
        )
    command = [path, "--user", "--scope", "--quiet", "true"]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            close_fds=True,
        )
    except subprocess.TimeoutExpired:
        return SystemdUserScopeProbe(
            ok=False,
            path=path,
            message="systemd-run --user scope probe timed out",
        )
    except OSError as exc:
        return SystemdUserScopeProbe(
            ok=False,
            path=path,
            message=f"systemd-run --user scope probe failed: {exc}",
        )
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return SystemdUserScopeProbe(
            ok=False,
            path=path,
            message="systemd-run --user scope probe failed",
            returncode=proc.returncode,
            stderr=stderr[:1000],
        )
    return SystemdUserScopeProbe(
        ok=True,
        path=path,
        message="systemd-run --user scope is available",
        returncode=0,
        stderr=stderr[:1000],
    )


def systemd_resource_controller_available() -> bool:
    return probe_systemd_user_scope().ok


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
