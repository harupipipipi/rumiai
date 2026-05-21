from __future__ import annotations

from core_runtime.graph_models import GraphNodeInstance
from core_runtime.node_models import load_node_document
from core_runtime.surface_launch_target import (
    extract_surface_launch_target,
    surface_launch_target_from_instance,
)


def _node(payload: dict):
    return load_node_document({"version": "rumi.node.v1", "nodes": [payload]})[0]


def test_surface_launch_target_rejects_cross_pack_launch_metadata():
    node = _node(
        {
            "node_id": "frontendpack.web_surface",
            "ports": [{"id": "surface", "direction": "output", "standards": ["rumi.surface"]}],
            "metadata": {
                "pack_id": "frontendpack",
                "launch": {
                    "kind": "desktop_app",
                    "pack_id": "otherpack",
                },
            },
        }
    )
    diagnostics = []

    target = surface_launch_target_from_instance(
        runtime_profile={},
        instance=GraphNodeInstance(id="frontendpack_web_surface", ref="frontendpack.web_surface"),
        nodes={node.node_id: node},
        diagnostics=diagnostics,
    )

    assert target is None
    assert diagnostics[0]["code"] == "launch_pack_mismatch"


def test_extract_surface_launch_target_falls_back_to_base_pack():
    target = extract_surface_launch_target(
        {"version": "rumi.runtime_profile.v1"},
        fallback_pack_id="defaultspack",
        surfaces={"preferred": "browser", "enabled": ["browser"]},
    )

    assert target is not None
    assert target["pack_id"] == "defaultspack"
    assert target["source"] == "startup_profile_fallback"
