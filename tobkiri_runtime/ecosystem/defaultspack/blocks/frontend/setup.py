"""Compatibility shim for legacy frontend setup location.

The lifecycle executor now loads setup.py from components/frontend/, so this
file keeps capability binding registration available if legacy loading is used.
"""


def run(context=None):
    context = context or {}
    interface_registry = context.get("interface_registry")
    registered = []
    if interface_registry is not None:
        from capability_bindings import register_defaultspack_binding_handlers

        register_defaultspack_binding_handlers(interface_registry)
        from blocks.ui.setup import run as register_ui_routes

        ui_result = register_ui_routes(
            {
                **context,
                "_source_component": context.get("_source_component") or "defaultspack:frontend:ui",
            }
        )
        registered.extend(ui_result.get("registered", []))
    return {
        "status": "ok",
        "message": "frontend setup moved to components/frontend/setup.py",
        "registered": registered,
    }
