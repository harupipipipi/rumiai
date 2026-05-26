from __future__ import annotations

import copy
from typing import Any, Dict

from .profile_graph_models import normalize_profile_graph_selected


def apply_profile_graph_selection(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(profile if isinstance(profile, dict) else {})
    metadata = dict(normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {})
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
        if first_prompt and not str(normalized.get("system_prompt_id") or "").strip():
            normalized["system_prompt_id"] = first_prompt

    normalized["policy"] = policy
    normalized["metadata"] = metadata
    return normalized
