from __future__ import annotations

import sys
from typing import Any, Dict, List
from pathlib import Path

_DEFAULTSPACK_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(_DEFAULTSPACK_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_DEFAULTSPACK_IMPORT_ROOT))

from core_runtime.profile_paths import active_profile_id
from core_runtime.profile_workspace import ProfileWorkspaceManager
from core_runtime.profile_runtime_selection import apply_profile_graph_selection

from domain.external.input_profile_registry import InputProfileRegistry
from domain.tool.registry import ToolRegistry
from domain.webhook.endpoint_store import WebhookEndpointStore
from transport.registry import canonical_http_route_specs


def build_api_map(*, profile_id: str | None = None, focus: str | None = None) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    for spec in canonical_http_route_specs(include_always_available=True):
        route_id = f"{spec.method} {spec.pattern}"
        route_node_id = f"api:{route_id}"
        nodes[route_node_id] = {
            "id": route_node_id,
            "kind": "api",
            "label": route_id,
            "ref": route_id,
            "metadata": {
                "method": spec.method,
                "path": spec.pattern,
                "block_module": spec.block_module,
                "function_name": spec.function_name,
                "flow_id": spec.flow_id,
                "fallback_block_module": spec.fallback_block_module,
            },
        }
        if spec.flow_id:
            flow_node_id = f"flow:{spec.flow_id}"
            nodes.setdefault(
                flow_node_id,
                {"id": flow_node_id, "kind": "flow", "label": spec.flow_id, "ref": spec.flow_id, "metadata": {"flow_id": spec.flow_id}},
            )
            edges.append(_edge(route_node_id, flow_node_id, "handled_by", {"flow_id": spec.flow_id}))
        for key, value in (("block_module", spec.block_module), ("function_name", spec.function_name), ("fallback_block_module", spec.fallback_block_module)):
            ref = str(value or "").strip()
            if not ref:
                continue
            node_id = f"node:{ref}"
            nodes.setdefault(
                node_id,
                {"id": node_id, "kind": key.replace("_module", "").replace("_name", ""), "label": ref.rsplit(".", 1)[-1], "ref": ref, "metadata": {key: ref}},
            )
            edge_kind = "handled_by" if key != "fallback_block_module" else "fallback"
            edges.append(_edge(route_node_id, node_id, edge_kind, {key: ref}))

    tool_registry = ToolRegistry()
    for tool in tool_registry.list_tools():
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        if not tool_id:
            continue
        tool_node_id = f"tool:{tool_id}"
        nodes.setdefault(
            tool_node_id,
            {"id": tool_node_id, "kind": "tool", "label": str(tool.get("display_name") or tool.get("name") or tool_id), "ref": tool_id, "metadata": tool},
        )
        execution = tool.get("execution") if isinstance(tool.get("execution"), dict) else {}
        handler = str(execution.get("handler") or "").strip()
        if handler:
            handler_node_id = f"node:{handler}"
            nodes.setdefault(
                handler_node_id,
                {"id": handler_node_id, "kind": "handler", "label": handler.rsplit(":", 1)[-1], "ref": handler, "metadata": {"handler": handler}},
            )
            edges.append(_edge(tool_node_id, handler_node_id, "executes", {"handler": handler}))

    endpoint_store = WebhookEndpointStore()
    input_profiles = {profile.id: profile for profile in InputProfileRegistry().list_profiles()}
    for endpoint in endpoint_store.list_endpoints():
        endpoint_id = str(endpoint.get("id") or "").strip()
        if not endpoint_id:
            continue
        webhook_node_id = f"webhook:{endpoint_id}"
        nodes.setdefault(
            webhook_node_id,
            {"id": webhook_node_id, "kind": "webhook", "label": endpoint_id, "ref": endpoint_id, "metadata": endpoint},
        )
        input_profile_key = str(endpoint.get("input_profile_id") or "").strip()
        if input_profile_key:
            input_profile = input_profiles.get(input_profile_key)
            input_node_id = f"node:{input_profile_key}"
            nodes.setdefault(
                input_node_id,
                {
                    "id": input_node_id,
                    "kind": "input_profile",
                    "label": str(getattr(input_profile, "display_name", "") or input_profile_key),
                    "ref": input_profile_key,
                    "metadata": {"input_profile_id": input_profile_key},
                },
            )
            edges.append(_edge(webhook_node_id, input_node_id, "uses_input_profile", {"input_profile_id": input_profile_key}))

    diagnostics: List[Dict[str, Any]] = []
    profile_edges = _profile_selection_edges(profile_id)
    if profile_edges["diagnostics"]:
        diagnostics.extend(profile_edges["diagnostics"])
    for node in profile_edges["nodes"]:
        nodes[node["id"]] = node
    edges.extend(profile_edges["edges"])

    filtered_nodes = list(nodes.values())
    filtered_edges = edges
    if focus:
        focus_id = str(focus).strip()
        neighbor_ids = {focus_id}
        for edge in edges:
            if edge["from_id"] == focus_id:
                neighbor_ids.add(edge["to_id"])
            if edge["to_id"] == focus_id:
                neighbor_ids.add(edge["from_id"])
        filtered_nodes = [node for node in filtered_nodes if node["id"] in neighbor_ids]
        filtered_edges = [
            edge
            for edge in edges
            if edge["from_id"] in neighbor_ids and edge["to_id"] in neighbor_ids
        ]

    return {
        "nodes": filtered_nodes,
        "edges": filtered_edges,
        "summary": {
            "node_count": len(filtered_nodes),
            "edge_count": len(filtered_edges),
            "route_count": len([node for node in filtered_nodes if node["kind"] == "api"]),
            "tool_count": len([node for node in filtered_nodes if node["kind"] == "tool"]),
            "webhook_count": len([node for node in filtered_nodes if node["kind"] == "webhook"]),
        },
        "diagnostics": diagnostics,
    }


