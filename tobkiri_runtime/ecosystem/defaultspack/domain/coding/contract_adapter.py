"""Finite defaultspack compatibility adapter for Wave 8 coding contracts."""

from __future__ import annotations

from typing import Any, Mapping

from core_runtime.di_container import get_container
from core_runtime.global_contract_dispatch import invoke_global_contract
from core_runtime.resolved_profile_scope import active_resolved_profile


FILE_INSPECT = "rumi.service.file.inspect.v1"
FILE_MUTATE = "rumi.service.file.mutate.v1"
FILE_PATCH = "rumi.service.file.patch.v1"
SHELL_INSPECT = "rumi.service.shell.inspect.v1"
SHELL_EXECUTE = "rumi.service.shell.execute.v1"
TERMINAL_RESOURCE = "rumi.resource.terminal.session.v1"
TERMINAL_CONTROL = "rumi.action.terminal.session.v1"
GIT_READ = "rumi.service.git.read.v1"
GIT_WRITE = "rumi.service.git.write.v1"
GIT_PUBLISH = "rumi.service.git.publish.v1"
HOST_AUTHORITY = "rumi.service.host.authorize.v1"


def invoke_coding_contract(
    contract_id: str,
    operation: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Invoke exactly one selected coding provider for the active profile."""

    registry = get_container().get_or_none("interface_registry")
    plan = active_resolved_profile()
    if registry is None or plan is None:
        raise RuntimeError("global coding provider is unavailable")
    request = {
        "profile_id": plan.profile_id,
        **dict(payload),
        "_contract_consumer_pack_id": "defaultspack",
    }
    result = invoke_global_contract(registry, contract_id, operation, request)
    if not isinstance(result, dict):
        raise RuntimeError("coding provider returned an invalid result")
    return result


def workspace_id(input_data: Mapping[str, Any]) -> str:
    """Require the canonical workspace identifier; never infer a root path."""

    value = str(input_data.get("workspace_id") or "").strip()
    if not value:
        raise ValueError("workspace_id is required")
    return value
