"""Attested production PackVM adapters for the supported host substrates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform as host_platform
import time
from typing import Callable, Iterable, Mapping, Protocol

from .backends import BackendStatus, REQUIRED_PRODUCTION_GATES
from .contracts import ResolvedOperationBinding
from .errors import BackendUnavailableError
from .models import ExecutionKind, OpaqueAuthorityRef, RuntimeEvidence, require_digest


SUPPORTED_BACKENDS: Mapping[str, tuple[str, str]] = {
    "Darwin": ("macos-vz", "/System/Library/Frameworks/Virtualization.framework"),
    "Windows": ("windows-whpx", "C:/Windows/System32/WinHvPlatform.dll"),
    "Linux": ("linux-firecracker", "/dev/kvm"),
}


@dataclass(frozen=True)
class IsolationLease:
    """Finite Host-owned lease for one materialized domain."""

    lease_id: str
    reservation_id: str
    expires_monotonic: float

    def __post_init__(self) -> None:
        if not self.lease_id or not self.reservation_id:
            raise BackendUnavailableError("domain lease identity is missing")
        if self.expires_monotonic <= 0:
            raise BackendUnavailableError("domain lease expiry is invalid")


@dataclass(frozen=True)
class IsolationLaunch:
    """Exact launch request passed to a privileged platform supervisor."""

    backend_id: str
    platform: str
    artifact_digest: str
    executable_digest: str
    isolation_profile: str
    reservation_id: str
    lease: IsolationLease


@dataclass(frozen=True)
class PlatformAttestation:
    """Host-authenticated evidence returned by the platform supervisor."""

    domain_id: str
    backend_id: str
    backend_digest: str
    platform: str
    executable_digest: str
    isolation_profile: str
    attestation_digest: str
    lease_id: str
    reservation_id: str
    authenticated_channel: bool
    nonce_fresh: bool

    def __post_init__(self) -> None:
        require_digest(self.backend_digest, "attested backend")
        require_digest(self.executable_digest, "attested executable")
        require_digest(self.attestation_digest, "platform attestation")


class PlatformIsolationDriver(Protocol):
    """Privileged supervisor boundary implemented by VZ, WHPX, or Firecracker."""

    backend_id: str
    backend_digest: str
    platform: str

    def capability(self) -> tuple[bool, str | None]:
        """Return deterministic dependency readiness without mutating the Host."""

    def launch(self, request: IsolationLaunch) -> PlatformAttestation:
        """Launch an exact artifact in the required isolation substrate."""

    def invoke(self, request: object) -> object:
        """Invoke over the authenticated supervisor channel."""

    def cancel(self, request_id: str) -> None:
        """Fence one request at the supervisor."""

    def terminate(self, domain_id: str) -> None:
        """Destroy one domain and release all platform resources."""


class UnavailablePlatformDriver:
    """Deterministic fail-closed driver used when Host dependencies are absent."""

    def __init__(self, backend_id: str, platform: str, reason: str) -> None:
        self.backend_id = backend_id
        self.platform = platform
        self.backend_digest = _digest(
            {"backend_id": backend_id, "platform": platform, "state": "unavailable"}
        )
        self._reason = reason

    def capability(self) -> tuple[bool, str | None]:
        return False, self._reason

    def launch(self, request: IsolationLaunch) -> PlatformAttestation:
        raise BackendUnavailableError(self._reason)

    def invoke(self, request: object) -> object:
        raise BackendUnavailableError(self._reason)

    def cancel(self, request_id: str) -> None:
        return None

    def terminate(self, domain_id: str) -> None:
        return None


class ProductionIsolationBackend:
    """Broker-facing adapter enforcing lifecycle, attestation, lease, and charge."""

    def __init__(
        self,
        driver: PlatformIsolationDriver,
        *,
        lease_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        ready, reason = driver.capability()
        self._driver = driver
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._domains: dict[str, PlatformAttestation] = {}
        self._reservations: dict[str, str] = {}
        self._leases: dict[str, IsolationLease] = {}
        self.status = BackendStatus(
            backend_id=driver.backend_id,
            execution_kind=ExecutionKind.PACK_VM,
            platform=driver.platform,
            backend_digest=driver.backend_digest,
            production_enabled=ready,
            conformance_only=not ready,
            satisfied_gates=REQUIRED_PRODUCTION_GATES if ready else frozenset(),
            unavailable_reason=reason,
        )

    def materialize(
        self,
        binding: ResolvedOperationBinding,
        reservation_id: str,
    ) -> RuntimeEvidence:
        if not self.status.ready_for_production:
            raise BackendUnavailableError(
                self.status.unavailable_reason or "platform backend is unavailable"
            )
        if binding.variant.backend != self.status.backend_id:
            raise BackendUnavailableError("launch requested the wrong platform provider")
        if binding.variant.execution_kind is not ExecutionKind.PACK_VM:
            raise BackendUnavailableError("platform backend requires a PackVM variant")
        if reservation_id in self._reservations:
            raise BackendUnavailableError("resource reservation is already materialized")
        lease = IsolationLease(
            lease_id=_digest(
                {
                    "reservation_id": reservation_id,
                    "executable": binding.function.implementation_digest,
                    "backend": self.status.backend_digest,
                }
            ),
            reservation_id=reservation_id,
            expires_monotonic=self._clock() + self._lease_seconds,
        )
        launch = IsolationLaunch(
            backend_id=self.status.backend_id,
            platform=self.status.platform,
            artifact_digest=binding.artifact.digest,
            executable_digest=binding.function.implementation_digest,
            isolation_profile=binding.route.execution_domain_profile,
            reservation_id=reservation_id,
            lease=lease,
        )
        attestation = self._driver.launch(launch)
        try:
            self._validate_attestation(launch, attestation)
        except BackendUnavailableError:
            self._driver.terminate(attestation.domain_id)
            raise
        if attestation.domain_id in self._domains:
            self._driver.terminate(attestation.domain_id)
            raise BackendUnavailableError("platform supervisor reused a live domain identity")
        self._domains[attestation.domain_id] = attestation
        self._reservations[reservation_id] = attestation.domain_id
        self._leases[attestation.domain_id] = lease
        return RuntimeEvidence(
            domain_ref=OpaqueAuthorityRef(attestation.domain_id),
            executable_digest=attestation.executable_digest,
            backend_digest=attestation.backend_digest,
            authenticated_channel=attestation.authenticated_channel,
            nonce_fresh=attestation.nonce_fresh,
            platform=attestation.platform,
            isolation_profile=attestation.isolation_profile,
            attestation_digest=attestation.attestation_digest,
            domain_lease_id=attestation.lease_id,
            resource_reservation_id=attestation.reservation_id,
        )

    def invoke(self, request: object) -> object:
        target = getattr(getattr(request, "target_domain", None), "value", None)
        if not isinstance(target, str):
            raise BackendUnavailableError("provider request has no Host domain identity")
        lease = self._leases.get(target)
        if lease is None or lease.expires_monotonic <= self._clock():
            self.terminate(target)
            raise BackendUnavailableError("provider domain lease is unavailable or expired")
        return self._driver.invoke(request)

    def cancel(self, request_id: str) -> None:
        self._driver.cancel(request_id)

    def terminate(self, domain_id: str) -> None:
        attestation = self._domains.pop(domain_id, None)
        if attestation is not None:
            self._reservations.pop(attestation.reservation_id, None)
            self._leases.pop(domain_id, None)
        self._driver.terminate(domain_id)

    def _validate_attestation(
        self,
        launch: IsolationLaunch,
        attestation: PlatformAttestation,
    ) -> None:
        if (
            attestation.backend_id != launch.backend_id
            or attestation.backend_digest != self.status.backend_digest
            or attestation.platform != launch.platform
            or attestation.executable_digest != launch.executable_digest
            or attestation.isolation_profile != launch.isolation_profile
            or attestation.lease_id != launch.lease.lease_id
            or attestation.reservation_id != launch.reservation_id
            or not attestation.authenticated_channel
            or not attestation.nonce_fresh
        ):
            raise BackendUnavailableError("platform attestation does not match launch")


class MacOSVZBackend(ProductionIsolationBackend):
    """macOS Virtualization.framework PackVM backend."""

    def __init__(self, driver: PlatformIsolationDriver) -> None:
        if driver.backend_id != "macos-vz" or not driver.platform.startswith("macos-"):
            raise BackendUnavailableError("macOS VZ driver identity mismatch")
        super().__init__(driver)


class WindowsWHPXBackend(ProductionIsolationBackend):
    """Windows Hypervisor Platform PackVM backend."""

    def __init__(self, driver: PlatformIsolationDriver) -> None:
        if driver.backend_id != "windows-whpx" or not driver.platform.startswith("windows-"):
            raise BackendUnavailableError("Windows WHPX driver identity mismatch")
        super().__init__(driver)


class LinuxFirecrackerBackend(ProductionIsolationBackend):
    """Linux Firecracker/KVM PackVM backend."""

    def __init__(self, driver: PlatformIsolationDriver) -> None:
        if driver.backend_id != "linux-firecracker" or not driver.platform.startswith("linux-"):
            raise BackendUnavailableError("Linux Firecracker driver identity mismatch")
        super().__init__(driver)


def build_platform_backend(
    *,
    platform_system: str | None = None,
    machine: str | None = None,
    drivers: Iterable[PlatformIsolationDriver] = (),
) -> ProductionIsolationBackend:
    """Build exactly the documented backend for the selected Host platform."""
    system = platform_system or host_platform.system()
    architecture = _normalize_machine(machine or host_platform.machine())
    spec = SUPPORTED_BACKENDS.get(system)
    if spec is None:
        driver: PlatformIsolationDriver = UnavailablePlatformDriver(
            "unsupported-packvm", f"{system.lower()}-{architecture}", "unsupported Host platform"
        )
        return ProductionIsolationBackend(driver)
    backend_id, dependency = spec
    platform_id = f"{system.lower().replace('darwin', 'macos')}-{architecture}"
    candidates = [
        item
        for item in drivers
        if getattr(item, "backend_id", None) == backend_id
        and getattr(item, "platform", None) == platform_id
    ]
    if len(candidates) > 1:
        raise BackendUnavailableError("multiple platform supervisors registered")
    if candidates:
        backend_class = {
            "macos-vz": MacOSVZBackend,
            "windows-whpx": WindowsWHPXBackend,
            "linux-firecracker": LinuxFirecrackerBackend,
        }[backend_id]
        return backend_class(candidates[0])
    reason = (
        f"required substrate dependency is unavailable: {dependency}"
        if not Path(dependency).exists()
        else f"authenticated {backend_id} supervisor is not registered"
    )
    return ProductionIsolationBackend(
        UnavailablePlatformDriver(backend_id, platform_id, reason)
    )


def _normalize_machine(value: str) -> str:
    return {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64"}.get(
        value, value.lower()
    )


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


__all__ = [
    "IsolationLaunch",
    "IsolationLease",
    "LinuxFirecrackerBackend",
    "MacOSVZBackend",
    "PlatformAttestation",
    "PlatformIsolationDriver",
    "ProductionIsolationBackend",
    "SUPPORTED_BACKENDS",
    "WindowsWHPXBackend",
    "build_platform_backend",
]
