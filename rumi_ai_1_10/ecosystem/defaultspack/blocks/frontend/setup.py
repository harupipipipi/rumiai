"""Compatibility shim for legacy frontend setup location.

The lifecycle executor now loads setup.py from components/frontend/, so this
file keeps capability binding registration available if legacy loading is used.
"""


def run(context=None):
    context = context or {}
    interface_registry = context.get("interface_registry")
    if interface_registry is not None:
        from capability_bindings import register_defaultspack_binding_handlers
        register_defaultspack_binding_handlers(interface_registry)
    return {
        "status": "ok",
        "message": "frontend setup moved to components/frontend/setup.py",
    }