def _profile_selection_edges(profile_id: str | None) -> Dict[str, Any]:
    resolved_profile_id = str(profile_id or active_profile_id() or "").strip()
    if not resolved_profile_id:
        return {"nodes": [], "edges": [], "diagnostics": []}
    profile = ProfileWorkspaceManager().load_profile_yaml(resolved_profile_id)
    if not profile:
        return {
            "nodes": [],
            "edges": [],
            "diagnostics": [{"level": "warning", "code": "profile_not_found", "message": f"Profile '{resolved_profile_id}' was not found."}],
        }
    profile = apply_profile_graph_selection(profile)
    metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    selected = metadata.get("selected") if isinstance(metadata.get("selected"), dict) else {}
    profile_node = {
        "id": f"profile:{resolved_profile_id}",
        "kind": "profile",
        "label": str(profile.get("name") or resolved_profile_id),
        "ref": resolved_profile_id,
        "metadata": {"profile_id": resolved_profile_id},
    }
    nodes = [profile_node]
    edges: List[Dict[str, Any]] = []
    for category, prefix, edge_kind in (
        ("tools", "tool", "selects"),
        ("webhooks", "webhook", "receives_from"),
        ("api_routes", "api", "allows_api"),
        ("prompts", "prompt", "uses_prompt"),
        ("frontend", "frontend", "uses_frontend"),
    ):
        for item in selected.get(category) if isinstance(selected.get(category), list) else []:
            item_id = str(item or "").strip()
            if not item_id:
                continue
            node_id = f"{prefix}:{item_id}"
            nodes.append({"id": node_id, "kind": prefix, "label": item_id, "ref": item_id, "metadata": {"selected": True}})
            edges.append(_edge(profile_node["id"], node_id, edge_kind, {"selected": True}))
    diagnostics: List[Dict[str, Any]] = []
    policy = profile.get("policy") if isinstance(profile.get("policy"), dict) else {}
    if policy.get("api_route_allowlist") and not policy.get("enforce_api_route_allowlist"):
        diagnostics.append(
            {
                "level": "info",
                "code": "api_route_allowlist_not_enforced",
                "message": "API route allowlist is configured on the active profile, but enforcement is disabled.",
            }
        )
    return {"nodes": nodes, "edges": edges, "diagnostics": diagnostics}


def _edge(from_id: str, to_id: str, kind: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "id": f"{from_id}->{to_id}:{kind}",
        "from_id": from_id,
        "to_id": to_id,
        "kind": kind,
        "active": True,
        "metadata": dict(metadata or {}),
    }
