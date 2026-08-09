"""Assemble the sole live Pack v4 composition from one active snapshot."""

from __future__ import annotations

import secrets
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from ecosystem.defaultspack.domain.runtime_v4 import (
    ActivationStore,
    ActiveDefaultProfile,
    BundledCatalog,
)
from tobkiri_host.admission import AdmissionEstimate, QueueScope, ResourceReservation
from tobkiri_host.backends import BackendRegistry, BackendStatus
from tobkiri_host.broker import AdmissionTicket, RequestAdmissionPort
from tobkiri_host.composition import AuthorityCeilings
from tobkiri_host.contracts import AdapterPlanner, ResolvedOperationBinding, StructuralAdapter
from tobkiri_host.effects import InMemoryReconciliationStore
from tobkiri_host.materialization import MaterializationCoordinator
from tobkiri_host.models import (
    ArtifactVariant,
    ContractOperation,
    ExecutionKind,
    FunctionArtifact,
    OpaqueAuthorityRef,
    PackArtifact,
    PackageKind,
    RequestContext,
)
from tobkiri_host.errors import BackendUnavailableError
from tobkiri_host.runtime import ProductionRuntimeV4, V4DispatchSession
from tobkiri_protocol.canonical import canonical_digest

from ..authority.v4 import (
    ApprovalRecord,
    AuthorityDenied,
    AuthorityMode,
    AuthorityScope,
    AuthorityStore,
    DomainBoundary,
    ExecutionDomain,
    FunctionPrincipal,
    GrantLifetime,
    GrantRecord,
    ProviderAuthorityRecord,
    authority_digest,
)
from ..pack_catalog_backend_v4 import (
    PACK_CATALOG_BACKEND_ID,
    PackControlBackendV4,
)
from ..pack_control_v4 import (
    PACK_CONTROL_CONTRACT,
    capture_pack_control_session,
    capture_valid_pack_approval,
)
from ..pack_boundary import resolve_selected_pack_roots


_PACK_CATALOG_KEY = (PACK_CONTROL_CONTRACT, "catalog.read")
_PYTHON_PACK_BACKEND_ID = "tobkiri.python-pack-v4"


class _UnavailablePythonPackBackend:
    """Exact fail-closed registration when no authenticated PackVM exists."""

    def __init__(self) -> None:
        self.status = BackendStatus(
            backend_id=_PYTHON_PACK_BACKEND_ID,
            execution_kind=ExecutionKind.PACK_VM,
            platform="any",
            backend_digest=canonical_digest(
                {
                    "backend": _PYTHON_PACK_BACKEND_ID,
                    "state": "authenticated-supervisor-unavailable",
                }
            ),
            production_enabled=False,
            conformance_only=True,
            unavailable_reason=(
                "authenticated PackVM supervisor is not registered for tobkiri.python-pack-v4"
            ),
        )

    def materialize(self, binding: Any, reservation_id: str) -> Any:
        del binding, reservation_id
        raise BackendUnavailableError(self.status.unavailable_reason or "backend unavailable")

    def invoke(self, request: object) -> object:
        del request
        raise BackendUnavailableError(self.status.unavailable_reason or "backend unavailable")

    def cancel(self, request_id: str) -> None:
        del request_id

    def terminate(self, domain_id: str) -> None:
        del domain_id


