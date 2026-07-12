"""Revision-bound access to the active immutable resolved profile."""

from __future__ import annotations

from contextvars import ContextVar, Token

from .resolved_profile import ResolvedProfile

_ACTIVE_PROFILE: ContextVar[ResolvedProfile | None] = ContextVar(
    "rumi_active_resolved_profile",
    default=None,
)


def activate_resolved_profile(plan: ResolvedProfile) -> Token[ResolvedProfile | None]:
    """Bind subsequent loaders and calls to one immutable plan revision."""
    return _ACTIVE_PROFILE.set(plan)


def restore_resolved_profile(token: Token[ResolvedProfile | None]) -> None:
    """Restore the prior plan after a revision-bound execution scope."""
    _ACTIVE_PROFILE.reset(token)


def active_resolved_profile() -> ResolvedProfile | None:
    """Return the current plan, or None before startup resolution."""
    return _ACTIVE_PROFILE.get()


def effective_pack_ids() -> frozenset[str]:
    """Return the only pack scope runtime resource loaders may consume."""
    plan = active_resolved_profile()
    if plan is None:
        return frozenset()
    return frozenset(plan.effective_pack_set)


def require_effective_pack(pack_id: str) -> None:
    """Fail closed when a caller tries to consume an out-of-plan pack."""
    plan = active_resolved_profile()
    if plan is None:
        raise RuntimeError("resolved profile is not active")
    if pack_id not in plan.effective_pack_set:
        raise PermissionError(
            f"pack is outside resolved profile {plan.plan_hash}: {pack_id}"
        )
