"""Production platform, Host Extension SDK, and OS wake contract tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from core_runtime.authority.v4 import (
    AuthorityMode,
    AuthorityScope,
    DomainBoundary,
    ExecutionDomain,
    FunctionPrincipal,
)
from tobkiri_host.backends import production_backend_registry
from tobkiri_host.contracts import OperationCatalog, OperationRoute
from tobkiri_host.errors import (
    AuthorizationError,
    BackendUnavailableError,
    ResolutionError,
    TriggerError,
)
from tobkiri_host.extension_sdk import (
    CapabilityProviderRegistration,
    HostExtensionRegistration,
    HostExtensionSDK,
)
from tobkiri_host.models import (
    ArtifactVariant,
    ContractOperation,
    ExecutionKind,
    FunctionArtifact,
    OpaqueAuthorityRef,
    PackArtifact,
    PackageKind,
)
from tobkiri_host.platform_backends import (
    IsolationLaunch,
    PlatformAttestation,
    ProductionIsolationBackend,
)
from tobkiri_host.ports import OpaqueInvocationLease
from tobkiri_host.triggers import (
    TriggerRegistration,
    TriggerWakeKernel,
    WakeAdapterStatus,
    WakeRegistrationLease,
)
from tobkiri_host.tauri_roles import validate_production_tauri_roles


def digest(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode()).hexdigest()}"


SCHEMA = {"type": "object", "additionalProperties": False}


def pack_artifact(kind: PackageKind = PackageKind.HOST_EXTENSION) -> PackArtifact:
    operation = ContractOperation(
        contract_id="host.files.v1",
        contract_version="1.0.0",
        revision_digest=digest("contract"),
        operation_id="read",
        input_schema=SCHEMA,
        output_schema=SCHEMA,
    )
    function = FunctionArtifact(
        function_id="extension.files.read",
        implementation_digest=digest("function"),
        variant_id="macos.arm64",
        operations=(operation,),
    )
    variant = ArtifactVariant(
        variant_id="macos.arm64",
        digest=digest("variant"),
        execution_kind=ExecutionKind.PACK_VM,
        os="macos",
        architecture="arm64",
        runtime_abi="packvm-v1",
        backend="macos-vz",
    )
    return PackArtifact(
        pack_id="extension.files",
        version="1.0.0",
        digest=digest("artifact"),
        publisher_lineage="publisher.files",
        package_kind=kind,
        functions=(function,),
        variants=(variant,),
    )


def binding():
    artifact = pack_artifact()
    route = OperationRoute(
        contract_id="host.files.v1",
        operation_id="read",
        artifact_digest=artifact.digest,
        function_id="extension.files.read",
        variant_id="macos.arm64",
        execution_domain_profile="packvm.host-extension.v1",
        materialization_mode="on_demand",
        target_principal_ref=OpaqueAuthorityRef("authority:files"),
    )
    return OperationCatalog((artifact,), (route,)).resolve(
        "host.files.v1", "read", ">=1,<2"
    )


class Driver:
    backend_id = "macos-vz"
    backend_digest = digest("backend")
    platform = "macos-arm64"

    def __init__(self) -> None:
        self.last_launch: IsolationLaunch | None = None
        self.attestation_platform: str | None = None
        self.terminated: list[str] = []

    def capability(self) -> tuple[bool, str | None]:
        return True, None

    def launch(self, request: IsolationLaunch) -> PlatformAttestation:
        self.last_launch = request
        result = PlatformAttestation(
            domain_id="domain.vz.1",
            backend_id=self.backend_id,
            backend_digest=self.backend_digest,
            platform=self.platform,
            executable_digest=request.executable_digest,
            isolation_profile=request.isolation_profile,
            attestation_digest=digest("attestation"),
            lease_id=request.lease.lease_id,
            reservation_id=request.reservation_id,
            authenticated_channel=True,
            nonce_fresh=True,
        )
        if self.attestation_platform is not None:
            return replace(result, platform=self.attestation_platform)
        return result

    def invoke(self, request: object) -> object:
        return request

    def cancel(self, request_id: str) -> None:
        return None

    def terminate(self, domain_id: str) -> None:
        self.terminated.append(domain_id)


def test_all_documented_platforms_register_exact_provider_with_controlled_driver() -> None:
    matrix = (
        ("Darwin", "arm64", "macos-vz", "macos-arm64"),
        ("Windows", "AMD64", "windows-whpx", "windows-amd64"),
        ("Linux", "x86_64", "linux-firecracker", "linux-amd64"),
    )
    for system, machine, backend_id, platform_id in matrix:
        driver = Driver()
        driver.backend_id = backend_id
        driver.platform = platform_id
        registry = production_backend_registry(
            platform_system=system,
            machine=machine,
            drivers=(driver,),
        )
        assert registry.statuses[0].backend_id == backend_id
        assert registry.statuses[0].ready_for_production


def test_platform_selection_and_attestation_fail_closed() -> None:
    selected = binding()
    unavailable = production_backend_registry(
        platform_system="Darwin", machine="arm64"
    )
    with pytest.raises(BackendUnavailableError, match="supervisor"):
        unavailable.select(selected)
    driver = Driver()
    backend = ProductionIsolationBackend(driver)
    evidence = backend.materialize(selected, "reservation-1")
    assert evidence.resource_reservation_id == "reservation-1"
    assert driver.last_launch is not None
    assert evidence.domain_lease_id == driver.last_launch.lease.lease_id
    driver.attestation_platform = "linux-arm64"
    with pytest.raises(BackendUnavailableError, match="attestation"):
        backend.materialize(selected, "reservation-2")
    wrong = replace(selected.variant, backend="linux-firecracker")
    with pytest.raises(BackendUnavailableError, match="wrong platform"):
        backend.materialize(replace(selected, variant=wrong), "reservation-3")


class RegistrationStore:
    security_epoch = 1

    def __init__(self) -> None:
        self.records: list[object] = []

    def put_records_atomically(self, records) -> None:
        self.records.extend(records)


class Authority:
    def __init__(self) -> None:
        self.store = RegistrationStore()
        self.revocations: list[tuple[str, str]] = []

    def revoke(self, *, target_kind: str, target_id: str, reason: str) -> str:
        self.revocations.append((target_kind, target_id))
        return digest(reason)


def extension_registration(
    kind: PackageKind = PackageKind.HOST_EXTENSION,
) -> HostExtensionRegistration:
    artifact = pack_artifact(kind)
    operation = artifact.functions[0].operations[0]
    principal = FunctionPrincipal(
        parent_artifact_digest=artifact.digest,
        function_implementation_digest=artifact.functions[0].implementation_digest,
        function_id=artifact.functions[0].function_id,
        contract_revision_digest=operation.revision_digest,
        operation_id=operation.operation_id,
    )
    domain = ExecutionDomain(
        domain_id="domain.extension.files",
        profile_id="host.extensions",
        activation_id="extension.files.activation",
        boot_epoch=1,
        process_identity="signed.helper.files",
        authenticated_channel_digest=digest("channel"),
        sandbox_profile_digest=digest("sandbox"),
        resource_namespace="extension.files.resources",
        principals=(principal,),
        boundary=DomainBoundary.DEDICATED_PROCESS,
        security_epoch=1,
    )
    scope = AuthorityScope(
        capability="host.files.read",
        semantics_digest=digest("scope"),
        dimensions={"root": ("workspace",)},
    )
    provider = CapabilityProviderRegistration(
        provider_id="extension.files.read",
        function_id="extension.files.read",
        contract_id="host.files.v1",
        operation_id="read",
        capability="host.files.read",
        scope_semantics_digest=scope.semantics_digest,
        provider_ceiling=scope,
        authority_mode=AuthorityMode.LEASE_ONLY,
        execution_domain=domain,
        input_schema=SCHEMA,
        output_schema=SCHEMA,
        error_schema=None,
        progress_schema=None,
        attenuation_definition={"kind": "path_root"},
        approval_metadata={"risk": "read"},
        audit_metadata={"redact": []},
        conformance_vectors=({"root": "workspace"},),
        host_broker_binding="resource-handle.files.v1",
    )
    return HostExtensionRegistration(
        registration_id="registration.files.v1",
        host_extension_id="extension.files",
        trust_id="trust.extension.files.v1",
        artifact=artifact,
        trust_provenance_digest=digest("trust"),
        providers=(provider,),
        valid_from=1.0,
    )


def test_host_extension_sdk_exact_registration_revoke_and_normal_pack_denial() -> None:
    authority = Authority()
    sdk = HostExtensionSDK(authority, sqlite3.connect(":memory:"), clock=lambda: 2.0)
    ids = sdk.register(extension_registration())
    assert ids == ("provider-authority.registration.files.v1.0",)
    assert len(authority.store.records) == 3
    sdk.revoke("registration.files.v1", reason="operator revoke")
    assert authority.revocations == [
        ("provider_authority", ids[0]),
        ("host_extension", "trust.extension.files.v1"),
    ]
    assert [event["event_type"] for event in sdk.audit_events("registration.files.v1")] == [
        "registered",
        "revoked",
    ]
    with pytest.raises(AuthorizationError, match="normal Pack/Profile"):
        sdk.register(extension_registration(PackageKind.NORMAL))


class WakeAuthority:
    def issue_trigger_lease(
        self,
        registration_id: str,
        occurrence_id: str,
        target: OpaqueAuthorityRef,
        security_epoch: int,
    ) -> OpaqueInvocationLease:
        return OpaqueInvocationLease(f"{registration_id}:{occurrence_id}".encode())


class WakeAdapter:
    status = WakeAdapterStatus("macos.backgroundtasks", "macos", True)

    def __init__(self) -> None:
        self.armed: list[str] = []
        self.revoked: list[str] = []

    def register(self, registration: TriggerRegistration) -> WakeRegistrationLease:
        return WakeRegistrationLease(
            "wake-lease-1", registration.registration_id, registration.security_epoch
        )

    def arm(
        self,
        lease: WakeRegistrationLease,
        occurrence_id: str,
        due_monotonic: float,
    ) -> None:
        self.armed.append(occurrence_id)

    def revoke(self, lease: WakeRegistrationLease) -> None:
        self.revoked.append(lease.registration_id)


def test_production_wake_requires_adapter_lease_and_current_epoch() -> None:
    epoch = [1]
    adapter = WakeAdapter()
    kernel = TriggerWakeKernel(
        sqlite3.connect(":memory:"),
        WakeAuthority(),
        clock=lambda: 10.0,
        wake_adapter=adapter,
        current_security_epoch=lambda: epoch[0],
        production=True,
    )
    registration = TriggerRegistration(
        "daily", "trigger.v1", "deliver", OpaqueAuthorityRef("target.daily"), digest("a"), 1
    )
    kernel.register(registration)
    assert kernel.schedule("daily", "occurrence-1", 9.0)
    assert adapter.armed == ["occurrence-1"]
    epoch[0] = 2
    with pytest.raises(TriggerError, match="stale"):
        kernel.claim_due()
    epoch[0] = 1
    kernel.revoke("daily")
    with pytest.raises(TriggerError, match="unknown or disabled"):
        kernel.schedule("daily", "occurrence-2", 11.0)
    unavailable = TriggerWakeKernel(
        sqlite3.connect(":memory:"),
        WakeAuthority(),
        current_security_epoch=lambda: 1,
        production=True,
    )
    with pytest.raises(TriggerError, match="not registered"):
        unavailable.register(registration)


def test_generated_tauri_roles_are_separate_and_production_selects_runtime_only() -> None:
    bundle = Path(__file__).parents[1] / "ecosystem" / "defaultspack" / "v4"
    runtime = json.loads(
        (bundle / "packs" / "runtime.tauri.application.default.pack.v4.json").read_text(
            encoding="utf-8"
        )
    )
    toolchain = json.loads(
        (bundle / "packs" / "dev.tauri.toolchain.default.pack.v4.json").read_text(
            encoding="utf-8"
        )
    )
    profile = json.loads(
        (bundle / "defaults.profile.v4.json").read_text(encoding="utf-8")
    )
    assert runtime["pack"]["kind"] == "application"
    assert runtime["contracts"][0]["contract_id"] == "runtime.tauri.application.v1"
    assert toolchain["pack"]["kind"] == "host_extension"
    assert toolchain["contracts"][0]["contract_id"] == "dev.tauri.toolchain.v1"
    selected = {item["pack_id"] for item in profile["packs"]}
    assert "runtime.tauri.application.default" in selected
    assert not any(item.startswith("dev.tauri.toolchain.") for item in selected)


def test_production_tauri_roles_reject_missing_runtime_and_development_toolchain() -> None:
    profile = {
        "shell": {"pack_id": "shell.tauri.default"},
        "packs": [{"pack_id": "runtime.tauri.application.default"}],
    }
    lock = {
        "effective_set": [
            {"identity": "runtime.tauri.application.default"},
        ]
    }
    validate_production_tauri_roles(profile, lock)
    with pytest.raises(ResolutionError, match="exactly one selected runtime"):
        validate_production_tauri_roles(profile, {"effective_set": []})
    with pytest.raises(ResolutionError, match="Development Realm"):
        validate_production_tauri_roles(
            profile,
            {
                "effective_set": [
                    {"identity": "runtime.tauri.application.default"},
                    {"identity": "dev.tauri.toolchain.default"},
                ]
            },
        )
