"""
blocks/tool/setup.py - Tool component setup phase

Registers tool and consent HTTP routes into the kernel's InterfaceRegistry
under the key ``io.http.route``.
"""

import sys
import os


def run(context):
    """Called by the kernel during the *setup* phase."""
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:tool:tool")
    try:
        from capability_bindings import register_defaultspack_binding_handlers
        register_defaultspack_binding_handlers(interface_registry)
    except Exception as exc:
        print(
            "[defaultspack.tool] setup: failed to register capability bindings - "
            + str(exc),
            file=sys.stderr,
        )

    def _lazy(module_path, func_name="run"):
        """Return a lazy handler that imports the module on first call."""
        def handler(request_data, context):
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, func_name)
            return fn(request_data, context)
        return handler

    routes = [
        # ---- Tool read/invoke routes ----
        ("GET", "/api/tools", _lazy("blocks.tool.list"), {}),
        ("POST", "/api/tools/invoke", _lazy("blocks.tool.invoke"), {}),
        ("POST", "/api/tools/browser-computer", _lazy("blocks.tool.browser_computer"), {}),
        # ---- Capability catalog routes ----
        ("GET", "/api/capabilities", _lazy("blocks.capability.list"), {}),
        ("GET", "/api/capabilities/{id}", _lazy("blocks.capability.manifest"), {"id": "capability_id"}),
        # ---- Browser v2 routes ----
        ("GET", "/api/browser/profiles", _lazy("blocks.browser.profiles"), {}),
        ("POST", "/api/browser/profiles", _lazy("blocks.browser.profiles"), {}),
        ("GET", "/api/browser/profiles/{id}", _lazy("blocks.browser.profile"), {"id": "profile_id"}),
        ("PUT", "/api/browser/profiles/{id}", _lazy("blocks.browser.profile"), {"id": "profile_id"}),
        ("DELETE", "/api/browser/profiles/{id}", _lazy("blocks.browser.profile"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/start", _lazy("blocks.browser.start"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/stop", _lazy("blocks.browser.stop"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/restart", _lazy("blocks.browser.restart"), {"id": "profile_id"}),
        ("GET", "/api/browser/profiles/{id}/health", _lazy("blocks.browser.health"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/active", _lazy("blocks.browser.active"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/actions", _lazy("blocks.browser.actions"), {"id": "profile_id"}),
        ("GET", "/api/browser/profiles/{id}/tabs", _lazy("blocks.browser.tabs"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/tabs", _lazy("blocks.browser.tabs"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/tabs/{tab_id}/focus", _lazy("blocks.browser.tab_focus"), {"id": "profile_id", "tab_id": "tab_id"}),
        ("DELETE", "/api/browser/profiles/{id}/tabs/{tab_id}", _lazy("blocks.browser.tab_close"), {"id": "profile_id", "tab_id": "tab_id"}),
        ("POST", "/api/browser/profiles/{id}/snapshot", _lazy("blocks.browser.snapshot"), {"id": "profile_id"}),
        ("POST", "/api/browser/profiles/{id}/screenshot", _lazy("blocks.browser.screenshot"), {"id": "profile_id"}),
        # ---- Approval Center routes ----
        ("GET", "/api/approvals", _lazy("blocks.approval.list"), {}),
        ("GET", "/api/approvals/policy", _lazy("blocks.approval.policy"), {}),
        ("PUT", "/api/approvals/policy", _lazy("blocks.approval.policy"), {}),
        ("GET", "/api/approvals/{id}", _lazy("blocks.approval.get"), {"id": "approval_id"}),
        ("POST", "/api/approvals/{id}/approve", _lazy("blocks.approval.approve"), {"id": "approval_id"}),
        ("POST", "/api/approvals/{id}/deny", _lazy("blocks.approval.deny"), {"id": "approval_id"}),
        ("POST", "/api/approvals/{id}/decision", _lazy("blocks.approval.decision"), {"id": "approval_id"}),
        ("POST", "/api/approvals/{id}/approve_once", _lazy("blocks.approval.approve_once"), {"id": "approval_id"}),
        ("POST", "/api/approvals/{id}/approve_for_session", _lazy("blocks.approval.approve_for_session"), {"id": "approval_id"}),
        # ---- Dynamic tool routes ----
        ("POST", "/api/tools/create", _lazy("blocks.tool.create"), {}),
        ("PUT", "/api/tools/{name}", _lazy("blocks.tool.update"), {"name": "name"}),
        ("DELETE", "/api/tools/{name}", _lazy("blocks.tool.delete"), {"name": "name"}),
        ("GET", "/api/tools/{name}/export", _lazy("blocks.tool.export"), {"name": "name"}),
        # ---- Tool policy routes ----
        ("GET", "/api/tools/permissions", _lazy("blocks.tool.permissions", "run_get"), {}),
        ("PUT", "/api/tools/permissions", _lazy("blocks.tool.permissions", "run_put"), {}),
        ("POST", "/api/tools/permissions/check", _lazy("blocks.tool.permissions", "run_check"), {}),
        ("GET", "/api/tools/{name}/permissions", _lazy("blocks.tool.permissions", "run_get"), {"name": "name"}),
        ("PUT", "/api/tools/{name}/permissions", _lazy("blocks.tool.permissions", "run_put"), {"name": "name"}),
        # ---- Consent routes ----
        ("POST", "/api/consent/check", _lazy("blocks.tool.consent_check"), {}),
        ("POST", "/api/consent/{id}/confirm", _lazy("blocks.tool.consent_confirm"), {"id": "consent_id"}),
        # ---- MCP routes ----
        ("POST", "/api/tools/mcp/connect", _lazy("blocks.tool.mcp_connect"), {}),
        ("GET", "/api/tools/mcp", _lazy("blocks.tool.mcp_list"), {}),
        # ---- Container routes (T14) ----
        ("POST", "/api/container", _lazy("blocks.tool.container.create"), {}),
        ("POST", "/api/container/{id}/start", _lazy("blocks.tool.container.start"), {"id": "id"}),
        ("POST", "/api/container/{id}/stop", _lazy("blocks.tool.container.stop"), {"id": "id"}),
        ("DELETE", "/api/container/{id}", _lazy("blocks.tool.container.delete"), {"id": "id"}),
        ("POST", "/api/container/{id}/exec", _lazy("blocks.tool.container.exec"), {"id": "id"}),
        ("GET", "/api/container/{id}/screenshot", _lazy("blocks.tool.container.screenshot"), {"id": "id"}),
        ("POST", "/api/container/{id}/input", _lazy("blocks.tool.container.input"), {"id": "id"}),
        # ---- Container task routes (T14) ----
        ("POST", "/api/container/task", _lazy("blocks.tool.container.task_create"), {}),
        ("GET", "/api/container/task/{id}", _lazy("blocks.tool.container.task_status"), {"id": "id"}),
        ("GET", "/api/container/task/{id}/result", _lazy("blocks.tool.container.task_result"), {"id": "id"}),
        ("POST", "/api/container/task/{id}/abort", _lazy("blocks.tool.container.task_abort"), {"id": "id"}),
        # ---- Container settings routes (T14) ----
        ("PUT", "/api/container/settings", _lazy("blocks.tool.container.settings"), {}),
        ("GET", "/api/container/settings", _lazy("blocks.tool.container.settings"), {}),
    ]

    for method, pattern, handler, path_inject in routes:
        interface_registry.register(
            "io.http.route",
            {
                "method": method,
                "pattern": pattern,
                "handler": handler,
                "path_inject": path_inject,
            },
            meta={"_source_component": source_component},
        )
