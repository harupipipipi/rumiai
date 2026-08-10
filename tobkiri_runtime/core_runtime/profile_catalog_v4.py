"""Authoritative read model for canonical Protocol v4 Profile definitions."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from ecosystem.defaultspack.domain.runtime_v4 import ActiveDefaultProfile, BundledCatalog
from tobkiri_protocol.canonical import canonical_digest


def profile_catalog_digest(catalog: BundledCatalog) -> str:
    """Return a deterministic digest of the verified Profile catalog."""

    return canonical_digest(
        {
            profile_id: canonical_digest(profile)
            for profile_id, profile in sorted(catalog.profiles.items())
        }
    )


def bundle_lock_digest(catalog: BundledCatalog) -> str:
    """Return the exact digest of the lock that admitted the catalog bytes."""

    lock_path = catalog.root / "bundle.lock.json"
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ValueError("canonical Profile catalog lock is unavailable")
    return "sha256:" + hashlib.sha256(lock_path.read_bytes()).hexdigest()


def profile_definition_digest(catalog: BundledCatalog, profile_id: str) -> str:
    """Return one canonical Profile definition digest or fail closed."""

    definition = catalog.profiles.get(profile_id)
    if definition is None:
        raise ValueError("Profile is absent from the canonical catalog")
    return canonical_digest(definition)


def project_profile_catalog(
    catalog: BundledCatalog,
    active: ActiveDefaultProfile,
) -> dict[str, object]:
    """Project all admitted Profile definitions without changing active state."""

    active_profile_id = str(active.resolved.profile["profile_id"])
    active_revision = str(active.resolved.plan["profile_revision"])
    active_plan_digest = str(active.resolved.plan["plan_digest"])
    active_lock_digest = str(active.resolved.lock["lock_digest"])
    active_authority_digest = str(active.resolved.profile["profile_authority_snapshot_digest"])
    catalog_digest = profile_catalog_digest(catalog)
    lock_digest = bundle_lock_digest(catalog)
    definitions = [
        _project_definition(
            catalog,
            profile_id,
            definition,
            active_profile_id=active_profile_id,
            active_revision=active_revision,
            active_plan_digest=active_plan_digest,
            active_lock_digest=active_lock_digest,
            active_authority_digest=active_authority_digest,
        )
        for profile_id, definition in sorted(catalog.profiles.items())
    ]
    return {
        "catalog_api_version": "io.tobkiri.profile-catalog-presentation.v4",
        "catalog_digest": catalog_digest,
        "bundle_lock_digest": lock_digest,
        "catalog_ref": f"profile-catalog-v4://bundle/{catalog_digest}",
        "active_profile_id": active_profile_id,
        "count": len(definitions),
        "profiles": definitions,
    }


def require_profile_catalog_binding(
    catalog: BundledCatalog,
    *,
    profile_id: str,
    expected_definition_digest: str,
    expected_catalog_digest: str,
    expected_bundle_lock_digest: str,
) -> Mapping[str, Any]:
    """Authenticate client-returned catalog bindings against current bytes."""

    definition = catalog.profiles.get(profile_id)
    if definition is None:
        raise ValueError("Profile is absent from the canonical catalog")
    actual_definition = canonical_digest(definition)
    actual_catalog = profile_catalog_digest(catalog)
    actual_lock = bundle_lock_digest(catalog)
    if not (
        hmac.compare_digest(expected_definition_digest, actual_definition)
        and hmac.compare_digest(expected_catalog_digest, actual_catalog)
        and hmac.compare_digest(expected_bundle_lock_digest, actual_lock)
    ):
        raise ValueError("Profile catalog binding is stale or tampered")
    return definition


def _project_definition(
    catalog: BundledCatalog,
    profile_id: str,
    definition: Mapping[str, Any],
    *,
    active_profile_id: str,
    active_revision: str,
    active_plan_digest: str,
    active_lock_digest: str,
    active_authority_digest: str,
) -> dict[str, object]:
    diagnostics: list[dict[str, str]] = []
    base_id = str(definition["base"]["pack_id"])
    shell_id = str(definition["shell"]["provider_id"])
    base = catalog.bases.get(base_id)
    shell = catalog.shells.get(shell_id)
    if base is None or base_id not in catalog.packs:
        diagnostics.append({"code": "BASE_UNAVAILABLE", "subject": base_id})
    elif base["artifact_digest"] != catalog.packs[base_id]["pack"]["artifact_digest"]:
        diagnostics.append({"code": "BASE_DIGEST_MISMATCH", "subject": base_id})
    if shell is None or str(shell.get("pack_id") or "") not in catalog.packs:
        diagnostics.append({"code": "SHELL_UNAVAILABLE", "subject": shell_id})
    elif base is not None:
        requirements = base["shell_requirements"]
        presentation = shell["presentation"]
        if presentation["family"] not in requirements["presentation_families"]:
            diagnostics.append({"code": "SHELL_FAMILY_INCOMPATIBLE", "subject": shell_id})
        missing_capabilities = sorted(
            set(requirements["required_capabilities"])
            - set(presentation["capabilities"])
        )
        diagnostics.extend(
            {"code": "SHELL_CAPABILITY_MISSING", "subject": capability}
            for capability in missing_capabilities
        )
        requested_variant = (
            str(definition["shell"]["platform"]),
            str(definition["shell"]["architecture"]),
        )
        matching_variants = [
            variant
            for variant in shell["launch"]["variants"]
            if (variant["platform"], variant["architecture"]) == requested_variant
            and variant["artifact_digest"] == shell["artifact_digest"]
        ]
        if len(matching_variants) != 1:
            diagnostics.append({"code": "SHELL_VARIANT_INCOMPATIBLE", "subject": shell_id})

    requested = [dict(item) for item in definition["packs"]]
    requested_ids = [str(item["pack_id"]) for item in requested]
    if len(requested_ids) != len(set(requested_ids)):
        diagnostics.append({"code": "PACK_DUPLICATE", "subject": profile_id})
    application_rows = [item for item in requested if item.get("role") == "application"]
    if len(application_rows) != 1:
        diagnostics.append({"code": "APPLICATION_BINDING_INVALID", "subject": profile_id})
    for item in requested:
        pack_id = str(item["pack_id"])
        manifest = catalog.packs.get(pack_id)
        if manifest is None:
            diagnostics.append({"code": "PACK_UNAVAILABLE", "subject": pack_id})
        elif item.get("artifact_digest") not in {
            None,
            manifest["pack"]["artifact_digest"],
        }:
            diagnostics.append({"code": "PACK_DIGEST_MISMATCH", "subject": pack_id})
        if item.get("role") == "application" and (
            manifest is None or manifest["pack"]["kind"] != "application"
        ):
            diagnostics.append({"code": "APPLICATION_KIND_INVALID", "subject": pack_id})

    closure = _static_pack_closure(catalog, base_id, shell, requested, diagnostics)
    is_active = profile_id == active_profile_id
    provenance = dict(definition["provenance"])
    definition_digest = canonical_digest(definition)
    return {
        "profile_id": profile_id,
        "display_name": str(definition.get("display_name") or profile_id),
        "active": is_active,
        "lifecycle_state": "active" if is_active else "available",
        "available": not diagnostics,
        "diagnostics": diagnostics,
        "definition": {
            "digest": definition_digest,
            "ref": f"profile-v4://{profile_id}/{definition_digest}",
            "catalog_revision": definition.get("catalog_revision"),
            "source_path": provenance.get("source_path"),
            "provenance": provenance,
        },
        "bindings": {
            "base": _base_binding(catalog, base_id, base),
            "shell": _shell_binding(catalog, shell_id, shell),
            "application": _application_binding(catalog, application_rows),
        },
        "pack_closure": closure,
        "records": {
            "profile_revision": active_revision if is_active else None,
            "profile_lock_digest": active_lock_digest if is_active else None,
            "plan_digest": active_plan_digest if is_active else None,
        },
        "authority_snapshot": {
            "state": "active" if is_active else "captured_on_resolve",
            "digest": active_authority_digest if is_active else None,
            "ref": (
                f"authority-snapshot-v4://{profile_id}/{active_authority_digest}"
                if is_active
                else None
            ),
            "definition_references": list(definition["authority_references"]),
        },
        "candidate": {
            "state": "not_staged",
            "candidate_id": None,
            "candidate_digest": None,
            "expires_at": None,
        },
    }


def _static_pack_closure(
    catalog: BundledCatalog,
    base_id: str,
    shell: Mapping[str, Any] | None,
    requested: list[dict[str, Any]],
    diagnostics: list[dict[str, str]],
) -> list[dict[str, object]]:
    roles = {base_id: "base"}
    if shell is not None:
        roles[str(shell["pack_id"])] = "shell"
    roles.update({str(item["pack_id"]): str(item.get("role") or "provider") for item in requested})
    pending = list(roles)
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    while pending:
        pack_id = pending.pop(0)
        if pack_id in seen:
            continue
        seen.add(pack_id)
        manifest = catalog.packs.get(pack_id)
        if manifest is None:
            continue
        dependencies = sorted(manifest["requirements"]["pack_dependencies"])
        pending.extend(dependencies)
        for dependency in dependencies:
            roles.setdefault(dependency, "dependency")
            if dependency not in catalog.packs:
                diagnostics.append({"code": "DEPENDENCY_UNAVAILABLE", "subject": dependency})
                continue
            version_range = manifest["requirements"]["pack_dependencies"][dependency]
            try:
                compatible = Version(catalog.packs[dependency]["pack"]["version"]) in SpecifierSet(
                    version_range.replace(" ", ",")
                )
            except (InvalidSpecifier, InvalidVersion):
                compatible = False
            if not compatible:
                diagnostics.append(
                    {"code": "DEPENDENCY_VERSION_INCOMPATIBLE", "subject": dependency}
                )
        pack = manifest["pack"]
        result.append(
            {
                "pack_id": pack_id,
                "role": roles[pack_id],
                "version": str(pack["version"]),
                "artifact_digest": str(pack["artifact_digest"]),
                "artifact_ref": f"pack-v4://{pack_id}@{pack['artifact_digest']}",
            }
        )
    return sorted(result, key=lambda item: str(item["pack_id"]))


def _base_binding(
    catalog: BundledCatalog,
    base_id: str,
    base: Mapping[str, Any] | None,
) -> dict[str, object]:
    manifest = catalog.packs.get(base_id)
    return {
        "pack_id": base_id,
        "definition_revision": base.get("definition_revision") if base else None,
        "definition_digest": canonical_digest(base) if base else None,
        "artifact_digest": manifest["pack"]["artifact_digest"] if manifest else None,
    }


def _shell_binding(
    catalog: BundledCatalog,
    shell_id: str,
    shell: Mapping[str, Any] | None,
) -> dict[str, object]:
    pack_id = str(shell.get("pack_id") or "") if shell else ""
    manifest = catalog.packs.get(pack_id)
    return {
        "provider_id": shell_id,
        "pack_id": pack_id or None,
        "definition_revision": shell.get("definition_revision") if shell else None,
        "definition_digest": canonical_digest(shell) if shell else None,
        "artifact_digest": manifest["pack"]["artifact_digest"] if manifest else None,
    }


def _application_binding(
    catalog: BundledCatalog,
    application_rows: list[dict[str, Any]],
) -> dict[str, object] | None:
    if len(application_rows) != 1:
        return None
    row = application_rows[0]
    pack_id = str(row["pack_id"])
    manifest = catalog.packs.get(pack_id)
    return {
        "pack_id": pack_id,
        "artifact_digest": manifest["pack"]["artifact_digest"] if manifest else None,
        "artifact_ref": (
            f"pack-v4://{pack_id}@{manifest['pack']['artifact_digest']}" if manifest else None
        ),
    }


__all__ = [
    "bundle_lock_digest",
    "profile_catalog_digest",
    "profile_definition_digest",
    "project_profile_catalog",
    "require_profile_catalog_binding",
]
