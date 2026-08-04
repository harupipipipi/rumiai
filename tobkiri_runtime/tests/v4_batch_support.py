"""Small fixtures for the residual Pack v4 contract migration batch."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from core_runtime.authority.v4 import AuthorityDenied, AuthorityScope, LeaseState

from tests.test_authority_v4_lifecycle import _Harness, _digest


def harness(tmp_path: Path, **kwargs: Any) -> _Harness:
    """Build the canonical two-domain Authority Kernel fixture."""
    return _Harness(tmp_path, **kwargs)


def bounded_scope(*, path: str = "/safe", max_bytes: int = 1024) -> AuthorityScope:
    """Return a deliberately bounded request scope."""
    return AuthorityScope(
        capability="host.http",
        semantics_digest=_digest("e"),
        dimensions={"path": (path,), "method": ("GET",)},
        quotas={"max_bytes": max_bytes},
    )


def altered_context(h: _Harness, **changes: Any):
    """Return a context mutation used to prove payload binding is exact."""
    return h.context(**changes)


def assert_payload_mutations_denied(h: _Harness) -> None:
    """Assert caller, target, activation, session, and epoch are host-bound."""
    impostor = replace(h.target, operation_id="admin")
    mutations = (
        {"target": impostor},
        {"activation_id": "activation-attacker"},
        {"caller_session_id": "session-attacker"},
        {"security_epoch": 2},
        {"plan_digest": _digest("attacker-plan")},
    )
    for mutation in mutations:
        try:
            h.kernel.authorize(altered_context(h, **mutation), h.scope)
        except AuthorityDenied:
            continue
        raise AssertionError(f"payload mutation was accepted: {mutation}")
    assert h.store.grant_usage(h.grant.grant_id) == (0, 0)


def assert_lease_is_single_use(h: _Harness) -> None:
    """Assert reserve, dispatch, finish, and replay are durable and ordered."""
    result = h.kernel.authorize(h.context(), h.scope)
    lease = h.kernel.dispatch(
        result.lease_token,
        target_domain_id=h.target_domain.domain_id,
        target_boot_epoch=h.target_domain.boot_epoch,
        request_digest=h.context().request_digest,
    )
    h.kernel.finish(
        lease.lease_id,
        state=LeaseState.COMMITTED,
        outcome_digest=_digest("batch-outcome"),
    )
    try:
        h.kernel.dispatch(
            result.lease_token,
            target_domain_id=h.target_domain.domain_id,
            target_boot_epoch=h.target_domain.boot_epoch,
            request_digest=h.context().request_digest,
        )
    except AuthorityDenied:
        pass
    else:
        raise AssertionError("a committed InvocationLease was replayed")
    assert h.store.grant_usage(h.grant.grant_id) == (0, 1)


def assert_legacy_registry_fails_closed() -> None:
    """The retained offline registry shape cannot discover runtime Packs."""
    from backend_core.ecosystem.registry import (
        LegacyRegistryUnavailable,
        Registry,
        get_registry,
        reload_registry,
        resolve_load_order,
    )

    with pytest.raises(LegacyRegistryUnavailable):
        Registry().load_all_packs()
    with pytest.raises(LegacyRegistryUnavailable):
        get_registry()
    with pytest.raises(LegacyRegistryUnavailable):
        reload_registry()
    with pytest.raises(LegacyRegistryUnavailable):
        resolve_load_order(())


__all__ = [
    "assert_lease_is_single_use",
    "assert_payload_mutations_denied",
    "altered_context",
    "bounded_scope",
    "harness",
    "assert_legacy_registry_fails_closed",
]
