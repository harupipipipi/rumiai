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
    resolve_default_profile,
)
from tobkiri_protocol.canonical import canonical_digest

from ..authority.v4 import AuthorityStore
from ..env_compat import read_migrated_env


def runtime_user_data_root(base_dir: Path | None = None) -> Path:
    """Return the configured Host state root without an authority fallback."""
    configured = read_migrated_env("TOBKIRI_USER_DATA", "RUMI_USER_DATA")
    if configured:
        return Path(configured).resolve()
    runtime_root = base_dir or Path(__file__).resolve().parents[2]
    return (runtime_root / "user_data").resolve()


def _bundle_root(base_dir: Path | None = None) -> Path:
    runtime_root = base_dir or Path(__file__).resolve().parents[2]
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


def capture_default_profile(
    *, base_dir: Path | None = None
) -> ActiveDefaultProfile:
    """Load or create the sole verified bundled Defaults activation.

    Creation is one finite transaction: verify the locked bundle, capture the
    Authority Kernel epoch, resolve the named ``defaults`` Profile, and atomically
    activate it.  Restart only reloads the digest-bound activation envelope.
    """
    user_data = runtime_user_data_root(base_dir)
    workspace = user_data / "workspaces" / "defaults"
    workspace.mkdir(parents=True, exist_ok=True)
    store = ActivationStore(user_data / "profiles" / "defaults" / "v4", workspace)
    active_pointer = store.state_root / "active.json"
    if active_pointer.is_file():
        return store.load_active_snapshot()
    if active_pointer.exists():
        raise ProfileResolutionDenied("active activation pointer is not a regular file")

    bundle_root = _bundle_root(base_dir)
    catalog = BundledCatalog.load(bundle_root)
    bundle_lock_digest = "sha256:" + hashlib.sha256(
        (bundle_root / "bundle.lock.json").read_bytes()
    ).hexdigest()
    authority = AuthorityStore(user_data / "authority" / "v4.sqlite3")
    snapshot_digest = _authority_snapshot_digest(authority, bundle_lock_digest)
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
        security_epoch=authority.security_epoch,
    )
    activation_id = (
        "activation:defaults-" + resolved.plan["plan_digest"].removeprefix("sha256:")[:16]
    )
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    store.activate(
        resolved,
        activation_id=activation_id,
        created_at=created_at,
        fencing_token=1,
    )
    return store.load_active_snapshot()


__all__ = ["capture_default_profile", "runtime_user_data_root"]
