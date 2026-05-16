"""
flow_run_handler - registry entry for flow.run capability

This handler is never executed via subprocess.
flow.run is intercepted by capability_executor.py and executed
in-process via kernel_core.execute_flow_sync().

This file exists solely for the FunctionRegistry entry.
"""


def execute(context: dict, args: dict) -> dict:
    """Direct execution is not supported."""
    return {
        "success": False,
        "error": "flow.run must be executed in-process by capability_executor",
        "error_type": "invalid_dispatch",
    }
