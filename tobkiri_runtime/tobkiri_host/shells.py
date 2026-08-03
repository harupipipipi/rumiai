"""Orthogonal Base Pack and Shell Provider resolution interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .errors import ResolutionError
from .models import require_digest, require_identifier


class PresentationFamily(str, Enum):
    """Broad presentation family without technology-specific privilege."""

    GRAPHICAL = "graphical"
    TERMINAL = "terminal"
    HEADLESS = "headless"


@dataclass(frozen=True)
class BaseDefinition:
    """Profile composition root independent of presentation technology."""

    pack_id: str
    artifact_digest: str
    required_shell_capabilities: frozenset[str]
    optional_shell_capabilities: frozenset[str] = frozenset()
    permitted_families: frozenset[PresentationFamily] = frozenset(
        {PresentationFamily.GRAPHICAL}
    )

    def __post_init__(self) -> None:
        require_identifier(self.pack_id, "base pack_id")
        require_digest(self.artifact_digest, "base artifact")


@dataclass(frozen=True)
class ShellDefinition:
    """Exact ``app.shell.v1`` Provider request and capabilities."""

    provider_id: str
    artifact_digest: str
    contract_id: str
    family: PresentationFamily
    capabilities: frozenset[str]
    technology: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.provider_id, "shell provider_id")
        require_digest(self.artifact_digest, "shell artifact")
        if self.contract_id != "app.shell.v1":
            raise ResolutionError("Shell must implement app.shell.v1")


@dataclass(frozen=True)
class PresentationContribution:
    """Pinned UI or CLI contribution metadata, never injected native code."""

    contribution_id: str
    artifact_digest: str
    contract_id: str
    family: PresentationFamily


@dataclass(frozen=True)
class BaseShellBinding:
    """Exact independently pinned Base/Shell pair and selected contributions."""

    base: BaseDefinition
    shell: ShellDefinition
    contributions: tuple[PresentationContribution, ...]


class BaseShellResolver:
    """Resolve compatibility without Runtime technology enum branches."""

    def resolve(
        self,
        base: BaseDefinition,
        shell: ShellDefinition,
        contributions: Sequence[PresentationContribution],
    ) -> BaseShellBinding:
        """Reject incompatible Shells and filter unselected contribution families."""
        if shell.family not in base.permitted_families:
            raise ResolutionError("Shell presentation family is not permitted")
        missing = base.required_shell_capabilities - shell.capabilities
        if missing:
            raise ResolutionError(f"Shell capabilities are missing: {sorted(missing)}")
        selected = tuple(
            sorted(
                (
                    contribution
                    for contribution in contributions
                    if contribution.family is shell.family
                ),
                key=lambda contribution: contribution.contribution_id,
            )
        )
        return BaseShellBinding(base=base, shell=shell, contributions=selected)
