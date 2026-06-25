from __future__ import annotations

import platform
import shutil
import subprocess

from ..models import Diagnostic, RUNTIME_CAPABILITIES, RuntimeProviderStatus, RuntimeRequirements


class ManagedUbuntuProvider:
    provider_id = "managed_ubuntu"
    platform_name = "linux"
    command_name = "bwrap"

    def doctor(self, request: RuntimeRequirements) -> RuntimeProviderStatus:
        host_platform = platform.system().lower() or "unknown"
        platform_ok = self.platform_name == "any" or host_platform == self.platform_name
        command_path = shutil.which(self.command_name)
        missing: list[str] = []
        diagnostics: list[Diagnostic] = []
        version: str | None = None
        if not platform_ok:
            missing.append(f"platform:{self.platform_name}")
        if command_path is None:
            missing.append(f"command:{self.command_name}")
        else:
            version = _command_version(command_path)
        if self.provider_id == "bwrap_host":
            if shutil.which("systemd-run") is None:
                missing.append("command:systemd-run")
            if not _unprivileged_userns_available():
                missing.append("kernel:unprivileged_userns")
        missing_caps = sorted(request.required_capabilities - RUNTIME_CAPABILITIES)
        missing.extend(missing_caps)
        if missing:
            diagnostics.append(
                Diagnostic(
                    code="RUNTIME_REQUIREMENT_MISSING",
                    message="Runtime provider requirements are not satisfied",
                    severity="warning",
                    details={"missing": tuple(missing)},
                )
            )
        return RuntimeProviderStatus(
            provider_id=self.provider_id,
            platform=self.platform_name,
            available=platform_ok and command_path is not None,
            installed=command_path is not None,
            ready=platform_ok and command_path is not None and not missing,
            version=version,
            capabilities=RUNTIME_CAPABILITIES if platform_ok else frozenset(),
            missing_requirements=tuple(missing),
            diagnostics=tuple(diagnostics),
        )


class LimaManagedUbuntuProvider(ManagedUbuntuProvider):
    provider_id = "lima_ubuntu"
    platform_name = "darwin"
    command_name = "limactl"


class WslManagedUbuntuProvider(ManagedUbuntuProvider):
    provider_id = "wsl_rumi_ubuntu"
    platform_name = "windows"
    command_name = "wsl.exe"


class BwrapHostProvider(ManagedUbuntuProvider):
    provider_id = "bwrap_host"
    platform_name = "linux"
    command_name = "bwrap"


def _command_version(command_path: str) -> str | None:
    try:
        proc = subprocess.run(
            [command_path, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0] if text else None


def _unprivileged_userns_available() -> bool:
    try:
        value = open("/proc/sys/kernel/unprivileged_userns_clone", encoding="utf-8").read().strip()
    except OSError:
        return platform.system().lower() != "linux"
    return value not in {"0", "false", "False"}