class _NoAdapterExecution:
    def execute(self, adapter: StructuralAdapter, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raise RuntimeError(f"unexpected structural adapter: {adapter.adapter_id}")


class _FiniteAdmission(RequestAdmissionPort):
    """Small bounded admission port for the bootstrap Broker."""

    def estimate(
        self,
        context: RequestContext,
        binding: ResolvedOperationBinding,
        payload: Mapping[str, Any],
    ) -> AdmissionEstimate:
        del context, binding, payload
        return AdmissionEstimate(
            measured_p95_bytes=1024 * 1024,
            declared_minimum_bytes=1024 * 1024,
            runtime_floor_bytes=1024 * 1024,
            profile_reservation_bytes=1024 * 1024,
            backend_overhead_bytes=1024 * 1024,
        )

    def acquire(
        self,
        scope: QueueScope,
        estimate: AdmissionEstimate,
        wait_timeout_seconds: float,
    ) -> AdmissionTicket:
        if wait_timeout_seconds <= 0:
            raise TimeoutError("admission deadline expired")
        return AdmissionTicket(
            ResourceReservation(
                reservation_id="reservation." + secrets.token_hex(16),
                profile_id=scope.profile_id,
                amount=estimate.charge(),
            )
        )

    def release(self, ticket: AdmissionTicket) -> None:
        del ticket


def _pack_root_identities(pack_roots: Mapping[str, Path]) -> dict[str, tuple[int, int]]:
    """Reject symlinks and capture exact Pack-root filesystem identities."""

    identities: dict[str, tuple[int, int]] = {}
    for pack_id, root in sorted(pack_roots.items()):
        if root.is_symlink() or not root.is_dir():
            raise AuthorityDenied(f"selected Pack root is unavailable: {pack_id}")
        for current, directories, names in os.walk(root, followlinks=False):
            current_path = Path(current)
            if current_path.is_symlink() or any(
                (current_path / name).is_symlink() for name in (*directories, *names)
            ):
                raise AuthorityDenied(f"selected Pack contains a symlink: {pack_id}")
        stat_result = root.stat()
        identities[pack_id] = (int(stat_result.st_dev), int(stat_result.st_ino))
    return identities


def _shell_artifact(catalog: BundledCatalog, shell_id: str) -> PackArtifact:
    manifest = catalog.packs[shell_id]
    functions: list[FunctionArtifact] = []
    variants: list[ArtifactVariant] = []
    for index, function in enumerate(manifest["functions"]):
        contract = next(
            item
            for item in manifest["contracts"]
            if item["revision_digest"] == function["contract_revision_digest"]
        )
        variant_id = f"{shell_id}.captured.{index}"
        functions.append(
            FunctionArtifact(
                function_id=function["id"],
                implementation_digest=function["implementation_digest"],
                variant_id=variant_id,
                operations=tuple(
                    ContractOperation(
                        contract_id=contract["contract_id"],
                        contract_version="1.0.0",
                        revision_digest=contract["revision_digest"],
                        operation_id=operation_id,
                        input_schema={"type": "object"},
                        output_schema={"type": "object"},
                    )
                    for operation_id in function["operations"]
                ),
            )
        )
        variants.append(
            ArtifactVariant(
                variant_id=variant_id,
                digest=function["implementation_digest"],
                execution_kind=ExecutionKind.HOST_EXTENSION,
                os=str(manifest["pack"].get("platform") or "any"),
                architecture="any",
                runtime_abi="tobkiri-shell-v4",
                backend="tobkiri.shell-host-v4",
            )
        )
    return PackArtifact(
        pack_id=shell_id,
        version=manifest["pack"]["version"],
        digest=manifest["pack"]["artifact_digest"],
        publisher_lineage="tobkiri.repository",
        package_kind=PackageKind.RUNTIME_TCB,
        functions=tuple(functions),
        variants=tuple(variants),
    )


def _operation_scope(
    contract_id: str,
    operation_id: str,
    target: FunctionPrincipal,
) -> AuthorityScope:
    return AuthorityScope(
        capability="operation.invoke",
        semantics_digest=target.contract_revision_digest,
        dimensions={
            "contract": (contract_id,),
            "operation": (operation_id,),
        },
    )


def _execution_domain(
    *,
    domain_id: str,
    principal: FunctionPrincipal,
    active: ActiveDefaultProfile,
    boundary: DomainBoundary,
    channel_seed: str,
) -> ExecutionDomain:
    activation = active.activation
    return ExecutionDomain(
        domain_id=domain_id,
        profile_id=str(active.resolved.profile["profile_id"]),
        activation_id=str(activation["activation_id"]),
        boot_epoch=1,
        process_identity=f"process.{domain_id}",
        authenticated_channel_digest=authority_digest(
            {
                "channel": channel_seed,
                "activation_id": activation["activation_id"],
                "principal_id": principal.principal_id,
            }
        ),
        sandbox_profile_digest=authority_digest(
            {
                "boundary": boundary.value,
                "provider": principal.principal_id,
                "network": "denied",
                "process": "denied",
            }
        ),
        resource_namespace=f"resource.{domain_id}",
        principals=(principal,),
        boundary=boundary,
        security_epoch=int(activation["security_epoch"]),
        fencing_token=int(activation["fencing_token"]),
    )


def _register_exact_domain(
    store: AuthorityStore,
    control: Any,
    domain: ExecutionDomain,
    *,
    session_id: str,
    principal: FunctionPrincipal,
) -> None:
    existing = store.get_domain(domain.domain_id)
    if existing is None:
        control.register_execution_domain(
            domain,
            session_id=session_id,
            channel_digest=domain.authenticated_channel_digest,
            principal_ref=OpaqueAuthorityRef(principal.principal_id),
        )
        return
    if existing != domain:
        raise AuthorityDenied("captured execution domain identity changed")
    try:
        session_domain, principal_id = store.resolve_authenticated_session(session_id)
    except AuthorityDenied:
        store.bind_authenticated_session(
            session_id=session_id,
            domain=domain,
            channel_digest=domain.authenticated_channel_digest,
            principal_id=principal.principal_id,
        )
        return
    if session_domain != domain or principal_id != principal.principal_id:
        raise AuthorityDenied("authenticated session identity changed")


def _commit_pack_control_authority(
    store: AuthorityStore,
    control: Any,
    *,
    active: ActiveDefaultProfile,
    caller: FunctionPrincipal,
    target: FunctionPrincipal,
    target_domain: ExecutionDomain,
    scope: AuthorityScope,
    authority_label: str = "pack-control",
    pack_approval_revision: str | None = None,
) -> None:
    activation = active.activation
    profile = active.resolved.profile
    decided_at = datetime.fromisoformat(
        str(activation["created_at"]).replace("Z", "+00:00")
    ).timestamp()
    identity_suffix = str(activation["activation_id"]).replace(":", ".")
    operation_suffix = target.operation_id.replace(".", "-")
    authority_label = authority_label.replace("/", "-").replace(".", "-")
    approval_identity = (
        pack_approval_revision.removeprefix("sha256:")[:24]
        if pack_approval_revision is not None
        else identity_suffix
    )
    record_identity = (
        f"{identity_suffix}.{approval_identity}"
        if pack_approval_revision is not None
        else identity_suffix
    )
    approval = ApprovalRecord(
        approval_id=(f"approval.defaults.{authority_label}.{operation_suffix}.{approval_identity}"),
        snapshot_digest=canonical_digest(
            {
                "ceremony": "defaults.activate",
                "activation_id": activation["activation_id"],
                "plan_digest": activation["plan_digest"],
                "profile_authority_snapshot_digest": activation[
                    "profile_authority_snapshot_digest"
                ],
                "security_epoch": activation["security_epoch"],
                "scope": scope.to_dict(),
                "pack_approval_revision": pack_approval_revision,
            }
        ),
        actor_id=(
            "user.pack-approval"
            if pack_approval_revision is not None
            else "user.defaults-confirmation"
        ),
        decision="approved",
        decided_at=decided_at,
        caller=caller,
        target=target,
        profile_id=str(profile["profile_id"]),
        effect_bundle_digest=scope.digest,
        security_epoch=int(activation["security_epoch"]),
    )
    provider = ProviderAuthorityRecord(
        record_id=(f"provider.defaults.{authority_label}.{operation_suffix}.{record_identity}"),
        provider=target,
        execution_domain_id=target_domain.domain_id,
        execution_domain_identity_digest=target_domain.identity_digest,
        scope=scope,
        authority_mode=AuthorityMode.LEASE_ONLY,
        security_epoch=int(activation["security_epoch"]),
        trust_provenance_digest=canonical_digest(
            {
                "source": "locked-defaults-profile",
                "plan_digest": activation["plan_digest"],
                "target": target.to_dict(),
            }
        ),
        publisher_lineage="tobkiri.repository",
        host_extension_id="runtime-tcb",
        valid_from=decided_at,
        host_broker_binding="tobkiri.request-broker.v4",
    )
    grant = GrantRecord(
        grant_id=(f"grant.defaults.{authority_label}.{operation_suffix}.{record_identity}"),
        caller=caller,
        target=target,
        profile_id=str(profile["profile_id"]),
        activation_id=str(activation["activation_id"]),
        profile_authority_digest=str(activation["profile_authority_snapshot_digest"]),
        caller_publisher_lineage="tobkiri.repository",
        target_publisher_lineage="tobkiri.repository",
        scope=scope,
        lifetime=GrantLifetime.PERSISTENT_PROFILE,
        security_epoch=int(activation["security_epoch"]),
        approval_id=approval.approval_id,
        issued_at=decided_at,
    )
    existing = (
        store.get_approval(approval.approval_id),
        store.get_provider_authority(provider.record_id),
        store.get_grant(grant.grant_id),
    )
    expected = (approval, provider, grant)
    if existing == (None, None, None):
        control.commit_approval_bundle(
            approval,
            provider_authorities=(provider,),
            grants=(grant,),
        )
    elif existing != expected:
        raise AuthorityDenied("Pack catalog authority snapshot changed")


def capture_production_dispatch(
    active: ActiveDefaultProfile,
    *,
    bundle_root: Path,
    ecosystem_root: Path,
    authority_store: AuthorityStore,
    backends: BackendRegistry | None = None,
    target_backend_digests: Mapping[str, str] | None = None,
) -> V4DispatchSession:
    """Capture ProductionRuntimeV4 and its RequestBroker from verified records."""

    authority_path = authority_store.path.resolve()
    if authority_path.name != "v4.sqlite3" or authority_path.parent.name != "authority":
        raise AuthorityDenied("Authority store path is not canonical")
    authority_user_data = authority_path.parent.parent
    authority_workspace = authority_user_data / "workspaces" / "defaults"
    try:
        activation_store = ActivationStore(
            authority_workspace / "activation",
            authority_workspace,
            profile_id="defaults",
            authority=authority_store,
        )
        persisted_active = activation_store.load_active_snapshot()
    except Exception as exc:
        raise AuthorityDenied(
            "Authority store is not bound to the captured Defaults activation"
        ) from exc
    if (
        dict(persisted_active.activation) != dict(active.activation)
        or dict(persisted_active.resolved.profile) != dict(active.resolved.profile)
        or dict(persisted_active.resolved.lock) != dict(active.resolved.lock)
        or dict(persisted_active.resolved.plan) != dict(active.resolved.plan)
    ):
        raise AuthorityDenied("Authority store is not bound to the captured Defaults activation")
    active = persisted_active
    activation_suffix = str(active.activation["fencing_token"])

    catalog = BundledCatalog.load(bundle_root)
    profile = active.resolved.profile
    lock = active.resolved.lock
    plan = active.resolved.plan
    shell_id = str(profile["shell"]["pack_id"])
    shell = _shell_artifact(catalog, shell_id)
    principals: dict[str, FunctionPrincipal] = {}
    for function in shell.functions:
        for operation in function.operations:
            principal = FunctionPrincipal(
                shell.digest,
                function.implementation_digest,
                function.function_id,
                operation.revision_digest,
                operation.operation_id,
            )
            principals[principal.function_id] = principal
    for binding in plan["bindings"]:
        principal = FunctionPrincipal.from_dict(binding["function_principal"])
        principals[principal.function_id] = principal

    # Dispatch must follow the persisted immutable Profile, including exact
    # operation edges contributed by an enabled/approved optional Pack.
    edges = profile["requested_edges"]
    binding_by_key = {
        (item["contract_id"], item["operation_id"]): item for item in plan["bindings"]
    }
    ceilings: dict[tuple[str, str], AuthorityCeilings] = {}
    caller_by_operation: dict[tuple[str, str], FunctionPrincipal] = {}
    for edge in edges:
        key = (edge["contract_id"], edge["operation_id"])
        binding = binding_by_key[key]
        caller = principals[str(edge["caller_function_id"])]
        target = FunctionPrincipal.from_dict(binding["function_principal"])
        scope = AuthorityScope(
            capability="operation.invoke",
            semantics_digest=target.contract_revision_digest,
            dimensions={
                "contract": (str(edge["contract_id"]),),
                "operation": (str(edge["operation_id"]),),
            },
        )
        ceilings[(caller.principal_id, target.principal_id)] = AuthorityCeilings(
            caller_effect=scope,
            runtime_safety=scope,
            profile_admin=scope,
        )
        caller_by_operation[key] = caller

    binding_pack_ids = {str(item["pack_id"]) for item in plan["bindings"]}
    pack_roots = resolve_selected_pack_roots(
        tuple(sorted(binding_pack_ids)),
        ecosystem_root,
    )
    captured_pack_root_identities = _pack_root_identities(pack_roots)
    effective = {
        str(item["identity"]): str(item["artifact_digest"]) for item in lock["effective_set"]
    }
    runtime = ProductionRuntimeV4.capture(
        profile=profile,
        lock=lock,
        plan=plan,
        activation=active.activation,
        pack_roots=pack_roots,
        supporting_artifacts=(shell,),
        verified_effective_artifacts=effective,
        authority_ceilings=ceilings,
    )
    authority_control = runtime.composition.authority_adapter(authority_store)
    control_targets: dict[str, tuple[str, str, str]] = {}
    control_backend: PackControlBackendV4 | None = None
    control_bindings = {
        key: binding for key, binding in binding_by_key.items() if key[0] == PACK_CONTROL_CONTRACT
    }
    if control_bindings:
        control_session = capture_pack_control_session()
        for key, control_binding in sorted(control_bindings.items()):
            operation_id = key[1]
            target = FunctionPrincipal.from_dict(control_binding["function_principal"])
            target_suffix = target.principal_id.removeprefix("sha256:")[:24]
            target_domain = _execution_domain(
                domain_id=f"domain.provider.{target_suffix}.{activation_suffix}",
                principal=target,
                active=active,
                boundary=DomainBoundary.DEDICATED_PROCESS,
                channel_seed=f"pack-control-provider:{operation_id}",
            )
            _register_exact_domain(
                authority_store,
                authority_control,
                target_domain,
                session_id=(f"session.provider.pack-control.{operation_id}.{activation_suffix}"),
                principal=target,
            )
            scope = _operation_scope(PACK_CONTROL_CONTRACT, operation_id, target)
            caller = caller_by_operation[key]
            _commit_pack_control_authority(
                authority_store,
                authority_control,
                active=active,
                caller=caller,
                target=target,
                target_domain=target_domain,
                scope=scope,
            )
            control_targets[operation_id] = (
                target.principal_id,
                target.function_implementation_digest,
                target_domain.domain_id,
            )
        backend_digest = canonical_digest(
            {
                "backend": "tobkiri.host-pack-control.v4",
                "targets": {
                    operation_id: list(target) for operation_id, target in control_targets.items()
                },
                "profile_id": profile["profile_id"],
                "plan_digest": plan["plan_digest"],
                "security_epoch": active.activation["security_epoch"],
            }
        )
        control_backend = PackControlBackendV4(
            session=control_session,
            targets=control_targets,
            backend_digest=backend_digest,
        )
        target_backend_digests = {
            **dict(target_backend_digests or {}),
            **{target[0]: backend_digest for target in control_targets.values()},
        }
    static_edge_keys = {
        (str(edge["contract_id"]), str(edge["operation_id"]))
        for edge in catalog.profiles["defaults"]["requested_edges"]
    }
    dynamic_bindings = {
        key: binding
        for key, binding in binding_by_key.items()
        if key not in static_edge_keys and key[0] != PACK_CONTROL_CONTRACT
    }
    optional_pack_ids = {
        str(item["pack_id"])
        for item in profile.get("packs", ())
        if str(item["pack_id"]) not in catalog.packs
    }
    pack_by_function = {
        str(binding["function_principal"]["function_id"]): str(binding["pack_id"])
        for binding in plan["bindings"]
    }
    edge_by_key = {
        (str(edge["contract_id"]), str(edge["operation_id"])): edge
        for edge in profile["requested_edges"]
    }
    captured_dynamic_approvals: dict[str, str] = {}
    for key, dynamic_binding in sorted(dynamic_bindings.items()):
        contract_id, operation_id = key
        target_pack_id = str(dynamic_binding["pack_id"])
        caller_pack_id = pack_by_function.get(
            str(edge_by_key[key]["caller_function_id"]),
            "",
        )
        approval_pack_ids = {
            pack_id for pack_id in (target_pack_id, caller_pack_id) if pack_id in optional_pack_ids
        }
        if len(approval_pack_ids) != 1:
            # Dynamic authority must trace to exactly one approved optional
            # Pack, either as the operation owner or as the signed direct
            # dependency caller.  Never mint authority from dependency
            # presence alone.
            continue
        approval_pack_id = next(iter(approval_pack_ids))
        try:
            pack_approval = capture_valid_pack_approval(approval_pack_id)
            pack_approval_revision = str(pack_approval["approval_revision"])
            captured_dynamic_approvals[approval_pack_id] = pack_approval_revision
        except Exception:
            # The immutable plan may still contain a previously selected Pack,
            # but missing/corrupt/stale approval must never recreate authority.
            continue
        target = FunctionPrincipal.from_dict(dynamic_binding["function_principal"])
        target_suffix = target.principal_id.removeprefix("sha256:")[:24]
        target_domain = _execution_domain(
            domain_id=f"domain.provider.{target_suffix}.{activation_suffix}",
            principal=target,
            active=active,
            boundary=DomainBoundary.DEDICATED_PROCESS,
            channel_seed=f"dynamic-provider:{contract_id}:{operation_id}",
        )
        _register_exact_domain(
            authority_store,
            authority_control,
            target_domain,
            session_id=f"session.provider.dynamic.{target_suffix}.{activation_suffix}",
            principal=target,
        )
        caller = caller_by_operation[key]
        _commit_pack_control_authority(
            authority_store,
            authority_control,
            active=active,
            caller=caller,
            target=target,
            target_domain=target_domain,
            scope=_operation_scope(contract_id, operation_id, target),
            authority_label="dynamic-pack",
            pack_approval_revision=pack_approval_revision,
        )
    registered_backends = tuple((backends or BackendRegistry(())).registered)
    if not any(item.status.backend_id == _PYTHON_PACK_BACKEND_ID for item in registered_backends):
        # The descriptor remains unavailable unless the composition root
        # supplies a real authenticated supervisor.  Registering the exact
        # disabled identity preserves a stable user-facing diagnostic without
        # substituting in-process Python execution.
        registered_backends += (_UnavailablePythonPackBackend(),)
    if control_backend is not None:
        if any(item.status.backend_id == PACK_CATALOG_BACKEND_ID for item in registered_backends):
            raise AuthorityDenied("Pack control backend identity is duplicated")
        registered_backends += (control_backend,)
    backend_registry = BackendRegistry(registered_backends)
    target_backend_digests = dict(target_backend_digests or {})
    for binding in plan["bindings"]:
        target = FunctionPrincipal.from_dict(binding["function_principal"])
        if target.principal_id in target_backend_digests:
            continue
        try:
            resolved_binding = runtime.composition.catalog.resolve(
                binding["contract_id"],
                binding["operation_id"],
                ">=1,<2",
            )
            selected_backend = backend_registry.select(resolved_binding)
        except Exception:
            continue
        target_backend_digests[target.principal_id] = selected_backend.status.backend_digest
    broker = runtime.broker(
        authority_store=authority_store,
        adapters=AdapterPlanner(()),
        adapter_executor=_NoAdapterExecution(),
        backends=backend_registry,
        materialization=MaterializationCoordinator(),
        admission=_FiniteAdmission(),
        reconciliation=InMemoryReconciliationStore(),
        authority_adapter=authority_control,
    )
    activation_digest = canonical_digest(active.activation)
    target_by_operation = {
        (item["contract_id"], item["operation_id"]): FunctionPrincipal.from_dict(
            item["function_principal"]
        )
        for item in plan["bindings"]
    }

    caller_sessions: set[str] = set()
    caller_sessions_lock = threading.RLock()

    def context_for(contract_id: str, operation_id: str, session_id: str) -> RequestContext:
        key = (contract_id, operation_id)
        caller = caller_by_operation[key]
        target = target_by_operation[key]
        target_suffix = target.principal_id.removeprefix("sha256:")[:24]
        # One authenticated panel session may invoke operations whose
        # resolved Shell caller principals differ.  Authority session
        # bindings are principal-specific, so include that exact caller in
        # the Host-derived session identity instead of reusing a session
        # already bound to another caller.
        caller_identity_suffix = caller.principal_id.removeprefix("sha256:")[:24]
        authority_session_id = f"{session_id}.{caller_identity_suffix}.{activation_suffix}"
        caller_suffix = canonical_digest(
            {"session_id": authority_session_id, "caller": caller.principal_id}
        ).removeprefix("sha256:")[:24]
        context = RequestContext(
            request_id="request." + secrets.token_hex(16),
            trace_id="trace." + secrets.token_hex(16),
            caller_principal=OpaqueAuthorityRef(caller.principal_id),
            profile_id=str(profile["profile_id"]),
            activation_id=str(active.activation["activation_id"]),
            activation_digest=activation_digest,
            plan_digest=str(plan["plan_digest"]),
            security_epoch=int(active.activation["security_epoch"]),
            caller_session_id=authority_session_id,
            caller_domain_id=f"domain.panel.{caller_suffix}.{activation_suffix}",
            caller_boot_epoch=1,
            target_domain_id=f"domain.provider.{target_suffix}.{activation_suffix}",
            target_boot_epoch=1,
            target_backend_digest=target_backend_digests.get(
                target.principal_id,
                canonical_digest(
                    {
                        "backend": "captured-but-not-materialized",
                        "target": target.principal_id,
                    }
                ),
            ),
            profile_authority_digest=str(active.activation["profile_authority_snapshot_digest"]),
            fencing_token=int(active.activation["fencing_token"]),
            handle_namespace=f"activation.{target_suffix}",
        )
        with caller_sessions_lock:
            if authority_session_id not in caller_sessions:
                caller_domain = _execution_domain(
                    domain_id=context.caller_domain_id,
                    principal=caller,
                    active=active,
                    boundary=DomainBoundary.UNPRIVILEGED_WORKER,
                    channel_seed=f"panel:{session_id}",
                )
                _register_exact_domain(
                    authority_store,
                    authority_control,
                    caller_domain,
                    session_id=authority_session_id,
                    principal=caller,
                )
                caller_sessions.add(authority_session_id)
        return context

    providers: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for binding in plan["bindings"]:
        resolved_binding = broker._catalog.resolve(
            binding["contract_id"],
            binding["operation_id"],
            ">=1,<2",
        )
        backend_error: str | None = None
        try:
            selected_backend = broker._backends.select(resolved_binding)
        except Exception as error:
            selected_backend = None
            backend_error = str(error) or "production backend is unavailable"
        function_principal = binding["function_principal"]
        providers.setdefault(binding["contract_id"], ())
        providers[binding["contract_id"]] += (
            {
                "provider_id": function_principal["function_id"],
                "function_id": function_principal["function_id"],
                "principal_id": resolved_binding.principal_ref.value,
                "implementation_digest": resolved_binding.function.implementation_digest,
                "contract_id": binding["contract_id"],
                "operation_id": binding["operation_id"],
                "artifact_digest": binding["artifact_digest"],
                **(
                    {
                        "backend_id": selected_backend.status.backend_id,
                        "backend_digest": selected_backend.status.backend_digest,
                    }
                    if selected_backend is not None
                    else {}
                ),
                **(
                    {"backend_unavailable_reason": backend_error}
                    if backend_error is not None
                    else {}
                ),
                "profile_id": profile["profile_id"],
                "plan_digest": plan["plan_digest"],
            },
        )

    captured_activation = dict(active.activation)
    captured_profile = dict(active.resolved.profile)
    captured_lock = dict(active.resolved.lock)
    captured_plan = dict(active.resolved.plan)

    def assert_current_capture() -> None:
        current = activation_store.load_active_snapshot()
        if (
            dict(current.activation) != captured_activation
            or dict(current.resolved.profile) != captured_profile
            or dict(current.resolved.lock) != captured_lock
            or dict(current.resolved.plan) != captured_plan
            or authority_store.security_epoch != int(captured_activation["security_epoch"])
        ):
            raise AuthorityDenied("captured Defaults activation is stale")
        if _pack_root_identities(pack_roots) != captured_pack_root_identities:
            raise AuthorityDenied("captured Pack filesystem identity changed")
        for pack_id, approval_revision in captured_dynamic_approvals.items():
            try:
                current_approval = capture_valid_pack_approval(pack_id)
            except Exception as error:
                raise AuthorityDenied("captured optional Pack approval is unavailable") from error
            if current_approval.get("approval_revision") != approval_revision:
                raise AuthorityDenied("captured optional Pack approval changed")

    return runtime.dispatch_session(
        broker=broker,
        context_for=context_for,
        effect_scope_for=lambda contract_id, operation_id, _payload: {
            "capability": "operation.invoke",
            "semantics_digest": target_by_operation[
                (contract_id, operation_id)
            ].contract_revision_digest,
            "dimensions": {
                "contract": [contract_id],
                "operation": [operation_id],
            },
        },
        providers=providers,
        authority_control=authority_control,
        current_capture_check=assert_current_capture,
        owned_authority_store=authority_store,
    )


__all__ = ["capture_production_dispatch"]
