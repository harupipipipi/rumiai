from __future__ import annotations

import copy
from typing import Any

from .ai_input_models import normalize_ai_input_config
from .profile_graph_models import normalize_profile_graph_selected


def apply_profile_graph_selection(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(profile)
    metadata = _dict_or_empty(normalized.get("metadata"))
    selected_input = _dict_or_empty(metadata.get("selected"))
    selected = normalize_profile_graph_selected(selected_input)
    graph = _dict_or_empty(metadata.get("profile_graph"))

    metadata["selected"] = selected
    if graph:
        metadata["profile_graph"] = {
            "nodes": _list_or_empty(graph.get("nodes")),
            "edges": _list_or_empty(graph.get("edges")),
        }
    if "ai_input" in metadata:
        metadata["ai_input"] = normalize_ai_input_config(metadata.get("ai_input"))
    normalized["metadata"] = metadata

    policy = _dict_or_empty(normalized.get("policy"))

    tools = _selected_list(selected, "tools")
    if tools:
        policy["tool_allowlist"] = tools

    api_routes = _selected_list(selected, "api_routes")
    if api_routes:
        policy["api_route_allowlist"] = api_routes

    prompts = _selected_list(selected, "prompts")
    if prompts:
        first_prompt = str(prompts[0] or "").strip()
        if first_prompt:
            normalized["system_prompt_id"] = first_prompt

    if _selection_key_present(selected_input, "nodes") or selected.get("nodes"):
        node_overrides = _dict_or_empty(normalized.get("node_overrides"))
        selected_surface_node = _selected_frontend_surface_node_ref(metadata, selected)
        if selected_surface_node:
            node_overrides["frontend.surface"] = selected_surface_node
        normalized["node_overrides"] = node_overrides

    normalized["policy"] = policy
    normalized["metadata"] = metadata
    return normalized


def _dict_or_empty(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_or_empty(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _selected_list(
    selected: dict[str, list[str] | dict[str, Any]], key: str
) -> list[str]:
    value = selected.get(key)
    return list(value) if isinstance(value, list) else []


def _selection_key_present(selected: dict[str, Any], key: str) -> bool:
    return key in selected


def _selected_frontend_surface_node_ref(
    metadata: dict[str, Any],
    selected: dict[str, list[str] | dict[str, Any]],
) -> str | None:
    graph = _dict_or_empty(metadata.get("profile_graph"))
    graph_nodes = _list_or_empty(graph.get("nodes"))
    node_by_ref: dict[str, dict[str, Any]] = {}
    for entry in graph_nodes:
        if not isinstance(entry, dict):
            continue
        ref = str(entry.get("ref") or "").strip()
        if not ref:
            continue
        node_by_ref[ref] = entry

    for ref in _selected_list(selected, "nodes"):
        node_entry = node_by_ref.get(str(ref))
        if _is_launchable_frontend_surface(node_entry):
            return str(ref)
    return None


def _is_launchable_frontend_surface(node_entry: dict[str, Any] | None) -> bool:
    if not isinstance(node_entry, dict):
        return False
    candidate = _dict_or_empty(node_entry.get("metadata"))
    nested = _dict_or_empty(candidate.get("metadata"))
    launch = _dict_or_empty(candidate.get("launch"))
    if not launch:
        launch = _dict_or_empty(nested.get("launch"))
    component_type = str(
        candidate.get("component_type") or nested.get("component_type") or ""
    ).strip().lower()
    if component_type != "frontend":
        return False
    if str(launch.get("kind") or "").strip().lower() != "desktop_app":
        return False
    if not str(launch.get("pack_id") or "").strip():
        return False
    ports = _list_or_empty(candidate.get("ports"))
    if not ports:
        ports = _list_or_empty(nested.get("ports"))
    if ports:
        for port in ports:
            if not isinstance(port, dict):
                continue
            standards = _list_or_empty(port.get("standards"))
            contracts = _list_or_empty(port.get("contracts"))
            direction = str(port.get("direction") or "").strip().lower()
            surface_contracts = {str(item).strip() for item in standards + contracts}
            if direction == "output" and "rumi.surface" in surface_contracts:
                return True
        return False
    return bool(launch.get("surface") or launch.get("default"))
