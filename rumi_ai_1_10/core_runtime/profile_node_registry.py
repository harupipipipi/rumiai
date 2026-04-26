"""Profile-aware view over the global Capability Graph node registry."""

from __future__ import annotations

from typing import Any, Dict, List

from .node_models import CORE_START_NODE_ID, NodeDefinition
from .node_state import compute_missing_node_state, compute_node_state
from .profile_models import ProfileDefinition


class ProfileNodeRegistry:
    """Filter global nodes and compute node state for a single profile."""

    def __init__(
        self,
        *,
        node_registry: Any,
        profile: ProfileDefinition,
    ) -> None:
        self.node_registry = node_registry
        self.profile = profile

    def nodes(self) -> Dict[str, NodeDefinition]:
        raw_nodes = getattr(self.node_registry, "nodes", None)
        if not raw_nodes:
            raw_nodes = self.node_registry.load_all_nodes()
        return dict(raw_nodes)

    def list_enabled_nodes(self) -> List[NodeDefinition]:
        nodes = self.nodes()
        return [
            nodes[node_id]
            for node_id in sorted(nodes)
            if self.profile.is_node_enabled(node_id)
        ]

    def node_state(self, node_id: str | None = None) -> List[Dict[str, Any]] | Dict[str, Any]:
        nodes = self.nodes()
        if node_id:
            node = nodes.get(node_id)
            if node is None:
                return compute_missing_node_state(node_id, self.profile)
            return compute_node_state(node, self.profile)

        state_by_id = {
            current_node_id: compute_node_state(node, self.profile)
            for current_node_id, node in nodes.items()
        }
        for configured_node_id in set(self.profile.enabled_nodes + self.profile.disabled_nodes):
            if configured_node_id != CORE_START_NODE_ID and configured_node_id not in state_by_id:
                state_by_id[configured_node_id] = compute_missing_node_state(
                    configured_node_id,
                    self.profile,
                )
        return [state_by_id[current_node_id] for current_node_id in sorted(state_by_id)]
