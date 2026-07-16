"""
blocks/agent/setup.py - Agent component setup phase

Registers agent-related HTTP routes (single-agent, multi-agent, instruction,
interrupt, and scheduler) into the kernel's InterfaceRegistry under the key
``io.http.route``.
"""

import sys
import os


def run(context):
    """Called by the kernel during the *setup* phase."""
    pack_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if pack_root not in sys.path:
        sys.path.insert(0, pack_root)

    interface_registry = context["interface_registry"]
    source_component = context.get("_source_component", "defaultspack:agent:agent")
    try:
        from capability_bindings import register_defaultspack_binding_handlers
        register_defaultspack_binding_handlers(interface_registry)
    except Exception as exc:
        print(
            "[defaultspack.agent] setup: failed to register capability bindings - "
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
        # ---- Single-agent routes ----
        ("POST", "/api/agent/execute", _lazy("blocks.agent.execute"), {}),
        ("POST", "/api/agent/{id}/approve", _lazy("blocks.agent.approve"), {"id": "execution_id"}),
        ("POST", "/api/agent/{id}/reject", _lazy("blocks.agent.reject"), {"id": "execution_id"}),
        ("POST", "/api/agent/{id}/cancel", _lazy("blocks.agent.cancel"), {"id": "execution_id"}),
        (
            "POST",
            "/api/agent/{id}/completion-gate/resume",
            _lazy("blocks.agent.resume_completion_gate"),
            {"id": "execution_id"},
        ),
        ("GET", "/api/agent/{id}/status", _lazy("blocks.agent.status"), {"id": "execution_id"}),
        # ---- Multi-agent routes ----
        ("POST", "/api/agent/multi/execute", _lazy("blocks.agent.multi_execute"), {}),
        ("GET", "/api/agent/multi/{id}/status", _lazy("blocks.agent.multi_status"), {"id": "session_id"}),
        ("POST", "/api/agent/multi/{id}/message", _lazy("blocks.agent.multi_message"), {"id": "session_id"}),
        ("POST", "/api/agent/subagent", _lazy("blocks.agent.run_subagent"), {}),
        # ---- Instruction route ----
        ("POST", "/api/agent/{id}/instruct", _lazy("blocks.agent.add_instruction"), {"id": "execution_id"}),
        # ---- Interrupt & control routes (T13) ----
        ("POST", "/api/agent/{id}/interrupt", _lazy("blocks.agent.interrupt.add"), {"id": "execution_id"}),
        ("DELETE", "/api/agent/{id}/interrupt/{inst_id}", _lazy("blocks.agent.interrupt.cancel"), {"id": "execution_id", "inst_id": "instruction_id"}),
        ("POST", "/api/agent/{id}/pause", _lazy("blocks.agent.interrupt.pause"), {"id": "execution_id"}),
        ("POST", "/api/agent/{id}/resume", _lazy("blocks.agent.interrupt.resume"), {"id": "execution_id"}),
        ("POST", "/api/agent/{id}/redirect", _lazy("blocks.agent.interrupt.redirect"), {"id": "execution_id"}),
        ("POST", "/api/agent/{id}/stepback", _lazy("blocks.agent.interrupt.stepback"), {"id": "execution_id"}),
        ("GET", "/api/agent/{id}/queue", _lazy("blocks.agent.interrupt.queue"), {"id": "execution_id"}),
        ("PUT", "/api/agent/{id}/queue", _lazy("blocks.agent.interrupt.queue"), {"id": "execution_id"}),
        ("GET", "/api/agent/{id}/progress", _lazy("blocks.agent.interrupt.progress"), {"id": "execution_id"}),
        # ---- Scheduler routes (T12) ----
        ("POST", "/api/agent/schedules", _lazy("blocks.agent.scheduler.create"), {}),
        ("GET", "/api/agent/schedules", _lazy("blocks.agent.scheduler.list"), {}),
        ("GET", "/api/agent/schedules/{id}", _lazy("blocks.agent.scheduler.get"), {"id": "schedule_id"}),
        ("PUT", "/api/agent/schedules/{id}", _lazy("blocks.agent.scheduler.update"), {"id": "schedule_id"}),
        ("DELETE", "/api/agent/schedules/{id}", _lazy("blocks.agent.scheduler.delete"), {"id": "schedule_id"}),
        ("POST", "/api/agent/schedules/{id}/trigger", _lazy("blocks.agent.scheduler.trigger"), {"id": "schedule_id"}),
        ("POST", "/api/agent/schedules/{id}/pause", _lazy("blocks.agent.scheduler.pause"), {"id": "schedule_id"}),
        ("POST", "/api/agent/schedules/{id}/resume", _lazy("blocks.agent.scheduler.resume"), {"id": "schedule_id"}),
        ("GET", "/api/agent/schedules/{id}/history", _lazy("blocks.agent.scheduler.history"), {"id": "schedule_id"}),
        # ---- Organization routes ----
        ("GET", "/api/agent/org", _lazy("blocks.agent.org.list"), {}),
        ("POST", "/api/agent/org", _lazy("blocks.agent.org.create"), {}),
        ("GET", "/api/agent/org/roles", _lazy("blocks.agent.org.list_roles"), {}),
        ("POST", "/api/agent/org/roles", _lazy("blocks.agent.org.define_role"), {}),
        ("GET", "/api/agent/org/{id}", _lazy("blocks.agent.org.get"), {"id": "id"}),
        ("DELETE", "/api/agent/org/{id}", _lazy("blocks.agent.org.delete"), {"id": "id"}),
        ("POST", "/api/agent/org/{id}/members", _lazy("blocks.agent.org.add_member"), {"id": "id"}),
        ("DELETE", "/api/agent/org/{id}/members/{agent_id}", _lazy("blocks.agent.org.remove_member"), {"id": "id", "agent_id": "agent_id"}),
        ("POST", "/api/agent/org/{id}/ask", _lazy("blocks.agent.org.ask"), {"id": "id"}),
        ("POST", "/api/agent/org/{id}/instruct", _lazy("blocks.agent.org.instruct"), {"id": "id"}),
        ("POST", "/api/agent/org/{id}/report", _lazy("blocks.agent.org.report"), {"id": "id"}),
        ("POST", "/api/agent/org/{id}/transfer", _lazy("blocks.agent.org.transfer_context"), {"id": "id"}),
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
