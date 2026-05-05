from __future__ import annotations

from blocks._common import error, ok
from domain.agent.agent_runtime import AgentRuntime
from domain.agent.agent_store import AgentStore


def agent_error(exc: Exception):
    return error(str(exc), code="AGENT_FACTORY_FAILED")


__all__ = ["AgentRuntime", "AgentStore", "agent_error", "ok"]
