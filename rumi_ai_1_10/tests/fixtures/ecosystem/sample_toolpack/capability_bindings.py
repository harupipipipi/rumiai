"""Binding handlers for the sample external tool pack."""

from __future__ import annotations

from typing import Any, Dict


def register_sample_toolpack_binding_handlers(interface_registry: Any) -> Dict[str, Any]:
    handlers = {
        "sample_toolpack:search.compile_node": compile_search_node,
        "sample_toolpack:write_guard.compile_node": compile_write_guard_node,
    }
    for handler_id, handler in handlers.items():
        if interface_registry.get(handler_id) is None:
            interface_registry.register(
                handler_id,
                handler,
                meta={"source": "sample_toolpack.capability_bindings", "pack_id": "sample_toolpack"},
            )
    return {"status": "ok", "registered": sorted(handlers)}


def compile_search_node(runtime_profile: Dict[str, Any], instance: Any) -> None:
    _tool_bundle(runtime_profile, instance, ["sample_search"], write=False)


def compile_write_guard_node(runtime_profile: Dict[str, Any], instance: Any) -> None:
    _tool_bundle(runtime_profile, instance, ["sample_write"], write=True)


def _tool_bundle(runtime_profile: Dict[str, Any], instance: Any, tool_names: list[str], *, write: bool) -> None:
    defaultspack = runtime_profile.setdefault("defaultspack", {})
    tools = defaultspack.setdefault("tools", {})
    definitions = []
    for name in tool_names:
        definitions.append(
            {
                "name": name,
                "description": f"{name} fixture tool",
                "schema": {"type": "object", "properties": {}, "required": []},
                "metadata": {
                    "category": "fixture",
                    "action_type": "write" if write else "read",
                    "write_action": write,
                },
            }
        )
    tools[str(instance.id)] = {
        "node_instance_id": str(instance.id),
        "node_id": str(instance.ref),
        "tools": list(tool_names),
        "definitions": definitions,
    }
