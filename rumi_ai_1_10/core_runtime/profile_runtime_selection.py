from __future__ import annotations

import copy
from typing import Any, Dict

from .profile_graph_models import normalize_profile_graph_selected


def apply_profile_graph_selection(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(profile if isinstance(profile, dict) else {})
    metadata = dict(normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {})
    selected_input = metadata.get("selected") if isinstance(metadata.get("selected"), dict) else {}
    selected = normalize_profile_graph_selected(metadata.get("selected"))
    graph = metadata.get("profile_graph") if isinstance(metadata.get("profile_graph"), dict) else {}

    metadata["selected"] = selected
    if graph:
        metadata["profile_graph"] = {
            "nodes": list(graph.get("nodes")) if isinstance(graph.get("nodes"), list) else [],
            "edges": list(graph.get("edges")) if isinstance(graph.get("edges"), list) else [],
        }
    normalized["metadata"] = metadata

    policy = dict(normalized.get("policy") if isinstance(normalized.get("policy"), dict) else {})

    if selected.get("tools"):
        policy["tool_allowlist"] = list(selected.get("tools") or [])

    if selected.get("api_routes"):
        policy["api_route_allowlist"] = list(selected.get("api_routes") or [])

    prompts = selected.get("prompts") if isinstance(selected.get("prompts"), list) else []
    if prompts:
        first_prompt = str(prompts[0] or "").strip()
        if first_prompt:
            normalized["system_prompt_id"] = first_prompt

    if _selection_key_present(selected_input, "nodes") or selected.get("nodes"):
        node_overrides = dict(normalized.get("node_overrides") if isinstance(normalized.get("node_overrides"), dict) else {})
        selected_surface_node = _selected_frontend_surface_node_ref(metadata, selected)
        if selected_surface_node:
            node_overrides["frontend.surface"] = selected_surface_node
        normalized["node_overrides"] = node_overrides

    normalized["policy"] = policy
    normalized["metadata"] = metadata
    return normalized


def _selection_key_present(selected: Dict[str, Any], key: str) -> bool:
    return isinstance(selected, dict) and key in selected


def _selected_frontend_surface_node_ref(metadata: Dict[str, Any], selected: Dict[str, Any]) -> str | None:
    graph = metadata.get("profile_graph") if isinstance(metadata.get("profile_graph"), dict) else {}
    graph_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    node_by_ref: Dict[str, Dict[str, Any]] = {}
    for entry in graph_nodes:
        if not isinstance(entry, dict):
            continue
        ref = str(entry.get("ref") or "").strip()
        if not ref:
            continue
        node_by_ref[ref] = entry

    for ref in selected.get("nodes") if isinstance(selected.get("nodes"), list) else []:
        node_entry = node_by_ref.get(str(ref))
        if _is_launchable_frontend_surface(node_entry):
            return str(ref)
    return None


def _is_launchable_frontend_surface(node_entry: Dict[str, Any] | None) -> bool:
    if not isinstance(node_entry, dict):
        return False
    candidate = node_entry.get("metadata") if isinstance(node_entry.get("metadata"), dict) else {}
    nested = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    launch = candidate.get("launch") if isinstance(candidate.get("launch"), dict) else {}
    if not launch and isinstance(nested.get("launch"), dict):
        launch = nested.get("launch")
    component_type = str(candidate.get("component_type") or nested.get("component_type") or "").strip().lower()
    if component_type != "frontend":
        return False
    if str(launch.get("kind") or "").strip().lower() != "desktop_app":
        return False
    if not str(launch.get("pack_id") or "").strip():
        return False
    ports = candidate.get("ports") if isinstance(candidate.get("ports"), list) else []
    if not ports and isinstance(nested.get("ports"), list):
        ports = nested.get("ports")
    if ports:
        for port in ports:
            if not isinstance(port, dict):
                continue
            standards = port.get("standards") if isinstance(port.get("standards"), list) else []
            contracts = port.get("contracts") if isinstance(port.get("contracts"), list) else []
            direction = str(port.get("direction") or "").strip().lower()
            if direction == "output" and "rumi.surface" in {str(item).strip() for item in [*standards, *contracts]}:
                return True
        return False
    return bool(launch.get("surface") or launch.get("default"))
