from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Mapping

from .models import ConnectionProvider


@dataclass(frozen=True)
class ResolvedConnectionPermissions:
    scopes: list[str]
    capabilities: list[str]
    approval_required_capabilities: list[str]
    rejected_capabilities: list[str]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scopes": list(self.scopes),
            "capabilities": list(self.capabilities),
            "approval_required_capabilities": list(self.approval_required_capabilities),
            "rejected_capabilities": list(self.rejected_capabilities),
            "status": self.status,
        }


def resolve_connection_permissions(provider: ConnectionProvider, token_metadata: Mapping[str, Any] | None = None) -> ResolvedConnectionPermissions:
    metadata = dict(token_metadata or {})
    scopes = _normalize_scopes(metadata.get("scopes") or metadata.get("scope"))
    manifest_capabilities = {capability.id: capability for capability in provider.capabilities}
    manifest_allowed = set(manifest_capabilities)
    rejected: set[str] = set(_normalize_string_list(metadata.get("capabilities") or metadata.get("capabilities_granted")))
    credential_kind = str(metadata.get("credential_kind") or metadata.get("material_type") or "").strip()
    provider_granted, mapping_rejected = _provider_granted_capability_sets(
        provider,
        scopes=scopes,
        credential_kind=credential_kind,
    )
    rejected.update(mapping_rejected)

    requested = _requested_capabilities(metadata)
    if requested:
        requested_set = set(requested)
    else:
        requested_set = {
            capability_id
            for capability_id in provider_granted
            if _capability_risk(manifest_capabilities[capability_id]) in {"none", "low"}
        }

    enabled: set[str] = set()
    approval_required: set[str] = set()
    for capability in requested_set:
        if capability not in manifest_allowed:
            rejected.add(capability)
            continue
        if capability not in provider_granted:
            rejected.add(capability)
            continue
        if _capability_risk(manifest_capabilities[capability]) == "high":
            approval_required.add(capability)
            continue
        enabled.add(capability)

    # Non-OAuth credentials often have no scopes.  They are still resolved from
    # explicit manifest rules keyed by credential kind, never from imported JSON.
    rejected.difference_update(enabled)
    rejected.difference_update(approval_required)
    return ResolvedConnectionPermissions(
        scopes=scopes,
        capabilities=sorted(enabled),
        approval_required_capabilities=sorted(approval_required),
        rejected_capabilities=sorted(rejected),
        status="resolved",
    )


def provider_granted_capabilities(provider: ConnectionProvider, token_metadata: Mapping[str, Any] | None = None) -> list[str]:
    metadata = dict(token_metadata or {})
    scopes = _normalize_scopes(metadata.get("scopes") or metadata.get("scope"))
    credential_kind = str(metadata.get("credential_kind") or metadata.get("material_type") or "").strip()
    granted, _rejected = _provider_granted_capability_sets(
        provider,
        scopes=scopes,
        credential_kind=credential_kind,
    )
    return sorted(granted)


def _requested_capabilities(metadata: Mapping[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            _normalize_string_list(
                metadata.get("requested_capabilities")
                or metadata.get("requestedCapabilities")
                or metadata.get("requested")
            )
        )
    )


def _capability_risk(capability: Any) -> str:
    return str(getattr(capability, "risk", "") or "none").strip().lower() or "none"


def _provider_granted_capability_sets(
    provider: ConnectionProvider,
    *,
    scopes: list[str],
    credential_kind: str,
) -> tuple[set[str], set[str]]:
    manifest_allowed = {capability.id for capability in provider.capabilities}
    granted: set[str] = set()
    rejected: set[str] = set()
    for mapping in provider.scope_to_capability:
        if not isinstance(mapping, Mapping):
            continue
        capabilities = _mapping_capabilities(mapping)
        if not capabilities:
            continue
        if not _mapping_matches(mapping, scopes=scopes, credential_kind=credential_kind):
            continue
        for capability in capabilities:
            if capability in manifest_allowed:
                granted.add(capability)
            else:
                rejected.add(capability)
    return granted, rejected


def _mapping_matches(mapping: Mapping[str, Any], *, scopes: list[str], credential_kind: str) -> bool:
    expected_kinds = _normalize_string_list(mapping.get("credential_kinds") or mapping.get("credential_kind"))
    if expected_kinds and credential_kind not in expected_kinds:
        return False
    scope_patterns = _normalize_string_list(mapping.get("scopes") or mapping.get("scope"))
    if not scope_patterns:
        return bool(expected_kinds and credential_kind in expected_kinds)
    match_mode = str(mapping.get("match") or "any").strip().lower()
    matched = [_scope_matches(pattern, scopes) for pattern in scope_patterns]
    return all(matched) if match_mode == "all" else any(matched)


def _mapping_capabilities(mapping: Mapping[str, Any]) -> list[str]:
    return _normalize_string_list(mapping.get("capabilities") or mapping.get("capability"))


def _normalize_scopes(value: Any) -> list[str]:
    return list(dict.fromkeys(_normalize_string_list(value)))


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item for item in text.replace(",", " ").split() if item]


def _scope_matches(pattern: str, scopes: list[str]) -> bool:
    pattern = str(pattern or "").strip()
    if not pattern:
        return False
    return any(scope == pattern or fnmatch.fnmatchcase(scope, pattern) for scope in scopes)
