"""Generate the Launcher presentation catalog from defaultspack manifests.

The Launcher consumes a small JSON projection of the canonical Pack
Architecture assets.  This module is the only generator for that projection;
the checked-in output is intentionally reproducible and is checked in CI.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

import yaml  # type: ignore[import-untyped]

from .catalog import PackCatalog
from .errors import CatalogError
from .model import PackDefinition, PresentationContribution

PRESENTATION_CATALOG_SCHEMA = "io.tobkiri.launcher.presentation-catalog.v1"
PRESENTATION_CATALOG_GENERATOR_VERSION = "1.0.0"
DEFAULT_PROFILE_RELATIVE = (
    "tobkiri_runtime/ecosystem/defaultspack/profiles/defaults-modern.profile.yaml"
)
ASSETS_RELATIVE = "tobkiri_runtime/ecosystem/defaultspack/domain/pack_architecture/assets"
CONTRACT_REGISTRY_RELATIVE = f"{ASSETS_RELATIVE}/contracts/revisions.json"
DEFAULT_CATALOG_RELATIVE = "tobkiri_launcher/src-tauri/bundled/presentation_catalog.json"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

_APPROVAL_STATES = frozenset({"verified", "pending", "blocked", "not_required"})
_GRANT_STATES = frozenset({"not_minted", "available", "missing", "blocked"})
_AUTHORITY_MODES = frozenset({"lease_only", "os_entitlement", "none"})


def sha256_file(path: Path) -> str:
    """Return the repository-standard SHA-256 digest for one file."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def generate_presentation_catalog(repository_root: Path) -> dict[str, Any]:
    """Generate a deterministic Launcher catalog from checked-in assets.

    No installed application is inferred from a descriptor.  Generated
    variants therefore have no ``path`` or executable digest; installation
    metadata must provide both before the Launcher can mark a variant
    verified.
    """
    root = repository_root.resolve()
    assets_root = root / ASSETS_RELATIVE
    catalog = PackCatalog.from_assets_root(assets_root)
    contract_revisions = _load_contract_revisions(root)
    base_packs = tuple(pack for pack in catalog.all() if pack.kind == "base")
    shells = tuple(pack for pack in catalog.all() if pack.is_shell)
    if not base_packs:
        raise CatalogError("presentation catalog requires at least one Base Pack")
    if not shells:
        raise CatalogError("presentation catalog requires at least one Shell Provider")

    default_profile = _load_default_profile(root, catalog)
    used_contracts = {
        "app.shell.v1",
        *(
            contract
            for pack in base_packs
            for contribution in pack.contributions
            for contract in [contribution.contract_id]
        ),
        *(contract for pack in shells for contract in pack.consumes_contracts),
    }
    for shell in shells:
        cli_protocol = shell.raw.get("cli_protocol")
        if isinstance(cli_protocol, Mapping):
            protocol_version = str(cli_protocol.get("version") or "").strip()
            if protocol_version:
                used_contracts.add(protocol_version)
    selected_revisions = [
        contract_revisions[contract]
        for contract in sorted(used_contracts)
        if contract in contract_revisions
    ]
    missing_revisions = sorted(used_contracts - set(contract_revisions))
    if missing_revisions:
        raise CatalogError("contract revision registry is missing: " + ", ".join(missing_revisions))

    source_manifest_digests = {
        pack.pack_id: sha256_file(pack.source_dir / "pack.json") for pack in catalog.all()
    }
    return {
        "schema": PRESENTATION_CATALOG_SCHEMA,
        "generator": "tobkiri-defaultspack-presentation-catalog",
        "generator_version": PRESENTATION_CATALOG_GENERATOR_VERSION,
        "default_profile_id": default_profile["profile_id"],
        "default_profile_source": default_profile["source"],
        "default_profile_digest": default_profile["digest"],
        "default_selection": default_profile["selection"],
        "contract_revisions": selected_revisions,
        "source_manifest_digests": source_manifest_digests,
        "base_packs": [
            _base_descriptor(pack, source_manifest_digests[pack.pack_id]) for pack in base_packs
        ],
        "shell_providers": [
            _shell_descriptor(
                shell,
                base_packs,
                contract_revisions,
            )
            for shell in shells
        ],
        "generated_at": 0,
    }


