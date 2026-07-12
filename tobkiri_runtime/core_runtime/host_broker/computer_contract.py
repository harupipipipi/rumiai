"""Model-agnostic contract for native computer hosts.

The host contract deliberately contains no public tool, provider, profile, or
prompt concepts. Packs may build their own model-facing tools on top of these
native primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ComputerHostTarget:
    """Stable native surface binding supplied to a computer host."""

    surface_id: str
    observation_revision: str = ""
    coordinate_space: str = "window"
    selectors: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComputerHostCapabilities:
    """Capabilities advertised by a native computer host."""

    host_id: str
    platform: str
    primitives: tuple[str, ...] = ()
    can_observe: bool = True
    can_verify: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComputerHostExecutionOptions:
    """Native routing constraints selected by the tool/service layer."""

    background_only: bool = False
    verified_only: bool = False
    pid_only: bool = False


@dataclass(frozen=True)
class ComputerHostObservation:
    """Observation bound to a native surface and revision."""

    surface_id: str
    observation_revision: str
    coordinate_space: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComputerHostActionResult:
    """Normalized delivery and verification outcome for a host primitive."""

    transport: str
    delivered: bool
    effect_observed: bool = False
    postcondition_verified: bool = False
    foreground_required: bool = False
    physical_input: bool = False
    parallel_user_work_safe: bool = False
    surface_id: str = ""
    observation_revision: str = ""
    coordinate_space: str = "window"
    data: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ComputerHost(Protocol):
    """Protocol implemented by Viewer, OS-native, and fake computer hosts."""

    def probe(self) -> ComputerHostCapabilities:
        """Return host capabilities without performing an action."""

    def list_surfaces(self) -> list[dict[str, Any]]:
        """Return native surfaces addressable by this host."""

    def observe(self, target: ComputerHostTarget) -> ComputerHostObservation:
        """Observe a target and return a revision-bound snapshot."""

    def execute_primitive(
        self,
        target: ComputerHostTarget,
        primitive: str,
        args: dict[str, Any],
        options: ComputerHostExecutionOptions | None = None,
    ) -> ComputerHostActionResult:
        """Deliver one model-agnostic native primitive."""

    def verify(
        self,
        target: ComputerHostTarget,
        expected_postcondition: dict[str, Any],
    ) -> ComputerHostActionResult:
        """Observe whether a postcondition holds for the bound target."""
