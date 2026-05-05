from __future__ import annotations

import os
from typing import Any

from blocks._common import gen_id, timestamp
from .agent_lifecycle import AgentLifecycle
from .agent_store import AgentStore
from .blocker import BlockerStore, blocker_contract
from .policy_resolver import PolicyResolver
from .run_history import RunHistory
from .run_state import RunStateStore
from domain.ai_client.key_resolver import KeyResolver


class AgentRuntime:
    """Small long-running runtime facade for stored AgentDefinitions."""

    def __init__(self, *, pack_root=None, store: AgentStore | None = None, state: RunStateStore | None = None, history: RunHistory | None = None) -> None:
        self.store = store or AgentStore(root=pack_root)
        self.state = state or RunStateStore(root=pack_root)
        self.history = history or RunHistory(root=pack_root)
        self.lifecycle = AgentLifecycle()
        self.blockers = BlockerStore(root=pack_root)
        self.policy_resolver = PolicyResolver()
        self.key_resolver = KeyResolver(pack_root=pack_root)

    def start(self, agent_id: str, *, conversation_id: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        definition = self._definition(agent_id)
        return self.state.update(
            agent_id,
            status="running",
            started_at=timestamp(),
            blocked_reason=None,
            profile_id=definition.get("profile_id"),
            conversation_id=conversation_id or self.state.get(agent_id).get("conversation_id"),
            metadata=metadata if isinstance(metadata, dict) else {},
        )

    def pause(self, agent_id: str, reason: str = "") -> dict[str, Any]:
        self._definition(agent_id)
        return self.state.update(agent_id, status="paused", paused_at=timestamp(), pause_reason=reason)

    def resume(self, agent_id: str) -> dict[str, Any]:
        self._definition(agent_id)
        return self.state.update(agent_id, status="running", resumed_at=timestamp(), blocked_reason=None)

    def stop(self, agent_id: str, reason: str = "") -> dict[str, Any]:
        self._definition(agent_id)
        return self.state.update(agent_id, status="completed", stopped_at=timestamp(), stop_reason=reason)

    def status(self, agent_id: str = "") -> dict[str, Any]:
        if not agent_id:
            return {"agents": self.store.list_agents(), "states": self.state.list()}
        definition = self._definition(agent_id)
        return {**self.state.get(agent_id), "definition": definition}

    def runs(self, agent_id: str = "", *, limit: int = 50, offset: int = 0):
        if agent_id:
            self._definition(agent_id)
        return self.history.list_runs(agent_id, limit=limit, offset=offset)

    def logs(self, agent_id: str = "", *, limit: int = 100, offset: int = 0):
        if agent_id:
            self._definition(agent_id)
        return self.history.list_logs(agent_id, limit=limit, offset=offset)

    def tick(
        self,
        agent_id: str,
        *,
        message: str = "",
        conversation_id: str | None = None,
        model: str | None = None,
        trigger: str = "manual",
        schedule_id: str = "",
        schedule_execution_id: str = "",
        tools: list[Any] | None = None,
        tool_policy: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        definition = self._definition(agent_id)
        state = self.state.get(agent_id)
        metadata = metadata if isinstance(metadata, dict) else {}
        active_blockers = self.blockers.list(agent_id, active_only=True)
        if active_blockers:
            run_id = "run_" + gen_id()
            started_at = timestamp()
            blocked_reason = active_blockers[0].get("message") or "active blocker"
            new_state = self.state.update(agent_id, status="blocked", blocked_reason=blocked_reason, blockers=active_blockers)
            run = {
                "run_id": run_id,
                "agent_id": agent_id,
                "status": "blocked",
                "started_at": started_at,
                "completed_at": timestamp(),
                "blocked_reason": blocked_reason,
                "result": blocker_contract(
                    agent_id,
                    str(blocked_reason or "blocked"),
                    profile_id=str(definition.get("profile_id") or ""),
                    browser_profile_id=str(definition.get("tool_policy", {}).get("browser_profile_id") or ""),
                ),
                "blockers": active_blockers,
            }
            self.history.append(agent_id, run)
            return {"status": "blocked", "state": new_state, "run": run}
        guard = self.lifecycle.before_tick(definition, state)
        run_id = "run_" + gen_id()
        started_at = timestamp()
        if guard.get("allowed") is False:
            status = guard.get("status") or "blocked"
            blocked_reason = guard.get("blocked_reason")
            new_state = self.state.update(agent_id, status=status, blocked_reason=blocked_reason)
            run = {
                "run_id": run_id,
                "agent_id": agent_id,
                "status": status,
                "started_at": started_at,
                "completed_at": timestamp(),
                "blocked_reason": blocked_reason,
                "result": blocker_contract(
                    agent_id,
                    str(blocked_reason or "blocked"),
                    profile_id=str(definition.get("profile_id") or ""),
                    browser_profile_id=str(definition.get("tool_policy", {}).get("browser_profile_id") or ""),
                )
                if status == "blocked"
                else None,
            }
            self.history.append(agent_id, run)
            return {"status": status, "state": new_state, "run": run}

        self.state.update(agent_id, status="running", current_run_id=run_id, last_tick_at=started_at)
        result: dict[str, Any]
        model_policy = definition.get("model_policy") if isinstance(definition.get("model_policy"), dict) else {}
        default_model = model or model_policy.get("default_model") or "stub/default"
        api_key_policy = definition.get("api_key_policy") if isinstance(definition.get("api_key_policy"), dict) else {}
        key_resolution = self.key_resolver.resolve_api_key(
            provider_id=str(api_key_policy.get("provider_id") or ""),
            profile_id=str(definition.get("profile_id") or ""),
            agent_id=agent_id,
            preferred_key_id=str(api_key_policy.get("preferred_key_id") or ""),
            model=str(default_model),
        )
        if key_resolution.get("configured") and key_resolution.get("env_key") and key_resolution.get("value"):
            os.environ[str(key_resolution["env_key"])] = str(key_resolution["value"])
        base_tool_policy = definition.get("tool_policy") if isinstance(definition.get("tool_policy"), dict) else {}
        resolved_tool_policy = self.policy_resolver.resolve(base_tool_policy, tool_policy if isinstance(tool_policy, dict) else {})
        selected_tools = tools if isinstance(tools, list) else resolved_tool_policy.get("tool_allowlist")
        try:
            if conversation_id:
                from blocks.chat.send import run as chat_send_run

                result = chat_send_run(
                    {
                        "conversation_id": conversation_id,
                        "message": {
                            "role": "user",
                            "content": message or "Run one agent tick.",
                            "metadata": {
                                **metadata,
                                "source": metadata.get("source") or "agent_runtime",
                                "runtime_source": "agent_runtime",
                                "agent_id": agent_id,
                                "profile_id": definition.get("profile_id"),
                                "run_id": run_id,
                                "trigger": trigger,
                                "schedule_id": schedule_id,
                                "schedule_execution_id": schedule_execution_id,
                            },
                        },
                        "params": {"tool_policy": resolved_tool_policy},
                        "tools": selected_tools,
                    },
                    {
                        **(context if isinstance(context, dict) else {}),
                        "profile_policy": resolved_tool_policy,
                    },
                )
                run_status = "completed" if result.get("status") == "ok" else "failed"
            else:
                result = {"status": "ok", "data": {"message": message or "tick recorded", "model": default_model}}
                run_status = "completed"
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}
            run_status = "failed"

        completed_at = timestamp()
        previous_failures = int(state.get("failure_count") or 0)
        new_state = self.state.update(
            agent_id,
            status="running" if run_status == "completed" and definition.get("runtime_policy", {}).get("non_stop") else run_status,
            current_run_id=None,
            last_tick_at=started_at,
            next_tick_at=None,
            run_count=int(state.get("run_count") or 0) + (1 if run_status == "completed" else 0),
            tick_count=int(state.get("tick_count") or 0) + 1,
            failure_count=previous_failures + (1 if run_status == "failed" else 0),
            no_change_count=int(state.get("no_change_count") or 0) + (1 if run_status == "completed" else 0),
            blocked_reason=None,
            conversation_id=conversation_id,
            browser_profile_id=definition.get("tool_policy", {}).get("browser_profile_id"),
        )
        run = {
            "run_id": run_id,
            "agent_id": agent_id,
            "status": run_status,
            "started_at": started_at,
            "completed_at": completed_at,
            "message": message,
            "result": result,
            "trigger": trigger,
            "schedule_id": schedule_id,
            "schedule_execution_id": schedule_execution_id,
            "policy": resolved_tool_policy,
            "key_resolution": self.key_resolver.redacted_resolution(key_resolution),
        }
        self.history.append(agent_id, run)
        return {"status": run_status, "state": new_state, "run": run}

    def _definition(self, agent_id: str) -> dict[str, Any]:
        definition = self.store.get_agent(agent_id)
        if not definition:
            raise ValueError("agent not found")
        return definition
