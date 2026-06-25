from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping


RUNTIME_CAPABILITIES = frozenset(
    {
        "sandbox.exec",
        "sandbox.files",
        "sandbox.terminal.exec",
        "sandbox.workspace.read",
        "sandbox.workspace.write",
        "sandbox.workspace.diff",
        "sandbox.artifact.export",
        "sandbox.overlay_workspace",
        "sandbox.network_policy",
        "sandbox.resource_limits",
        "sandbox.profile_runtime",
        "sandbox.bubblewrap",
        "runtime.managed_install",
    }
)


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "info"
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeProviderStatus:
    provider_id: str
    platform: str
    available: bool
    installed: bool
    ready: bool
    version: str | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    missing_requirements: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "missing_requirements", tuple(self.missing_requirements))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True)
class RuntimeRequirements:
    profile_id: str
    template_id: str = "pack.safe"
    provider_id: str | None = None
    required_capabilities: frozenset[str] = field(default_factory=lambda: frozenset({"sandbox.exec"}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_capabilities", frozenset(self.required_capabilities))

    @property
    def runtime_id(self) -> str:
        digest = hashlib.sha256(str(self.profile_id or "").encode("utf-8")).hexdigest()[:16]
        return f"rumi-profile-{digest}"


@dataclass(frozen=True)
class ResourceLimits:
    memory_max: str = "512M"
    memory_swap_max: str = "0"
    cpu_quota: str = "100%"
    tasks_max: int = 128
    runtime_max_sec: int = 60


@dataclass(frozen=True)
class NetworkPolicy:
    mode: str = "off"
    domains: tuple[str, ...] = ()
    ports: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "domains", tuple(self.domains))
        object.__setattr__(self, "ports", tuple(int(port) for port in self.ports))


@dataclass(frozen=True)
class SandboxCreateSpec:
    profile_id: str
    pack_id: str
    function_id: str = ""
    template_id: str = "pack.safe"
    workspace_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def sandbox_id(self) -> str:
        seed = f"{self.profile_id}:{self.pack_id}:{self.function_id}:{self.workspace_id}"
        return "sbx_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class ProviderInstance:
    provider_id: str
    provider_instance_id: str
    sandbox_id: str
    runtime_id: str
    state: str = "created"
    opaque_state: Mapping[str, Any] = field(default_factory=dict)
    generation: int = 0


@dataclass
class SandboxInstance:
    sandbox_id: str = field(default_factory=lambda: "sbx_" + uuid.uuid4().hex[:24])
    provider_id: str = ""
    runtime_id: str = ""
    profile_id: str = ""
    pack_id: str = ""
    state: str = "creating"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def model_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: model_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, tuple):
        return [model_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: model_to_dict(item) for key, item in value.items()}
    return value
