"""
docker_exec handler - Execute a command inside a running Docker container
via DockerCapabilityHandler.

This handler is the entry point for docker.exec capability requests.
It delegates to DockerCapabilityHandler (provided by W22-D) which
validates permissions and runs the command.
"""
from __future__ import annotations

try:
    from core_runtime.docker_capability import DockerCapabilityHandler
except ImportError:
    DockerCapabilityHandler = None


def execute(context: dict, args: dict) -> dict:
    """Execute a command inside a running Docker container.

    Parameters
    ----------
    context : dict
        Execution context containing principal_id and grant_config.
    args : dict
        Arguments matching input_schema (container_name, command, etc.).

    Returns
    -------
    dict
        Result with exit_code, stdout, stderr,
        or an error response if DockerCapabilityHandler is unavailable.
    """
    if DockerCapabilityHandler is None:
        return {
            "error": "DockerCapabilityHandler is not available. W22-D module (core_runtime.docker_capability) has not been installed.",
            "error_type": "dependency_not_available",
        }

    principal_id = context.get("principal_id", "unknown")
    grant_config = context.get("grant_config", {})

    handler = DockerCapabilityHandler()
    return handler.handle_exec(
        principal_id=principal_id,
        args=args,
        grant_config=grant_config,
    )
