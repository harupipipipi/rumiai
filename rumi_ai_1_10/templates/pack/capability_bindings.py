from __future__ import annotations


def register_example_pack_binding_handlers(interface_registry):
    interface_registry.register("example_pack:search.compile_node", compile_search_node)
    return {"registered": ["example_pack:search.compile_node"]}


def compile_search_node(runtime_profile, instance):
    defaultspack = runtime_profile.setdefault("defaultspack", {})
    tools = defaultspack.setdefault("tools", {})
    tools[str(instance.id)] = {
        "node_instance_id": str(instance.id),
        "node_id": str(instance.ref),
        "tools": ["example_search"],
    }
