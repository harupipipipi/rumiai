"""Finite, restart-safe capture of the bundled Defaults Profile v4."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ecosystem.defaultspack.domain.runtime_v4 import (
    ActivationStore,
    ActiveDefaultProfile,
    BundledCatalog,
    ProfileResolutionDenied,
    ResolvedDefaultProfile,
    resolve_default_profile,
)
from tobkiri_protocol.canonical import canonical_digest

from ..authority.v4 import AuthorityStore
from ..authority.v4_models import authority_digest
from ..env_compat import read_migrated_env


def runtime_user_data_root(base_dir: Path | None = None) -> Path:
    """Return the configured Host state root without an authority fallback."""
    configured = read_migrated_env("TOBKIRI_USER_DATA", "RUMI_USER_DATA")
    if configured:
        return Path(configured).resolve()
    runtime_root = base_dir or Path(__file__).resolve().parents[2]
    return (runtime_root / "user_data").resolve()


def _bundle_root(base_dir: Path | None = None) -> Path:
    del base_dir
    runtime_root = Path(__file__).resolve().parents[2]
    return runtime_root / "ecosystem" / "defaultspack" / "v4"


def _edge_key(edge: Mapping[str, Any]) -> str:
    return "|".join(
        str(edge[field])
        for field in (
            "caller_function_id",
            "target_provider_id",
            "contract_id",
            "operation_id",
        )
    )


def _authority_reference(edge: Mapping[str, Any], snapshot_digest: str) -> str:
    digest = canonical_digest(
        {
            "schema": "io.tobkiri.profile-authority-edge.v1",
            "edge": _edge_key(edge),
            "profile_authority_snapshot_digest": snapshot_digest,
        }
    )
    return f"authority-ref:{digest.removeprefix('sha256:')}"


def _authority_snapshot_digest(
    store: AuthorityStore, bundle_lock_digest: str
) -> str:
    epoch = store.security_epoch_record
    return canonical_digest(
        {
            "schema": "io.tobkiri.profile-authority-snapshot.v1",
            "security_epoch": epoch.value,
            "security_epoch_reason_digest": epoch.reason_digest,
            "bundle_lock_digest": bundle_lock_digest,
            "grant_import": "none",
        }
    )


def _genesis_authority_snapshot_digest(bundle_lock_digest: str) -> str:
    """Return the read-only snapshot a new Authority store will initialize."""

    return canonical_digest(
        {
            "schema": "io.tobkiri.profile-authority-snapshot.v1",
            "security_epoch": 1,
            "security_epoch_reason_digest": authority_digest({"reason": "genesis"}),
            "bundle_lock_digest": bundle_lock_digest,
            "grant_import": "none",
        }
    )


def _resolve_candidate(
    *, base_dir: Path | None = None
) -> tuple[ResolvedDefaultProfile, dict[str, Any]]:
    """Resolve the finite Defaults candidate without writing first-start state."""

    user_data = runtime_user_data_root(base_dir)
    bundle_root = _bundle_root(base_dir)
    catalog = BundledCatalog.load(bundle_root)
    bundle_lock_digest = "sha256:" + hashlib.sha256(
        (bundle_root / "bundle.lock.json").read_bytes()
    ).hexdigest()
    authority_path = user_data / "authority" / "v4.sqlite3"
    if authority_path.is_file():
        authority = AuthorityStore(authority_path)
        security_epoch = authority.security_epoch
        snapshot_digest = _authority_snapshot_digest(authority, bundle_lock_digest)
    elif authority_path.exists():
        raise ProfileResolutionDenied("Authority store path is not a regular file")
    else:
        security_epoch = 1
        snapshot_digest = _genesis_authority_snapshot_digest(bundle_lock_digest)
    source_profile = catalog.profiles.get("defaults")
    if source_profile is None:
        raise ProfileResolutionDenied("bundled defaults Profile is missing")
    authority_bindings = {
        _edge_key(edge): _authority_reference(edge, snapshot_digest)
        for edge in source_profile["requested_edges"]
    }
    verified_artifacts = {
        str(manifest["pack"]["artifact_digest"])
        for manifest in catalog.packs.values()
    }
    resolved = resolve_default_profile(
        catalog,
        "defaults",
        approved_artifact_digests=verified_artifacts,
        authority_snapshot_digest=snapshot_digest,
        authority_bindings=authority_bindings,
        security_epoch=security_epoch,
    )
    confirmation = {
        "confirmation_api_version": "io.tobkiri.defaults-confirmation.v1",
        "operation_id": "defaults.activate",
        "profile_id": "defaults",
        "catalog_revision": resolved.profile["catalog_revision"],
        "profile_revision": resolved.plan["profile_revision"],
        "plan_digest": resolved.plan["plan_digest"],
        "authority_snapshot_digest": snapshot_digest,
        "security_epoch": security_epoch,
        "base": dict(resolved.plan["base"]),
        "shell": dict(resolved.plan["shell"]),
        "bindings": [dict(binding) for binding in resolved.plan["bindings"]],
    }
    confirmation["confirmation_digest"] = canonical_digest(confirmation)
    return resolved, confirmation


def prepare_default_profile_confirmation(
    *, base_dir: Path | None = None
) -> dict[str, Any]:
    """Return an exact, read-only confirmation bound to the current catalog."""

    _resolved, confirmation = _resolve_candidate(base_dir=base_dir)
    return confirmation


def active_default_profile_exists(*, base_dir: Path | None = None) -> bool:
    """Return whether the canonical activation pointer physically exists."""

    pointer = (
        runtime_user_data_root(base_dir)
        / "profiles"
        / "defaults"
        / "v4"
        / "active.json"
    )
    return pointer.is_file()


def activation_audit_receipt(
    active: ActiveDefaultProfile, *, base_dir: Path | None = None
) -> dict[str, Any]:
    """Return the committed Authority reservation bound to an activation."""

    authority = AuthorityStore(
        runtime_user_data_root(base_dir) / "authority" / "v4.sqlite3"
    )
    reservation = authority.active_activation_reservation(
        str(active.activation["activation_id"])
    )
    if reservation is None or (
        reservation.get("state") != "active"
        or reservation.get("plan_digest") != active.activation["plan_digest"]
        or reservation.get("fencing_token")
        != active.activation["fencing_token"]
    ):
        raise ProfileResolutionDenied("activation audit commit is unavailable")
    return {
        "reservation_id": str(reservation["reservation_id"]),
        "state": "committed",
        "activation_id": str(reservation["activation_id"]),
        "fencing_token": int(reservation["fencing_token"]),
    }


def capture_default_profile(
    *,
    base_dir: Path | None = None,
    confirmation: Mapping[str, Any] | None = None,
) -> ActiveDefaultProfile:
    """Load or create the sole verified bundled Defaults activation.

    Creation is one finite transaction: verify the locked bundle, capture the
    Authority Kernel epoch, resolve the named ``defaults`` Profile, and atomically
    activate it.  Restart only reloads the digest-bound activation envelope.
    """
    user_data = runtime_user_data_root(base_dir)
    state_root = user_data / "profiles" / "defaults" / "v4"
    active_pointer = state_root / "active.json"
    if active_pointer.is_file():
        if confirmation is not None:
            raise ProfileResolutionDenied("Defaults activation confirmation was replayed")
        workspace = user_data / "workspaces" / "defaults"
        authority = AuthorityStore(user_data / "authority" / "v4.sqlite3")
        store = ActivationStore(
            state_root,
            workspace,
            profile_id="defaults",
            authority=authority,
        )
        return store.load_active_snapshot()
    if active_pointer.exists():
        raise ProfileResolutionDenied("active activation pointer is not a regular file")
    if confirmation is None:
        raise ProfileResolutionDenied(
            "explicit Defaults activation confirmation is required"
        )

    resolved, expected_confirmation = _resolve_candidate(base_dir=base_dir)
    if dict(confirmation) != expected_confirmation:
        raise ProfileResolutionDenied(
            "Defaults activation confirmation is stale or tampered"
        )
    workspace = user_data / "workspaces" / "defaults"
    workspace.mkdir(parents=True, exist_ok=True)
    authority = AuthorityStore(user_data / "authority" / "v4.sqlite3")
    store = ActivationStore(
        state_root,
        workspace,
        profile_id="defaults",
        authority=authority,
    )
    store.recover()
    activation_id = (
        "activation:defaults-" + resolved.plan["plan_digest"].removeprefix("sha256:")[:16]
    )
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    store.activate(
        resolved,
        activation_id=activation_id,
        created_at=created_at,
    )
    return store.load_active_snapshot()


__all__ = [
    "activation_audit_receipt",
    "active_default_profile_exists",
    "capture_default_profile",
    "prepare_default_profile_confirmation",
    "runtime_user_data_root",
]
