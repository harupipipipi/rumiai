"""Register explicitly selected bootstrap definitions without replacing user state."""

from pathlib import Path
from typing import Any, Mapping

from tobkiri_protocol.canonical import canonical_digest

from ..authority.v4 import AuthorityStore
from ..profile_definition_store_v4 import (
    ProfileDefinitionStore,
    ProfileDefinitionStoreConflict,
)


def register_bootstrap_definition(
    user_data: Path,
    source: Mapping[str, Any],
    *,
    approved_predecessor_digest: str | None = None,
) -> None:
    """Register a source or append its explicitly confirmed predecessor's successor."""
    definitions = ProfileDefinitionStore(user_data)
    generation = definitions.snapshot()["generation"]
    existing = definitions.get_profile(str(source["profile_id"]), include_tombstone=True)
    if existing is None:
        try:
            definitions.create_profile(source, expected_store_generation=generation)
            return
        except ProfileDefinitionStoreConflict:
            existing = definitions.get_profile(
                str(source["profile_id"]), include_tombstone=True
            )
            if existing is None:
                raise
    if (
        existing is not None
        and not existing.tombstone
        and dict(existing.profile) != dict(source)
        and approved_predecessor_digest is not None
        and canonical_digest(existing.profile) == approved_predecessor_digest
    ):
        definitions.update_profile(
            existing.profile_id,
            source,
            expected_profile_revision=existing.profile_revision,
            expected_store_generation=generation,
        )
        return
    if existing is None or existing.tombstone or dict(existing.profile) != dict(source):
        raise ProfileDefinitionStoreConflict(
            "bootstrap Profile conflicts with the existing definition"
        )


def recover_bootstrap_definition(
    *, user_data: Path, pointer: Any, runtime: Any, catalog: Any
) -> None:
    """Restore only the exact source of a verified, already committed activation."""
    definitions = ProfileDefinitionStore(user_data)
    if definitions.get_profile(pointer.profile_id, include_tombstone=True) is not None:
        raise ProfileDefinitionStoreConflict(
            "active bootstrap Profile has an unavailable existing definition"
        )
    workspace = user_data / "workspaces" / pointer.profile_id
    with AuthorityStore(user_data / "authority" / "v4.sqlite3") as authority:
        active = runtime.activation_store(
            root=workspace / "activation",
            workspace=workspace,
            profile_id=pointer.profile_id,
            authority=authority,
            catalog=catalog,
        ).load_active_snapshot()
    if (
        active.resolved.plan["profile_revision"],
        active.activation["activation_id"],
        active.resolved.plan["plan_digest"],
        active.resolved.lock["lock_digest"],
    ) != (
        pointer.profile_revision,
        pointer.activation_id,
        pointer.plan_digest,
        pointer.lock_digest,
    ):
        raise runtime.denied("Host active pointer does not match the Profile activation")
    source = catalog.profiles.get(pointer.profile_id)
    if source is None or canonical_digest(source) != active.resolved.plan.get(
        "profile_definition_digest"
    ):
        raise runtime.denied("bootstrap definition differs from its committed source")
    register_bootstrap_definition(user_data, source)
