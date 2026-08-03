"""Fail-closed Base Pack/Shell Provider profile resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml  # type: ignore[import-untyped]

from .catalog import PackCatalog
from .errors import ProfileResolutionError
from .model import (
    APP_SHELL_CONTRACT,
    ArtifactVariant,
    PackDefinition,
    PresentationContribution,
)


@dataclass(frozen=True)
class SelectedArtifact:
    """One exact descriptor selected for materialization."""

    artifact_id: str
    pack_id: str
    artifact_ref: str
    source_path: Path
    digest: str
    kind: str


@dataclass(frozen=True)
class ResolvedProfile:
    """The immutable composition result a ProfileLock can bind."""

    profile_id: str
    profile_revision: str
    base_pack_id: str
    shell_contract: str
    shell_provider_id: str
    presentation_family: str
    technology: str
    platform: str
    architecture: str
    backend_provider_ids: tuple[str, ...]
    state_owners: tuple[str, ...]
    selected_contributions: tuple[PresentationContribution, ...]
    omitted_contribution_ids: tuple[str, ...]
    selected_artifacts: tuple[SelectedArtifact, ...]
    base_pack: PackDefinition
    shell_provider: PackDefinition

    @property
    def backend_identity(self) -> tuple[str, ...]:
        """Return backend identities for shell-invariance assertions."""
        return self.backend_provider_ids


def load_profile_document(profile_path: Path) -> dict[str, Any]:
    """Load a YAML or JSON profile without importing runtime code."""
    try:
        raw = profile_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileResolutionError(f"cannot read profile {profile_path}: {exc}") from exc
    try:
        loaded = (
            yaml.safe_load(raw)
            if profile_path.suffix.lower() in {".yaml", ".yml"}
            else json.loads(raw)
        )
    except (ValueError, yaml.YAMLError) as exc:
        raise ProfileResolutionError(f"cannot parse profile {profile_path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ProfileResolutionError("profile document must be an object")
    return loaded


def resolve_profile(
    profile: Mapping[str, Any] | Path,
    catalog: PackCatalog | None = None,
    *,
    platform_name: str | None = None,
    architecture: str | None = None,
) -> ResolvedProfile:
    """Resolve one exact Base Pack and one compatible ``app.shell.v1`` provider.

    ``platform`` and ``architecture`` are required by the v4 profile contract.
    A caller may supply them explicitly for conformance tests, but the resolver
    never chooses a different variant when the requested one is unavailable.
    """
    document = load_profile_document(profile) if isinstance(profile, Path) else dict(profile)
    if catalog is None:
        catalog = PackCatalog.from_assets_root()
    if document.get("schema") != "io.tobkiri.profile.v4":
        raise ProfileResolutionError("profile schema must be io.tobkiri.profile.v4")
    profile_id = str(document.get("profile_id") or "").strip()
    if not profile_id:
        raise ProfileResolutionError("profile_id is required")
    composition = document.get("composition")
    if composition is not None:
        if not isinstance(composition, Mapping):
            raise ProfileResolutionError("composition must be an object")
        source = dict(composition)
    else:
        source = document
    base = source.get("base")
    shell = source.get("shell")
    if not isinstance(base, Mapping):
        raise ProfileResolutionError("base.pack is required; legacy base_pack needs migration")
    if not isinstance(shell, Mapping):
        raise ProfileResolutionError("shell.provider is required; shell selection is not implicit")
    base_pack_id = str(base.get("pack") or "").strip()
    if not base_pack_id:
        raise ProfileResolutionError("base.pack is required")
    if any(key in base for key in ("type", "technology", "launch", "command")):
        raise ProfileResolutionError("Base Pack cannot select a UI technology or launch command")
    base_pack = catalog.require(base_pack_id)
    if base_pack.kind != "base":
        raise ProfileResolutionError(f"{base_pack_id} is not a Base Pack")
    if not base_pack.backend_provider_ids:
        raise ProfileResolutionError(f"{base_pack_id} does not declare a backend Provider")
    if not base_pack.state_owners:
        raise ProfileResolutionError(f"{base_pack_id} does not declare state owners")
    for provider_id in base_pack.backend_provider_ids:
        provider = catalog.require(provider_id)
        if provider.kind != "provider":
            raise ProfileResolutionError(
                f"{provider_id} cannot back Base Pack {base_pack_id}: not a backend Provider"
            )
    shell_requirements = base_pack.raw.get("shell_requirements")
    if not isinstance(shell_requirements, Mapping) or (
        shell_requirements.get("contract") != APP_SHELL_CONTRACT
    ):
        raise ProfileResolutionError(
            f"{base_pack_id} must require the {APP_SHELL_CONTRACT} Shell contract"
        )
    shell_contract = str(shell.get("contract") or "").strip()
    shell_provider_id = str(shell.get("provider") or "").strip()
    if shell_contract != APP_SHELL_CONTRACT:
        raise ProfileResolutionError(f"shell.contract must be {APP_SHELL_CONTRACT}")
    if not shell_provider_id:
        raise ProfileResolutionError("shell.provider must be an exact provider ID")
    if "providers" in shell:
        raise ProfileResolutionError("shell.providers is ambiguous; choose exactly one provider")
    shell_provider = catalog.require(shell_provider_id)
    if not shell_provider.is_shell:
        raise ProfileResolutionError(f"{shell_provider_id} is not a Shell Pack")
    if shell_provider.shell_contract != shell_contract:
        raise ProfileResolutionError(
            f"{shell_provider_id} does not provide the requested {shell_contract}"
        )
    _validate_shell_production(shell_provider)
    _validate_shell_security(shell_provider)
    family = shell_provider.presentation_family
    if not family:
        raise ProfileResolutionError(f"{shell_provider_id} has no presentation family")
    if family not in base_pack.shell_requirement_families:
        raise ProfileResolutionError(
            f"{shell_provider_id} is incompatible with Base Pack {base_pack_id}: {family}"
        )
    missing_capabilities = sorted(
        set(base_pack.shell_requirement_capabilities) - set(shell_provider.capabilities)
    )
    if missing_capabilities:
        raise ProfileResolutionError(
            f"{shell_provider_id} does not satisfy shell capabilities: {missing_capabilities}"
        )
    selected_platform = str(
        platform_name or _platform_value(document.get("platform"), "os")
    ).strip()
    selected_architecture = str(
        architecture or _platform_value(document.get("platform"), "architecture")
    ).strip()
    if not selected_platform or not selected_architecture:
        raise ProfileResolutionError("platform.os and platform.architecture are required")
    variant = _select_shell_variant(shell_provider, selected_platform, selected_architecture)
    selected_contributions, omitted = _select_contributions(
        base_pack,
        shell_provider,
    )
    selected_artifacts = [
        SelectedArtifact(
            artifact_id=f"{shell_provider.pack_id}:{variant.variant_id}",
            pack_id=shell_provider.pack_id,
            artifact_ref=variant.artifact_ref,
            source_path=_safe_asset_path(shell_provider.source_dir, variant.artifact_ref),
            digest=variant.digest,
            kind="shell_variant",
        )
    ]
    _verify_artifact_digest(
        selected_artifacts[0].source_path,
        selected_artifacts[0].digest,
        selected_artifacts[0].artifact_id,
    )
    for contribution in selected_contributions:
        owner = catalog.get(contribution.owner_pack_id)
        if owner is None:
            raise ProfileResolutionError(
                f"contribution owner is not cataloged: {contribution.owner_pack_id}"
            )
        source_path = _safe_asset_path(
            owner.source_dir,
            contribution.artifact_ref,
            allowed_root=owner.source_dir.parent.parent,
        )
        _verify_artifact_digest(source_path, contribution.digest, contribution.contribution_id)
        selected_artifacts.append(
            SelectedArtifact(
                artifact_id=contribution.contribution_id,
                pack_id=owner.pack_id,
                artifact_ref=contribution.artifact_ref,
                source_path=source_path,
                digest=contribution.digest,
                kind="presentation_contribution",
            )
        )
    return ResolvedProfile(
        profile_id=profile_id,
        profile_revision=str(
            document.get("profile_revision") or document.get("version") or "4.0.0"
        ),
        base_pack_id=base_pack.pack_id,
        shell_contract=shell_contract,
        shell_provider_id=shell_provider.pack_id,
        presentation_family=family,
        technology=str(shell_provider.technology or "").strip(),
        platform=selected_platform,
        architecture=selected_architecture,
        backend_provider_ids=base_pack.backend_provider_ids,
        state_owners=base_pack.state_owners,
        selected_contributions=selected_contributions,
        omitted_contribution_ids=omitted,
        selected_artifacts=tuple(selected_artifacts),
        base_pack=base_pack,
        shell_provider=shell_provider,
    )


def _platform_value(value: Any, key: str) -> str:
    return str(value.get(key) or "").strip() if isinstance(value, Mapping) else ""


def _select_shell_variant(
    shell_provider: PackDefinition,
    platform_name: str,
    architecture: str,
) -> ArtifactVariant:
    try:
        return shell_provider.select_variant(platform_name, architecture)
    except Exception as exc:
        raise ProfileResolutionError(
            f"no exact prebuilt variant for {shell_provider.pack_id} "
            f"on {platform_name}/{architecture}: {exc}"
        ) from exc


def _select_contributions(
    base_pack: PackDefinition,
    shell_provider: PackDefinition,
) -> tuple[tuple[PresentationContribution, ...], tuple[str, ...]]:
    consumed = set(shell_provider.consumes_contracts)
    selected: list[PresentationContribution] = []
    omitted: list[str] = []
    for contribution in base_pack.contributions:
        compatible = (
            contribution.presentation_family == shell_provider.presentation_family
            and contribution.contract_id in consumed
        )
        if compatible:
            selected.append(contribution)
        else:
            omitted.append(contribution.contribution_id)
    if not selected:
        raise ProfileResolutionError(
            f"{shell_provider.pack_id} selected no compatible Base Pack contributions"
        )
    return tuple(selected), tuple(omitted)


def _validate_shell_production(shell_provider: PackDefinition) -> None:
    """Reject shells that could build or reach development commands in production."""
    production = shell_provider.raw.get("production")
    if not isinstance(production, Mapping):
        raise ProfileResolutionError(
            f"{shell_provider.pack_id} has no production launch declaration"
        )
    required_values = {
        "launchable": True,
        "prebuilt_only": True,
        "build_during_activation": False,
        "dev_commands_reachable": False,
    }
    for field_name, expected in required_values.items():
        if production.get(field_name) is not expected:
            raise ProfileResolutionError(
                f"{shell_provider.pack_id}.production.{field_name} must be {expected!r}"
            )


def _validate_shell_security(shell_provider: PackDefinition) -> None:
    """Require the shell's host-boundary declarations before activation."""
    security = shell_provider.raw.get("security")
    if not isinstance(security, Mapping):
        raise ProfileResolutionError(f"{shell_provider.pack_id} has no security boundary")
    if security.get("host_authority") not in {
        "authenticated_broker_requests_only",
        "structured_protocol_only",
    }:
        raise ProfileResolutionError(f"{shell_provider.pack_id} must use brokered shell authority")
    if security.get("trusted_attention_surface") != "host_owned":
        raise ProfileResolutionError(
            f"{shell_provider.pack_id} must keep trusted attention Host-owned"
        )
    if security.get("native_plugin_loading") != "forbidden":
        raise ProfileResolutionError(
            f"{shell_provider.pack_id} cannot load arbitrary native plugins"
        )
    if (
        shell_provider.presentation_family == "graphical"
        and not str(security.get("origin_partition") or "").strip()
    ):
        raise ProfileResolutionError(
            f"{shell_provider.pack_id} must declare a graphical origin partition"
        )
    if shell_provider.presentation_family == "terminal":
        protocol = shell_provider.raw.get("cli_protocol")
        if not isinstance(protocol, Mapping) or protocol.get("version") != "cli.io.v1":
            raise ProfileResolutionError(f"{shell_provider.pack_id} must declare cli.io.v1")
        if protocol.get("structured_stdio") is not True:
            raise ProfileResolutionError(f"{shell_provider.pack_id} must use structured stdio")
        if protocol.get("raw_host_terminal") is not False:
            raise ProfileResolutionError(
                f"{shell_provider.pack_id} cannot use raw Host terminal authority"
            )


def _verify_artifact_digest(path: Path, expected: str, artifact_id: str) -> None:
    """Verify a selected descriptor before it enters the immutable resolution."""
    actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ProfileResolutionError(f"artifact digest mismatch: {artifact_id}")


def _safe_asset_path(
    pack_dir: Path,
    artifact_ref: str,
    *,
    allowed_root: Path | None = None,
) -> Path:
    """Resolve a descriptor path without permitting traversal outside the catalog."""
    candidate = (pack_dir / artifact_ref).resolve()
    root = (allowed_root or pack_dir).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ProfileResolutionError(
            f"artifact reference escapes pack directory: {artifact_ref!r}"
        ) from exc
    if not candidate.is_file():
        raise ProfileResolutionError(f"selected artifact is missing: {artifact_ref}")
    return candidate
