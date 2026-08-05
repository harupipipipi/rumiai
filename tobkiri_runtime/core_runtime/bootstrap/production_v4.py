"""Assemble the sole live Pack v4 composition from one active snapshot."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Mapping

from ecosystem.defaultspack.domain.runtime_v4 import ActiveDefaultProfile, BundledCatalog
from tobkiri_host.admission import AdmissionEstimate, QueueScope, ResourceReservation
from tobkiri_host.backends import BackendRegistry
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
from tobkiri_host.runtime import ProductionRuntimeV4, V4DispatchSession
from tobkiri_protocol.canonical import canonical_digest

from ..authority.v4 import AuthorityScope, AuthorityStore, FunctionPrincipal


class _NoAdapterExecution:
    def execute(
        self, adapter: StructuralAdapter, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
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

    edges = catalog.profiles["defaults"]["requested_edges"]
    binding_by_key = {
        (item["contract_id"], item["operation_id"]): item
        for item in plan["bindings"]
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
    effective = {
        str(item["identity"]): str(item["artifact_digest"])
        for item in lock["effective_set"]
    }
    runtime = ProductionRuntimeV4.capture(
        profile=profile,
        lock=lock,
        plan=plan,
        activation=active.activation,
        pack_roots={
            pack_id: ecosystem_root / pack_id for pack_id in binding_pack_ids
        },
        supporting_artifacts=(shell,),
        verified_effective_artifacts=effective,
        authority_ceilings=ceilings,
    )
    authority_control = runtime.composition.authority_adapter(authority_store)
    broker = runtime.broker(
        authority_store=authority_store,
        adapters=AdapterPlanner(()),
        adapter_executor=_NoAdapterExecution(),
        backends=backends or BackendRegistry(()),
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

    def context_for(
        contract_id: str, operation_id: str, session_id: str
    ) -> RequestContext:
        key = (contract_id, operation_id)
        caller = caller_by_operation[key]
        target = target_by_operation[key]
        target_suffix = target.principal_id.removeprefix("sha256:")[:24]
        caller_suffix = canonical_digest(
            {"session_id": session_id, "caller": caller.principal_id}
        ).removeprefix("sha256:")[:24]
        return RequestContext(
            request_id="request." + secrets.token_hex(16),
            trace_id="trace." + secrets.token_hex(16),
            caller_principal=OpaqueAuthorityRef(caller.principal_id),
            profile_id=str(profile["profile_id"]),
            activation_id=str(active.activation["activation_id"]),
            activation_digest=activation_digest,
            plan_digest=str(plan["plan_digest"]),
            security_epoch=int(active.activation["security_epoch"]),
            caller_session_id=session_id,
            caller_domain_id=f"domain.panel.{caller_suffix}",
            caller_boot_epoch=1,
            target_domain_id=f"domain.provider.{target_suffix}",
            target_boot_epoch=1,
            target_backend_digest=(
                target_backend_digests or {}
            ).get(
                target.principal_id,
                canonical_digest(
                    {
                        "backend": "captured-but-not-materialized",
                        "target": target.principal_id,
                    }
                ),
            ),
            profile_authority_digest=str(
                active.activation["profile_authority_snapshot_digest"]
            ),
            fencing_token=int(active.activation["fencing_token"]),
            handle_namespace=f"activation.{target_suffix}",
        )

    providers: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for binding in plan["bindings"]:
        providers.setdefault(binding["contract_id"], ())
        providers[binding["contract_id"]] += (
            {
                "provider_id": binding["function_principal"]["function_id"],
                "contract_id": binding["contract_id"],
                "operation_id": binding["operation_id"],
                "artifact_digest": binding["artifact_digest"],
                "profile_id": profile["profile_id"],
                "plan_digest": plan["plan_digest"],
            },
        )
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
    )


__all__ = ["capture_production_dispatch"]
