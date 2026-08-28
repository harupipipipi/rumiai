"""Canonical bindings between Profile edges, scopes, and Authority snapshots."""

from __future__ import annotations

from typing import Any, Mapping

from .canonical import canonical_digest
from .ids import validate_artifact_digest


AUTHORITY_EDGE_SCHEMA = "io.tobkiri.profile-authority-edge.v2"
_EDGE_FIELDS = (
    "caller_function_id",
    "target_provider_id",
    "contract_id",
    "operation_id",
)


def authority_edge_key(edge: Mapping[str, Any]) -> str:
    """Return the exact stable key for one Profile requested edge."""

    values: list[str] = []
    for field in _EDGE_FIELDS:
        value = edge.get(field)
        if not isinstance(value, str) or not value or "|" in value:
            raise ValueError(f"authority edge field is invalid: {field}")
        values.append(value)
    return "|".join(values)


def authority_reference(
    edge: Mapping[str, Any],
    profile_authority_snapshot_digest: str,
    *,
    requested_scope_digest: str,
) -> str:
    """Return the opaque Authority reference for an exact edge and scope.

    The requested scope digest is deliberately part of the opaque reference.
    A scope change therefore cannot reuse an Authority reference minted for a
    different scope, even when the caller, target, Contract, and operation are
    unchanged.
    """

    edge_key = authority_edge_key(edge)
    try:
        validate_artifact_digest(
            profile_authority_snapshot_digest,
            field="profile Authority snapshot digest",
        )
        validate_artifact_digest(requested_scope_digest, field="requested scope digest")
    except Exception as error:
        raise ValueError("authority binding digest is invalid") from error
    digest = canonical_digest(
        {
            "schema": AUTHORITY_EDGE_SCHEMA,
            "edge": edge_key,
            "requested_scope_digest": requested_scope_digest,
            "profile_authority_snapshot_digest": profile_authority_snapshot_digest,
        }
    )
    return f"authority-ref:{digest.removeprefix('sha256:')}"


__all__ = ["AUTHORITY_EDGE_SCHEMA", "authority_edge_key", "authority_reference"]
