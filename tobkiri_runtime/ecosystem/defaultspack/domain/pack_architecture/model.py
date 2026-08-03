"""Typed, dependency-free models for the v4 Base/Shell application model.

The runtime core is intentionally not imported here.  These models describe the
profile and pack boundary that a future v4 resolver can hand to the core through
the authenticated ProfileLock interface.  They reject ambiguous values instead of
inventing a framework, provider, or launch command.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .errors import CatalogError

PACK_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
CONTRACT_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

APP_SHELL_CONTRACT = "app.shell.v1"
PROFILE_SCHEMA = "io.tobkiri.profile.v4"
PACK_SCHEMA = "io.tobkiri.pack.v4"
PRESENTATION_CONTRIBUTION_SCHEMA = "io.tobkiri.presentation.contribution.v1"

GRAPHICAL_FAMILY = "graphical"
TERMINAL_FAMILY = "terminal"
HEADLESS_FAMILY = "headless"
SUPPORTED_PRESENTATION_FAMILIES = frozenset({GRAPHICAL_FAMILY, TERMINAL_FAMILY, HEADLESS_FAMILY})


def _required_string(value: Any, field_name: str, *, pattern: re.Pattern[str] | None = None) -> str:
    """Return a non-empty string or raise a catalog error."""
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{field_name} must be a non-empty string")
    result = value.strip()
    if pattern is not None and pattern.fullmatch(result) is None:
        raise CatalogError(f"{field_name} has an invalid value: {result!r}")
    return result


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    """Normalize a list of non-empty strings without accepting scalar fallbacks."""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise CatalogError(f"{field_name} must be an array")
    result: list[str] = []
    for item in value:
        result.append(_required_string(item, field_name))
    if len(set(result)) != len(result):
        raise CatalogError(f"{field_name} must not contain duplicates")
    return tuple(result)


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    """Return a mapping or raise a useful validation error."""
    if not isinstance(value, Mapping):
        raise CatalogError(f"{field_name} must be an object")
    return value


@dataclass(frozen=True)
class ArtifactVariant:
    """A complete, prebuilt executable variant pinned by ProfileLock."""

    variant_id: str
    platform: str
    architecture: str
    artifact_ref: str
    digest: str
    entrypoint: str
    artifact_kind: str = "prebuilt"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], field_name: str) -> "ArtifactVariant":
        """Build a variant from a manifest object."""
        digest = _required_string(value.get("digest"), f"{field_name}.digest")
        if DIGEST_RE.fullmatch(digest) is None:
            raise CatalogError(f"{field_name}.digest must be a sha256 digest")
        return cls(
            variant_id=_required_string(value.get("variant_id"), f"{field_name}.variant_id"),
            platform=_required_string(value.get("platform"), f"{field_name}.platform"),
            architecture=_required_string(value.get("architecture"), f"{field_name}.architecture"),
            artifact_ref=_required_string(value.get("artifact_ref"), f"{field_name}.artifact_ref"),
            digest=digest,
            entrypoint=_required_string(value.get("entrypoint"), f"{field_name}.entrypoint"),
            artifact_kind=str(value.get("artifact_kind") or "prebuilt").strip(),
        )


@dataclass(frozen=True)
class PresentationContribution:
    """A declarative or structured presentation contribution."""

    contribution_id: str
    owner_pack_id: str
    presentation_family: str
    contract_id: str
    artifact_ref: str
    digest: str
    presentation_kind: str
    technology: str
    label: str = ""
    host_authority: str = "none"
    materialization: str = "selected_only"

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        field_name: str,
        *,
        default_owner_pack_id: str,
    ) -> "PresentationContribution":
        """Build a contribution and reject unknown presentation families."""
        family = _required_string(
            value.get("presentation_family"), f"{field_name}.presentation_family"
        )
        if family not in SUPPORTED_PRESENTATION_FAMILIES - {HEADLESS_FAMILY}:
            raise CatalogError(f"{field_name}.presentation_family is not selectable: {family!r}")
        owner = str(value.get("owner_pack_id") or default_owner_pack_id).strip()
        _required_string(owner, f"{field_name}.owner_pack_id", pattern=PACK_ID_RE)
        digest = _required_string(value.get("digest"), f"{field_name}.digest")
        if DIGEST_RE.fullmatch(digest) is None:
            raise CatalogError(f"{field_name}.digest must be a sha256 digest")
        materialization = str(value.get("materialization") or "selected_only").strip()
        if materialization != "selected_only":
            raise CatalogError(f"{field_name}.materialization must be selected_only")
        return cls(
            contribution_id=_required_string(
                value.get("contribution_id"), f"{field_name}.contribution_id"
            ),
            owner_pack_id=owner,
            presentation_family=family,
            contract_id=_required_string(
                value.get("contract_id"), f"{field_name}.contract_id", pattern=CONTRACT_ID_RE
            ),
            artifact_ref=_required_string(value.get("artifact_ref"), f"{field_name}.artifact_ref"),
            digest=digest,
            presentation_kind=_required_string(
                value.get("presentation_kind"), f"{field_name}.presentation_kind"
            ),
            technology=_required_string(value.get("technology"), f"{field_name}.technology"),
            label=str(value.get("label") or value.get("contribution_id") or "").strip(),
            host_authority=str(value.get("host_authority") or "none").strip(),
            materialization=materialization,
        )


@dataclass(frozen=True)
class PackDefinition:
    """Manifest-level identity and composition metadata for one v4 pack."""

    pack_id: str
    version: str
    kind: str
    display_name: str
    source_dir: Path
    contracts: tuple[str, ...] = ()
    backend_provider_ids: tuple[str, ...] = ()
    state_owners: tuple[str, ...] = ()
    shell_contract: str | None = None
    presentation_family: str | None = None
    presentation_kind: str | None = None
    technology: str | None = None
    capabilities: tuple[str, ...] = ()
    consumes_contracts: tuple[str, ...] = ()
    shell_requirement_families: tuple[str, ...] = ()
    shell_requirement_capabilities: tuple[str, ...] = ()
    contributions: tuple[PresentationContribution, ...] = ()
    variants: tuple[ArtifactVariant, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_file(cls, manifest_path: Path) -> "PackDefinition":
        """Load and validate one pack manifest without executing pack code."""
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"Cannot read pack manifest {manifest_path}: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise CatalogError(f"Pack manifest must be an object: {manifest_path}")
        schema = str(raw.get("schema") or "").strip()
        if schema != PACK_SCHEMA:
            raise CatalogError(f"{manifest_path}: schema must be {PACK_SCHEMA}")
        pack_id = _required_string(raw.get("pack_id"), "pack_id", pattern=PACK_ID_RE)
        kind = _required_string(raw.get("kind"), f"{pack_id}.kind")
        if kind not in {
            "base",
            "provider",
            "shell",
            "application_runtime",
            "development_toolchain",
        }:
            raise CatalogError(f"{pack_id}.kind is not supported: {kind!r}")
        if kind == "base" and any(
            key in raw for key in ("shell_contract", "presentation_family", "technology")
        ):
            raise CatalogError(f"{pack_id}: Base Packs cannot select a presentation technology")
        contracts = _mapping(raw.get("contracts") or {}, f"{pack_id}.contracts")
        provides = _string_tuple(contracts.get("provides"), f"{pack_id}.contracts.provides")
        consumes = _string_tuple(raw.get("consumes_contracts"), f"{pack_id}.consumes_contracts")
        backend = _mapping(raw.get("backend") or {}, f"{pack_id}.backend")
        shell_requirements = _mapping(
            raw.get("shell_requirements") or {}, f"{pack_id}.shell_requirements"
        )
        family_value = raw.get("presentation_family")
        family = str(family_value).strip() if family_value is not None else None
        if family is not None and family not in SUPPORTED_PRESENTATION_FAMILIES:
            raise CatalogError(f"{pack_id}.presentation_family is invalid: {family!r}")
        shell_contract_value = raw.get("shell_contract")
        shell_contract = (
            _required_string(
                shell_contract_value, f"{pack_id}.shell_contract", pattern=CONTRACT_ID_RE
            )
            if shell_contract_value is not None
            else None
        )
        if kind == "shell" and shell_contract != APP_SHELL_CONTRACT:
            raise CatalogError(f"{pack_id}: shell packs must provide {APP_SHELL_CONTRACT}")
        if kind == "shell" and APP_SHELL_CONTRACT not in provides:
            raise CatalogError(f"{pack_id}: contracts.provides must include {APP_SHELL_CONTRACT}")
        contribution_values = raw.get("contributions") or []
        if not isinstance(contribution_values, list):
            raise CatalogError(f"{pack_id}.contributions must be an array")
        contributions = tuple(
            PresentationContribution.from_mapping(
                _mapping(value, f"{pack_id}.contributions[{index}]"),
                f"{pack_id}.contributions[{index}]",
                default_owner_pack_id=pack_id,
            )
            for index, value in enumerate(contribution_values)
        )
        contribution_ids = [item.contribution_id for item in contributions]
        if len(set(contribution_ids)) != len(contribution_ids):
            raise CatalogError(f"{pack_id}.contributions contains duplicate IDs")
        variant_values = raw.get("variants") or []
        if not isinstance(variant_values, list):
            raise CatalogError(f"{pack_id}.variants must be an array")
        variants = tuple(
            ArtifactVariant.from_mapping(
                _mapping(value, f"{pack_id}.variants[{index}]"),
                f"{pack_id}.variants[{index}]",
            )
            for index, value in enumerate(variant_values)
        )
        variant_ids = [item.variant_id for item in variants]
        if len(set(variant_ids)) != len(variant_ids):
            raise CatalogError(f"{pack_id}.variants contains duplicate IDs")
        return cls(
            pack_id=pack_id,
            version=_required_string(raw.get("version"), f"{pack_id}.version"),
            kind=kind,
            display_name=_required_string(raw.get("display_name"), f"{pack_id}.display_name"),
            source_dir=manifest_path.parent,
            contracts=provides,
            backend_provider_ids=_string_tuple(
                backend.get("provider_ids"), f"{pack_id}.backend.provider_ids"
            ),
            state_owners=_string_tuple(
                backend.get("state_owners"), f"{pack_id}.backend.state_owners"
            ),
            shell_contract=shell_contract,
            presentation_family=family,
            presentation_kind=(
                str(raw.get("presentation_kind")).strip()
                if raw.get("presentation_kind") is not None
                else None
            ),
            technology=(
                str(raw.get("technology")).strip() if raw.get("technology") is not None else None
            ),
            capabilities=_string_tuple(raw.get("capabilities"), f"{pack_id}.capabilities"),
            consumes_contracts=consumes,
            shell_requirement_families=_string_tuple(
                shell_requirements.get("presentation_families"),
                f"{pack_id}.shell_requirements.presentation_families",
            ),
            shell_requirement_capabilities=_string_tuple(
                shell_requirements.get("capabilities"),
                f"{pack_id}.shell_requirements.capabilities",
            ),
            contributions=contributions,
            variants=variants,
            raw=dict(raw),
        )

    @property
    def is_shell(self) -> bool:
        """Whether the manifest is a replaceable interaction shell."""
        return self.kind == "shell"

    @property
    def is_production_launchable(self) -> bool:
        """Whether this pack describes a production prebuilt launch surface."""
        production = self.raw.get("production")
        return bool(isinstance(production, Mapping) and production.get("launchable"))

    def select_variant(self, platform: str, architecture: str) -> ArtifactVariant:
        """Select one exact platform variant; never fall back across platforms."""
        matches = tuple(
            variant
            for variant in self.variants
            if variant.platform == platform and variant.architecture == architecture
        )
        if len(matches) != 1:
            raise CatalogError(
                f"{self.pack_id} has {len(matches)} variants for "
                f"{platform}/{architecture}; exact selection is required"
            )
        return matches[0]
