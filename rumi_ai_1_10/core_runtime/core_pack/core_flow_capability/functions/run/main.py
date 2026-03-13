"""
flow_run_handler - stub handler for flow.run capability

This handler is never executed via subprocess.
flow.run is intercepted by capability_executor.py and executed
in-process via kernel_core.execute_flow_sync().

This file exists solely because handler_registry scans for
handler.json + handler.py pairs in builtin_capability_handlers/.
"""


def execute(context: dict, args: dict) -> dict:
    """Stub: should never be called via subprocess."""
    return {
        "error": "flow.run must be executed in-process by capability_executor",
        "error_type": "invalid_dispatch",
    }
