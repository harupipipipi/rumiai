"""Bridge Startup Profiles to compiled Capability Graph runtime profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .capability_graph_compiler import CapabilityGraphCompiler
from .capability_graph_loader import CapabilityGraphLoader
from .ecosystem_nodes import EcosystemNodeRegistry
from .interface_registry import InterfaceRegistry
from .profile_loader import CapabilityProfileLoader


@dataclass
class StartupCapabilityCompileResult:
    ok: bool
    graph_id: Optional[str] = None
    capability_profile_id: Optional[str] = None
    runtime_profile_key: Optional[str] = None
    runtime_profile: Optional[Dict[str, Any]] = None
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    skipped: bool = False
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "skipped": self.skipped,
            "reason": self.reason,
            "graph_id": self.graph_id,
            "capability_profile_id": self.capability_profile_id,
            "runtime_profile_key": self.runtime_profile_key,
            "runtime_profile": self.runtime_profile,
            "diagnostics": list(self.diagnostics),
        }


def compile_startup_capabilities(
    startup_profile: Dict[str, Any],
    *,
    interface_registry: InterfaceRegistry,
    approval_manager: Any = None,
    ecosystem_dir: Optional[str] = None,
) -> StartupCapabilityCompileResult:
    """Compile the startup profile's opt-in Capability Graph bridge."""
    graph_id = _string_or_none(startup_profile.get("default_graph"))
    capability_profile_id = _string_or_none(startup_profile.get("capability_profile_id"))
    diagnostics: List[Dict[str, Any]] = []

    if not graph_id:
        diagnostics.append(
            _diagnostic(
                "warning",
                "startup_graph_missing",
                "Startup profile has launch_capability_graph enabled but no default_graph",
            )
        )
        return StartupCapabilityCompileResult(
            ok=False,
            graph_id=None,
            capability_profile_id=capability_profile_id,
            diagnostics=diagnostics,
        )

    if not capability_profile_id:
        diagnostics.append(
            _diagnostic(
                "warning",
                "startup_capability_profile_missing",
                "Startup profile has launch_capability_graph enabled but no capability_profile_id",
                graph_id=graph_id,
            )
        )
        return StartupCapabilityCompileResult(
            ok=False,
            graph_id=graph_id,
            capability_profile_id=None,
            diagnostics=diagnostics,
        )

    try:
        _register_pack_binding_handlers(
            interface_registry,
            diagnostics,
            approval_manager=approval_manager,
            ecosystem_dir=ecosystem_dir,
        )

        profile_loader = CapabilityProfileLoader(
            interface_registry=interface_registry,
            approval_manager=approval_manager,
            ecosystem_dir=ecosystem_dir,
        )
        profile = profile_loader.get_profile(capability_profile_id)
        diagnostics.extend(profile_loader.diagnostics)
        if profile is None:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "capability_profile_not_found",
                    f"Capability profile '{capability_profile_id}' was not found",
                    capability_profile_id=capability_profile_id,
                )
            )
            return StartupCapabilityCompileResult(
                ok=False,
                graph_id=graph_id,
                capability_profile_id=capability_profile_id,
                diagnostics=diagnostics,
            )

        graph_loader = CapabilityGraphLoader(
            interface_registry=interface_registry,
            approval_manager=approval_manager,
            ecosystem_dir=ecosystem_dir,
        )
        graph = graph_loader.get_graph(graph_id)
        diagnostics.extend(graph_loader.diagnostics)
        if graph is None:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "startup_graph_not_found",
                    f"Capability graph '{graph_id}' was not found",
                    graph_id=graph_id,
                )
            )
            return StartupCapabilityCompileResult(
                ok=False,
                graph_id=graph_id,
                capability_profile_id=capability_profile_id,
                diagnostics=diagnostics,
            )

        node_registry = EcosystemNodeRegistry(
            interface_registry=interface_registry,
            approval_manager=approval_manager,
            ecosystem_dir=ecosystem_dir,
        )
        nodes = node_registry.load_all_nodes(register=True)
        diagnostics.extend(node_registry.diagnostics)

        compile_result = CapabilityGraphCompiler(interface_registry=interface_registry).compile(
            graph,
            profile=profile,
            nodes=dict(nodes),
            register=True,
        )
        diagnostics.extend(compile_result.diagnostics)
        runtime_profile = compile_result.runtime_profile
        runtime_profile_key = None
        if isinstance(runtime_profile, dict):
            runtime_profile_key = _string_or_none(runtime_profile.get("registry_key"))

        return StartupCapabilityCompileResult(
            ok=compile_result.ok,
            graph_id=graph_id,
            capability_profile_id=capability_profile_id,
            runtime_profile_key=runtime_profile_key,
            runtime_profile=runtime_profile,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        diagnostics.append(
            _diagnostic(
                "error",
                "startup_capability_compile_failed",
                f"Startup capability graph compile failed: {exc}",
                graph_id=graph_id,
                capability_profile_id=capability_profile_id,
            )
        )
        return StartupCapabilityCompileResult(
            ok=False,
            graph_id=graph_id,
            capability_profile_id=capability_profile_id,
            diagnostics=diagnostics,
        )


def _register_pack_binding_handlers(
    interface_registry: InterfaceRegistry,
    diagnostics: List[Dict[str, Any]],
    *,
    approval_manager: Any = None,
    ecosystem_dir: Optional[str] = None,
) -> None:
    try:
        from .capability_binding_registration import register_pack_binding_handlers
    except Exception as exc:
        diagnostics.append(
            _diagnostic(
                "warning",
                "pack_binding_registration_unavailable",
                f"Pack binding registration is unavailable: {exc}",
            )
        )
        return

    result = register_pack_binding_handlers(
        interface_registry=interface_registry,
        approval_manager=approval_manager,
        ecosystem_dir=ecosystem_dir,
    )
    diagnostics.extend(result.diagnostics)


def _string_or_none(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _diagnostic(level: str, code: str, message: str, **meta: Any) -> Dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        **meta,
    }
