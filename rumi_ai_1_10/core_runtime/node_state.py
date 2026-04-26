"""Profile-scoped node state helpers for Capability Graph."""

from __future__ import annotations

from typing import Any, Dict, List

from .node_models import CORE_START_NODE_ID, NodeDefinition
from .profile_models import ProfileDefinition


def compute_node_state(
    node: NodeDefinition,
    profile: ProfileDefinition,
    *,
    installed: bool = True,
) -> Dict[str, Any]:
    node_id = node.node_id
    settings = profile.node_settings.get(node_id, {})
    missing = _missing_settings(node, settings)
    enabled = profile.is_node_enabled(node_id)
    configured = not missing
    approved = node_id == CORE_START_NODE_ID or bool(node.metadata.get("pack_id"))
    status = _status(installed, approved, enabled, configured)
    return {
        "node_id": node_id,
        "installed": installed,
        "approved": approved,
        "enabled": enabled,
        "configured": configured,
        "status": status,
        "missing": missing,
        "credential_ref": settings.get("credential_ref"),
        "profile_id": profile.profile_id,
    }


def compute_missing_node_state(node_id: str, profile: ProfileDefinition) -> Dict[str, Any]:
    enabled = profile.is_node_enabled(node_id)
    return {
        "node_id": node_id,
        "installed": False,
        "approved": False,
        "enabled": enabled,
        "configured": False,
        "status": "missing_node",
        "missing": ["node_definition"],
        "credential_ref": None,
        "profile_id": profile.profile_id,
    }


def _missing_settings(node: NodeDefinition, settings: Dict[str, Any]) -> List[str]:
    required = node.requirements.get("required_settings") or node.requirements.get("settings") or []
    if not isinstance(required, list):
        return []
    missing: List[str] = []
    for key in required:
        if isinstance(key, str) and key and settings.get(key) in (None, ""):
            missing.append(key)
    return missing


def _status(installed: bool, approved: bool, enabled: bool, configured: bool) -> str:
    if not installed:
        return "missing_node"
    if not approved:
        return "unapproved"
    if not enabled:
        return "disabled"
    if not configured:
        return "missing_config"
    return "ready"
