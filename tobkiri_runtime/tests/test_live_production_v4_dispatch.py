"""Clean-home proof for the sole ProductionRuntimeV4/RequestBroker path."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core_runtime.authority.v4 import (
    ApprovalRecord,
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
from core_runtime.bootstrap.production_v4 import capture_production_dispatch
from core_runtime.bootstrap.profile_capture import capture_default_profile
from tobkiri_host.backends import (
    REQUIRED_PRODUCTION_GATES,
    BackendRegistry,
    BackendStatus,
)
from tobkiri_host.effects import ProviderOutcome
from tobkiri_host.errors import AuthorizationError
from tobkiri_host.models import ExecutionKind, OpaqueAuthorityRef, RuntimeEvidence


def _digest(seed: str) -> str:
    return authority_digest({"seed": seed})


class _CapturedBackend:
    def __init__(self, backend_digest: str) -> None:
        self.status = BackendStatus(
            backend_id="tobkiri.python-pack-v4",
            execution_kind=ExecutionKind.PACK_VM,
            platform="any",
            backend_digest=backend_digest,
            production_enabled=True,
            conformance_only=False,
            satisfied_gates=REQUIRED_PRODUCTION_GATES,
        )
        self.target_domain_id = ""
        self.target_executable_digest = ""

    def materialize(self, binding, reservation_id: str) -> RuntimeEvidence:
        assert reservation_id
        assert binding.variant.backend == self.status.backend_id
        return RuntimeEvidence(
            domain_ref=OpaqueAuthorityRef(self.target_domain_id),
            executable_digest=self.target_executable_digest,
            backend_digest=self.status.backend_digest,
            authenticated_channel=True,
            nonce_fresh=True,
        )

    def invoke(self, request: object) -> ProviderOutcome:
        assert request is not None
        return ProviderOutcome({"ok": True})

    def cancel(self, request_id: str) -> None:
        assert request_id

    def terminate(self, domain_id: str) -> None:
        assert domain_id


def _domain(
    *,
    domain_id: str,
    principal: FunctionPrincipal,
    active,
    boundary: DomainBoundary,
) -> ExecutionDomain:
    return ExecutionDomain(
        domain_id=domain_id,
        profile_id="defaults",
        activation_id=active.activation["activation_id"],
        boot_epoch=1,
        process_identity="process." + domain_id,
        authenticated_channel_digest=_digest("channel:" + domain_id),
        sandbox_profile_digest=_digest("sandbox:" + domain_id),
        resource_namespace="resource." + domain_id,
        principals=(principal,),
        boundary=boundary,
        security_epoch=active.activation["security_epoch"],
        fencing_token=active.activation["fencing_token"],
    )


def test_clean_home_broker_dispatches_then_revocation_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_data = tmp_path / "clean-home"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    active = capture_default_profile()
    binding = next(
        item
        for item in active.resolved.plan["bindings"]
        if item["contract_id"] == "conversation.turn.v1"
    )
    target = FunctionPrincipal.from_dict(binding["function_principal"])
    backend = _CapturedBackend(_digest("backend"))
    store = AuthorityStore(user_data / "authority" / "v4.sqlite3")
    session = capture_production_dispatch(
        active,
        bundle_root=Path(__file__).resolve().parents[1]
        / "ecosystem"
        / "defaultspack"
        / "v4",
        ecosystem_root=Path(__file__).resolve().parents[1] / "ecosystem",
        authority_store=store,
        backends=BackendRegistry((backend,)),
        target_backend_digests={target.principal_id: backend.status.backend_digest},
    )
    control = session.authority_control
    assert control is not None
    session_id = "session.panel.clean-home"
    context = session.context_for("conversation.turn.v1", "complete", session_id)
    caller = control._principals.resolve_principal(context.caller_principal)
    resolved_target = control._principals.resolve_principal(
        OpaqueAuthorityRef(target.principal_id)
    )
    assert resolved_target == target
    caller_domain = _domain(
        domain_id=context.caller_domain_id,
        principal=caller,
        active=active,
        boundary=DomainBoundary.UNPRIVILEGED_WORKER,
    )
    target_domain = _domain(
        domain_id=context.target_domain_id,
        principal=target,
        active=active,
        boundary=DomainBoundary.DEDICATED_PROCESS,
    )
    control.register_execution_domain(
        caller_domain,
        session_id=session_id,
        channel_digest=caller_domain.authenticated_channel_digest,
        principal_ref=context.caller_principal,
    )
    control.register_execution_domain(
        target_domain,
        session_id="session.provider.clean-home",
        channel_digest=target_domain.authenticated_channel_digest,
        principal_ref=OpaqueAuthorityRef(target.principal_id),
    )
    backend.target_domain_id = target_domain.domain_id
    backend.target_executable_digest = target.function_implementation_digest

    scope = AuthorityScope.from_dict(
        session.effect_scope_for("conversation.turn.v1", "complete", {})
    )
    now = time.time() - 1.0
    approval = ApprovalRecord(
        approval_id="approval.clean-home",
        snapshot_digest=_digest("approval-snapshot"),
        actor_id="user.clean-home",
        decision="approved",
        decided_at=now,
        caller=caller,
        target=target,
        profile_id="defaults",
        effect_bundle_digest=scope.digest,
        security_epoch=active.activation["security_epoch"],
    )
    provider = ProviderAuthorityRecord(
        record_id="provider.clean-home",
        provider=target,
        execution_domain_id=target_domain.domain_id,
        execution_domain_identity_digest=target_domain.identity_digest,
        scope=scope,
        authority_mode=AuthorityMode.LEASE_ONLY,
        security_epoch=active.activation["security_epoch"],
        trust_provenance_digest=_digest("repository-trust"),
        publisher_lineage="tobkiri.repository",
        host_extension_id="runtime-tcb",
        valid_from=now,
        host_broker_binding="tobkiri.request-broker.v4",
    )
    grant = GrantRecord(
        grant_id="grant.clean-home",
        caller=caller,
        target=target,
        profile_id="defaults",
        activation_id=active.activation["activation_id"],
        profile_authority_digest=active.activation[
            "profile_authority_snapshot_digest"
        ],
        caller_publisher_lineage="tobkiri.repository",
        target_publisher_lineage="tobkiri.repository",
        scope=scope,
        lifetime=GrantLifetime.PERSISTENT_PROFILE,
        security_epoch=active.activation["security_epoch"],
        approval_id=approval.approval_id,
        issued_at=now,
        max_uses=2,
    )
    control.commit_approval_bundle(
        approval,
        provider_authorities=(provider,),
        grants=(grant,),
    )
    persisted = store.list_grants()
    current_context = session.context_for(
        "conversation.turn.v1", "complete", session_id
    )
    current_caller = control._principals.resolve_principal(
        current_context.caller_principal
    )
    assert len(persisted) == 1
    assert persisted[0].caller == current_caller
    assert persisted[0].target == target
    assert persisted[0].profile_id == current_context.profile_id
    assert persisted[0].activation_id == current_context.activation_id
    assert (
        persisted[0].profile_authority_digest
        == current_context.profile_authority_digest
    )
    assert persisted[0].security_epoch == current_context.security_epoch
    assert persisted[0].issued_at <= time.time()
    assert persisted[0].expires_at is None
    assert persisted[0].revoked is False
    assert not store.is_revoked("grant", grant.grant_id)
    assert scope.is_subset_of(persisted[0].scope)
    assert store.get_approval(approval.approval_id) == approval
    translated, translated_scope = control._translate_query(
        current_context,
        OpaqueAuthorityRef(target.principal_id),
        _digest("request"),
        scope.to_dict(),
    )
    assert translated.target == target
    assert translated_scope.is_subset_of(persisted[0].scope)
    selected = control._kernel._select_grant(
        context=translated,
        caller=current_caller,
        request_scope=translated_scope,
        now=time.time(),
    )
    assert selected == grant

    try:
        assert session.invoke(
            "conversation.turn.v1",
            "complete",
            {"_session_id": session_id, "messages": [{"role": "user"}]},
        ) == {"ok": True}
        assert store.grant_usage(grant.grant_id) == (0, 1)
        control.revoke(
            target_kind="grant",
            target_id=grant.grant_id,
            reason="test explicit revoke",
        )
        with pytest.raises(AuthorizationError, match="static authorization failed"):
            session.invoke(
                "conversation.turn.v1",
                "complete",
                {"_session_id": session_id, "messages": [{"role": "user"}]},
            )
    finally:
        session.broker.close()

    assert not (user_data / "settings" / "startup_profiles.json").exists()