def write_presentation_catalog(repository_root: Path, output: Path | None = None) -> Path:
    """Write the generated catalog using stable JSON formatting."""
    root = repository_root.resolve()
    target = (output or root / DEFAULT_CATALOG_RELATIVE).resolve()
    payload = generate_presentation_catalog(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def presentation_catalog_drift(repository_root: Path, output: Path | None = None) -> bool:
    """Return whether a checked-in Launcher catalog differs from its inputs."""
    root = repository_root.resolve()
    target = (output or root / DEFAULT_CATALOG_RELATIVE).resolve()
    if not target.is_file():
        return True
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return existing != generate_presentation_catalog(root)


def _base_descriptor(pack: PackDefinition, manifest_digest: str) -> dict[str, Any]:
    approval = _approval(pack)
    return {
        "pack_id": pack.pack_id,
        "display_name": pack.display_name,
        "version": pack.version,
        "artifact_digest": manifest_digest,
        "backend_provider_ids": list(pack.backend_provider_ids),
        "state_owners": list(pack.state_owners),
        "backend_identity_digest": _identity_digest(
            {
                "provider_ids": list(pack.backend_provider_ids),
                "state_owners": list(pack.state_owners),
            }
        ),
        "required_capabilities": list(pack.shell_requirement_capabilities),
        "allowed_families": list(pack.shell_requirement_families),
        "approval": approval,
    }


def _shell_descriptor(
    shell: PackDefinition,
    base_packs: tuple[PackDefinition, ...],
    contract_revisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if shell.shell_contract is None or shell.presentation_family is None:
        raise CatalogError(f"{shell.pack_id}: shell contract and family are required")
    approval = _approval(shell)
    consumed = set(shell.consumes_contracts)
    contributions = [
        _contribution_descriptor(contribution, contract_revisions, base.source_dir)
        for base in base_packs
        for contribution in base.contributions
    ]
    variants = [_variant_descriptor(shell, variant) for variant in shell.variants]
    descriptor: dict[str, Any] = {
        "provider_id": shell.pack_id,
        "display_name": shell.display_name,
        "contract_id": shell.shell_contract,
        "contract_revision_digest": _revision_digest(contract_revisions, shell.shell_contract),
        "experience_role": str(shell.raw.get("experience_role") or "shell"),
        "presentation_kind": str(shell.presentation_kind or ""),
        "presentation_family": shell.presentation_family,
        "technology": str(shell.technology or ""),
        "capabilities": list(shell.capabilities),
        "consumes_contracts": list(shell.consumes_contracts),
        "contributions": contributions,
        "artifact_variants": variants,
        "approval": approval,
    }
    cli_protocol = shell.raw.get("cli_protocol")
    if isinstance(cli_protocol, Mapping):
        protocol_version = str(cli_protocol.get("version") or "").strip()
        if protocol_version:
            descriptor["protocol_revision_digest"] = _revision_digest(
                contract_revisions, protocol_version
            )
    # Keep this check next to generation so a Shell cannot accidentally list
    # contribution metadata it does not consume.  The full contribution list
    # is retained for auditability; materialization filters it by this set.
    if not consumed:
        raise CatalogError(f"{shell.pack_id}: no contribution contracts are consumed")
    return descriptor


def _contribution_descriptor(
    contribution: PresentationContribution,
    contract_revisions: Mapping[str, Mapping[str, Any]],
    owner_source_dir: Path,
) -> dict[str, Any]:
    artifact_path = _safe_relative_file(owner_source_dir, contribution.artifact_ref)
    actual_digest = sha256_file(artifact_path)
    if actual_digest != contribution.digest:
        raise CatalogError(
            f"{contribution.contribution_id}: contribution digest drift "
            f"({actual_digest} != {contribution.digest})"
        )
    return {
        "contribution_id": contribution.contribution_id,
        "owner_pack_id": contribution.owner_pack_id,
        "contract_id": contribution.contract_id,
        "contract_revision_digest": _revision_digest(contract_revisions, contribution.contract_id),
        "family": contribution.presentation_family,
        "label": contribution.label or contribution.contribution_id,
        "artifact_ref": contribution.artifact_ref,
        "digest": contribution.digest,
        "presentation_kind": contribution.presentation_kind,
        "technology": contribution.technology,
        "host_authority": contribution.host_authority,
        "materialization": contribution.materialization,
    }


def _variant_descriptor(pack: PackDefinition, variant: Any) -> dict[str, Any]:
    descriptor_path = _safe_relative_file(pack.source_dir, variant.artifact_ref)
    if sha256_file(descriptor_path) != variant.digest:
        raise CatalogError(f"{pack.pack_id}:{variant.variant_id}: descriptor digest drift")
    try:
        raw = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read variant descriptor {descriptor_path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise CatalogError(f"variant descriptor must be an object: {descriptor_path}")
    expected_artifact_id = f"{pack.pack_id}.{variant.variant_id}"
    if raw.get("artifact_id") != expected_artifact_id:
        raise CatalogError(f"{descriptor_path}: artifact_id must be {expected_artifact_id!r}")
    for key, expected in {
        "pack_id": pack.pack_id,
        "platform": variant.platform,
        "architecture": variant.architecture,
        "source_build": False,
    }.items():
        if raw.get(key) != expected:
            raise CatalogError(f"{descriptor_path}: {key} does not match pack manifest")
    if raw.get("kind") != variant.artifact_kind:
        raise CatalogError(f"{descriptor_path}: artifact kind does not match pack manifest")
    production = pack.raw.get("production")
    if not isinstance(production, Mapping):
        raise CatalogError(f"{pack.pack_id}: production declaration is missing")
    if production.get("prebuilt_only") is not True or production.get("launchable") is not True:
        raise CatalogError(f"{pack.pack_id}: Shell must be a production prebuilt surface")
    installed = raw.get("installed_artifact")
    installed_path: str | None = None
    installed_digest: str | None = None
    if installed is not None:
        if not isinstance(installed, Mapping):
            raise CatalogError(f"{descriptor_path}: installed_artifact must be an object")
        installed_path = str(installed.get("path") or "").strip()
        installed_digest = str(installed.get("digest") or "").strip()
        if (
            not installed_path
            or Path(installed_path).is_absolute()
            or ".." in Path(installed_path).parts
        ):
            raise CatalogError(f"{descriptor_path}: installed artifact path is unsafe")
        if not DIGEST_RE.fullmatch(installed_digest):
            raise CatalogError(f"{descriptor_path}: installed artifact digest is invalid")
    return {
        "artifact_id": str(raw["artifact_id"]),
        "variant": variant.variant_id,
        "platform": variant.platform,
        "architecture": variant.architecture,
        "artifact_ref": variant.artifact_ref,
        "entrypoint": variant.entrypoint,
        "artifact_kind": variant.artifact_kind,
        "descriptor_digest": variant.digest,
        "path": installed_path,
        "sha256": installed_digest,
        "prebuilt": production.get("prebuilt_only") is True,
        "production": production.get("launchable") is True,
        "development_command": None,
        "bundle_identifier": raw.get("bundle_identity"),
    }


def _load_contract_revisions(repository_root: Path) -> dict[str, dict[str, Any]]:
    path = repository_root / CONTRACT_REGISTRY_RELATIVE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read contract revision registry {path}: {exc}") from exc
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema") != "io.tobkiri.contract.revision-registry.v1"
    ):
        raise CatalogError("contract revision registry has an unsupported schema")
    values = payload.get("contracts")
    if not isinstance(values, list):
        raise CatalogError("contract revision registry contracts must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            raise CatalogError(f"contract revision {index} must be an object")
        contract_id = str(item.get("contract_id") or "").strip()
        revision = str(item.get("revision") or "").strip()
        source_path = str(item.get("source_path") or "").strip()
        if not contract_id or not SEMVER_RE.fullmatch(revision) or not source_path:
            raise CatalogError(f"contract revision {index} is incomplete")
        if contract_id in result:
            raise CatalogError(f"duplicate contract revision: {contract_id}")
        source = (repository_root / source_path).resolve()
        try:
            source.relative_to(repository_root)
        except ValueError as exc:
            raise CatalogError(f"contract source escapes repository: {source_path}") from exc
        if not source.is_file():
            raise CatalogError(f"contract revision source is missing: {source_path}")
        result[contract_id] = {
            "contract_id": contract_id,
            "revision": revision,
            "source_path": source_path,
            "digest": sha256_file(source),
        }
    return result


def _load_default_profile(repository_root: Path, catalog: PackCatalog) -> dict[str, Any]:
    path = repository_root / DEFAULT_PROFILE_RELATIVE
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogError(f"cannot read default profile {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CatalogError("defaults-modern profile must be an object")
    if payload.get("schema") != "io.tobkiri.profile.v4":
        raise CatalogError("defaults-modern profile must use io.tobkiri.profile.v4")
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("default_for_new_setups") is not True:
        raise CatalogError("defaults-modern profile must be marked default_for_new_setups")
    if _contains_legacy_launch_field(payload):
        raise CatalogError("defaults-modern profile contains a legacy launch field")
    base = payload.get("base")
    shell = payload.get("shell")
    if not isinstance(base, Mapping) or not isinstance(shell, Mapping):
        raise CatalogError("defaults-modern profile must select Base Pack and Shell explicitly")
    base_id = str(base.get("pack") or "").strip()
    shell_id = str(shell.get("provider") or "").strip()
    if not base_id or not shell_id or shell.get("contract") != "app.shell.v1":
        raise CatalogError("defaults-modern profile has an incomplete exact Shell selection")
    if catalog.get(base_id) is None or catalog.get(shell_id) is None:
        raise CatalogError("defaults-modern profile selects an uncataloged provider")
    return {
        "profile_id": str(payload.get("profile_id") or "defaults-modern").strip(),
        "source": DEFAULT_PROFILE_RELATIVE,
        "digest": sha256_file(path),
        "selection": {"base_pack_id": base_id, "shell_provider_id": shell_id},
    }


def _approval(pack: PackDefinition) -> dict[str, Any]:
    raw = pack.raw.get("approval")
    if not isinstance(raw, Mapping):
        raise CatalogError(f"{pack.pack_id}: approval declaration is missing")
    required = (
        "state",
        "provider_trust",
        "grant_state",
        "authority_mode",
        "execution_domain",
        "effect_scope",
        "blast_radius",
    )
    if any(key not in raw for key in required):
        raise CatalogError(f"{pack.pack_id}: approval declaration is incomplete")
    state = str(raw.get("state") or "")
    provider_trust = str(raw.get("provider_trust") or "")
    grant_state = str(raw.get("grant_state") or "")
    authority_mode = str(raw.get("authority_mode") or "")
    if state not in _APPROVAL_STATES or provider_trust not in _APPROVAL_STATES:
        raise CatalogError(f"{pack.pack_id}: approval/trust state is invalid")
    if grant_state not in _GRANT_STATES or authority_mode not in _AUTHORITY_MODES:
        raise CatalogError(f"{pack.pack_id}: grant/authority state is invalid")
    effect_scope = raw.get("effect_scope")
    if not isinstance(effect_scope, list) or not all(
        isinstance(item, str) for item in effect_scope
    ):
        raise CatalogError(f"{pack.pack_id}: approval effect_scope must be a string array")
    return {
        "state": state,
        "provider_trust": provider_trust,
        "grant_state": grant_state,
        "authority_mode": authority_mode,
        "execution_domain": str(raw.get("execution_domain") or ""),
        "effect_scope": list(effect_scope),
        "blast_radius": str(raw.get("blast_radius") or ""),
        **({"reason": raw["reason"]} if "reason" in raw else {}),
    }


def _revision_digest(revisions: Mapping[str, Mapping[str, Any]], contract_id: str) -> str:
    try:
        return str(revisions[contract_id]["digest"])
    except KeyError as exc:
        raise CatalogError(f"contract revision is not registered: {contract_id}") from exc


def _safe_relative_file(pack_dir: Path, artifact_ref: str) -> Path:
    candidate = (pack_dir / artifact_ref).resolve()
    root = pack_dir.parent.parent.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise CatalogError(f"artifact reference escapes catalog assets: {artifact_ref!r}") from exc
    if not candidate.is_file():
        raise CatalogError(f"artifact descriptor is missing: {artifact_ref}")
    return candidate


def _identity_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _contains_legacy_launch_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        if any(key in value for key in ("command", "desktop_app")):
            return True
        return any(_contains_legacy_launch_field(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_legacy_launch_field(child) for child in value)
    return False
