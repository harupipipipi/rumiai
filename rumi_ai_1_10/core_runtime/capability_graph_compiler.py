"""Domain-neutral Capability Graph compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .binding_handlers import BindingHandlerResolver
from .graph_models import GraphDefinition, GraphEdge, GraphNodeInstance
from .interface_registry import InterfaceRegistry
from .node_models import NodeDefinition
from .port_standards import validate_graph_ports
from .profile_models import ProfileDefinition


RUNTIME_PROFILE_VERSION = "rumi.runtime_profile.v1"


@dataclass
class CompileContext:
    graph: GraphDefinition
    profile: ProfileDefinition
    nodes: Dict[str, NodeDefinition]
    runtime_profile: Dict[str, Any]
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    def diagnose(self, level: str, code: str, message: str, **meta: Any) -> None:
        self.diagnostics.append(_diagnostic(level, code, message, **meta))


@dataclass
class GraphCompileResult:
    ok: bool
    runtime_profile: Optional[Dict[str, Any]]
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "runtime_profile": self.runtime_profile,
            "diagnostics": list(self.diagnostics),
        }


class CapabilityGraphCompiler:
    """Compile a validated Capability Graph into a runtime profile dict."""

    def __init__(
        self,
        *,
        interface_registry: Optional[InterfaceRegistry] = None,
        binding_resolver: Optional[BindingHandlerResolver] = None,
    ) -> None:
        self.interface_registry = interface_registry
        self.binding_resolver = binding_resolver or BindingHandlerResolver(
            interface_registry=interface_registry,
        )

    def compile(
        self,
        graph: GraphDefinition,
        *,
        profile: ProfileDefinition,
        nodes: Dict[str, NodeDefinition],
        register: bool = True,
    ) -> GraphCompileResult:
        diagnostics: List[Dict[str, Any]] = []
        validation = validate_graph_ports(graph, nodes=nodes, profile=profile)
        diagnostics.extend(validation.diagnostics)
        if not validation.ok:
            return GraphCompileResult(
                ok=False,
                runtime_profile=None,
                diagnostics=diagnostics,
            )

        runtime_profile = _make_runtime_profile(graph, profile, nodes)
        context = CompileContext(
            graph=graph,
            profile=profile,
            nodes=nodes,
            runtime_profile=runtime_profile,
            diagnostics=diagnostics,
        )

        instances = {instance.id: instance for instance in graph.nodes}
        for instance in graph.nodes:
            self._run_node_compile_handler(instance, instances=instances, context=context)
        for edge in graph.edges:
            self._run_edge_binding_handler(edge, instances=instances, context=context)

        ok = not any(item.get("level") == "error" for item in context.diagnostics)
        if ok and register and self.interface_registry is not None:
            registry_key = f"runtime_profile.{profile.profile_id}.{graph.graph_id}"
            self.interface_registry.register(
                registry_key,
                runtime_profile,
                meta={
                    "source": "capability_graph_compiler",
                    "profile_id": profile.profile_id,
                    "graph_id": graph.graph_id,
                    "_system": True,
                },
            )
            runtime_profile["registry_key"] = registry_key

        return GraphCompileResult(
            ok=ok,
            runtime_profile=runtime_profile if ok else None,
            diagnostics=list(context.diagnostics),
        )

    def _run_node_compile_handler(
        self,
        instance: GraphNodeInstance,
        *,
        instances: Dict[str, GraphNodeInstance],
        context: CompileContext,
    ) -> None:
        node = context.nodes.get(instance.ref)
        handler_id = node.bindings.compile if node else None
        if not handler_id:
            return
        self._resolve_and_call(
            handler_id,
            context=context,
            instance=instance,
            edge=None,
            source=None,
            target=instance,
            binding_scope="node.compile",
        )

    def _run_edge_binding_handler(
        self,
        edge: GraphEdge,
        *,
        instances: Dict[str, GraphNodeInstance],
        context: CompileContext,
    ) -> None:
        target = instances.get(edge.target.node_id)
        if target is None:
            return
        target_node = context.nodes.get(target.ref)
        if target_node is None:
            return
        handler_id = target_node.bindings.on_input.get(edge.target.port_id)
        if not handler_id:
            return
        self._resolve_and_call(
            handler_id,
            context=context,
            instance=target,
            edge=edge,
            source=instances.get(edge.source.node_id),
            target=target,
            binding_scope="edge.on_input",
        )

    def _resolve_and_call(
        self,
        handler_id: str,
        *,
        context: CompileContext,
        instance: GraphNodeInstance,
        edge: Optional[GraphEdge],
        source: Optional[GraphNodeInstance],
        target: Optional[GraphNodeInstance],
        binding_scope: str,
    ) -> None:
        resolution = self.binding_resolver.resolve(handler_id)
        context.diagnostics.extend(resolution.diagnostics)
        binding_record = {
            "handler_id": handler_id,
            "scope": binding_scope,
            "node_instance_id": instance.id,
            "edge_id": edge.id if edge else None,
            "resolved": resolution.handler is not None,
        }
        context.runtime_profile["bindings"].append(binding_record)
        if resolution.handler is None:
            return
        try:
            result = resolution.handler(
                context=context,
                runtime_profile=context.runtime_profile,
                graph=context.graph,
                profile=context.profile,
                nodes=context.nodes,
                instance=instance,
                edge=edge,
                source=source,
                target=target,
            )
        except TypeError:
            result = resolution.handler(context)
        except Exception as exc:
            context.diagnose(
                "error",
                "binding_handler_failed",
                f"Binding handler '{handler_id}' failed: {exc}",
                handler_id=handler_id,
                node_instance_id=instance.id,
                edge_id=edge.id if edge else None,
            )
            return
        if isinstance(result, dict):
            diagnostics = result.get("diagnostics")
            if isinstance(diagnostics, list):
                context.diagnostics.extend(
                    item for item in diagnostics if isinstance(item, dict)
                )
            status = result.get("status") or result.get("_kernel_step_status")
            if status == "failed":
                context.diagnose(
                    "error",
                    "binding_handler_reported_failed",
                    f"Binding handler '{handler_id}' reported failure",
                    handler_id=handler_id,
                    node_instance_id=instance.id,
                    edge_id=edge.id if edge else None,
                )


def _make_runtime_profile(
    graph: GraphDefinition,
    profile: ProfileDefinition,
    nodes: Dict[str, NodeDefinition],
) -> Dict[str, Any]:
    node_instances: Dict[str, Dict[str, Any]] = {}
    for instance in graph.nodes:
        node = nodes.get(instance.ref)
        node_instances[instance.id] = {
            "id": instance.id,
            "node_id": instance.ref,
            "node": node.to_dict() if node else None,
            "settings": dict(profile.node_settings.get(instance.ref, {})),
            "metadata": dict(instance.metadata),
        }
    return {
        "version": RUNTIME_PROFILE_VERSION,
        "runtime_profile_id": f"{profile.profile_id}.{graph.graph_id}",
        "profile_id": profile.profile_id,
        "graph_id": graph.graph_id,
        "graph": graph.to_dict(),
        "profile": profile.to_dict(),
        "nodes": node_instances,
        "edges": [edge.to_dict() for edge in graph.edges],
        "bindings": [],
        "metadata": {
            "compiler": "core_runtime.capability_graph_compiler",
        },
    }


def compile_capability_graph(
    graph: GraphDefinition,
    *,
    profile: ProfileDefinition,
    nodes: Dict[str, NodeDefinition],
    interface_registry: Optional[InterfaceRegistry] = None,
    register: bool = True,
) -> GraphCompileResult:
    compiler = CapabilityGraphCompiler(interface_registry=interface_registry)
    return compiler.compile(
        graph,
        profile=profile,
        nodes=nodes,
        register=register,
    )


def _diagnostic(
    level: str,
    code: str,
    message: str,
    **meta: Any,
) -> Dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        **meta,
    }
