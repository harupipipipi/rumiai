from __future__ import annotations

from copy import deepcopy
from typing import Any

from blocks._common import gen_id, timestamp


DEFAULT_MODEL_POLICY = {
    "default_model": "stub/default",
    "allowed_models": ["stub/default"],
    "reasoning_effort": "medium",
    "self_selection": True,
    "max_switches_per_day": 3,
}

DEFAULT_RUNTIME_POLICY = {
    "non_stop": False,
    "can_run_24_7": True,
    "activation_mode": "manual",
    "max_tool_calls_per_tick": 12,
    "max_concurrent_children": 1,
    "max_spawn_depth": 1,
    "normal_status_silent": True,
    "incident_delivery_required": True,
}

DEFAULT_STOP_CONDITIONS = {
    "max_runtime_minutes": None,
    "max_cost_usd": 1.0,
    "max_tokens": 2000000,
    "max_failures": 3,
    "max_no_change_ticks": 20,
    "stop_on_approval_required": False,
    "stop_on_login_required": False,
}

DEFAULT_WEBHOOK_POLICY = {
    "enabled": False,
    "url_mode": "cloudflare_pages",
    "cloudflare_pages_url": "https://rumi-agent-webhook.pages.dev/api/agent-webhook",
    "custom_webhook_url": "",
    "secret": "",
    "accept_unsigned_local": True,
}


class AgentDefinition:
    """Create Agent schema used by Agent Factory and Operations Company."""

    def __init__(
        self,
        *,
        agent_id: str | None = None,
        display_name: str = "",
        profile_id: str = "defaultspack.local_agent",
        role_key: str = "custom",
        enabled: bool = True,
        system_prompt: str = "",
        model_policy: dict[str, Any] | None = None,
        api_key_policy: dict[str, Any] | None = None,
        tool_policy: dict[str, Any] | None = None,
        runtime_policy: dict[str, Any] | None = None,
        schedule_policy: dict[str, Any] | None = None,
        webhook_policy: dict[str, Any] | None = None,
        stop_conditions: dict[str, Any] | None = None,
        memory_policy: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        self.agent_id = str(agent_id or "agent_" + gen_id()).strip()
        self.display_name = display_name or self.agent_id
        self.profile_id = profile_id
        self.role_key = role_key
        self.enabled = bool(enabled)
        self.system_prompt = system_prompt
        self.model_policy = self._merge(DEFAULT_MODEL_POLICY, model_policy)
        self.api_key_policy = dict(api_key_policy or {})
        self.tool_policy = dict(tool_policy or {})
        self.runtime_policy = self._merge(DEFAULT_RUNTIME_POLICY, runtime_policy)
        self.schedule_policy = dict(schedule_policy or {"type": "manual"})
        self.webhook_policy = self._merge(DEFAULT_WEBHOOK_POLICY, webhook_policy)
        self.stop_conditions = self._merge(DEFAULT_STOP_CONDITIONS, stop_conditions)
        self.memory_policy = dict(memory_policy or {"compact_context": True})
        self.metadata = dict(metadata or {})
        self.created_at = created_at or timestamp()
        self.updated_at = updated_at or self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "profile_id": self.profile_id,
            "role_key": self.role_key,
            "enabled": self.enabled,
            "system_prompt": self.system_prompt,
            "model_policy": deepcopy(self.model_policy),
            "api_key_policy": deepcopy(self.api_key_policy),
            "tool_policy": deepcopy(self.tool_policy),
            "runtime_policy": deepcopy(self.runtime_policy),
            "schedule_policy": deepcopy(self.schedule_policy),
            "webhook_policy": deepcopy(self.webhook_policy),
            "stop_conditions": deepcopy(self.stop_conditions),
            "memory_policy": deepcopy(self.memory_policy),
            "metadata": deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AgentDefinition":
        return cls(
            agent_id=value.get("agent_id") or value.get("id"),
            display_name=value.get("display_name") or value.get("name") or "",
            profile_id=value.get("profile_id") or "defaultspack.local_agent",
            role_key=value.get("role_key") or value.get("role") or "custom",
            enabled=value.get("enabled", True) is not False,
            system_prompt=value.get("system_prompt") or "",
            model_policy=value.get("model_policy") if isinstance(value.get("model_policy"), dict) else None,
            api_key_policy=value.get("api_key_policy") if isinstance(value.get("api_key_policy"), dict) else None,
            tool_policy=value.get("tool_policy") if isinstance(value.get("tool_policy"), dict) else None,
            runtime_policy=value.get("runtime_policy") if isinstance(value.get("runtime_policy"), dict) else None,
            schedule_policy=value.get("schedule_policy") if isinstance(value.get("schedule_policy"), dict) else None,
            webhook_policy=value.get("webhook_policy") if isinstance(value.get("webhook_policy"), dict) else None,
            stop_conditions=value.get("stop_conditions") if isinstance(value.get("stop_conditions"), dict) else None,
            memory_policy=value.get("memory_policy") if isinstance(value.get("memory_policy"), dict) else None,
            metadata=value.get("metadata") if isinstance(value.get("metadata"), dict) else None,
            created_at=value.get("created_at"),
            updated_at=value.get("updated_at"),
        )

    @classmethod
    def from_role(cls, role: dict[str, Any], *, profile_id: str) -> "AgentDefinition":
        allowed_tools = list(role.get("allowed_tools") or [])
        return cls(
            agent_id=role.get("agent_id"),
            display_name=role.get("display_name") or role.get("agent_name") or role.get("role_key"),
            profile_id=profile_id,
            role_key=role.get("role_key") or role.get("agent_id") or "custom",
            enabled=True,
            system_prompt=role.get("system_prompt") or "",
            model_policy={
                "default_model": role.get("model") or "stub/default",
                "allowed_models": [role.get("model") or "stub/default"],
                "reasoning_effort": "medium",
                "self_selection": True,
            },
            tool_policy={
                "allowlist": allowed_tools,
                "denylist": [],
                "browser_profile_id": "operations-company",
                "computer_use_mode": "inspect_first",
                "write_actions_require_approval": True,
                "terminal_actions_require_approval": True,
                "external_send_requires_approval": True,
                "settings_mutation_requires_approval": True,
            },
            runtime_policy={
                "non_stop": role.get("agent_id") == "operations_monitor",
                "normal_status_silent": role.get("agent_id") == "operations_monitor",
                "max_tool_calls_per_tick": 12,
            },
            schedule_policy={"type": "interval", "every_minutes": 15, "timezone": "Asia/Tokyo"}
            if role.get("agent_id") == "operations_monitor"
            else {"type": "manual"},
            memory_policy={
                "compact_context": True,
                "compact_after_messages": 32,
                "protect_last_messages": 12,
                "store_decisions": True,
                "store_incidents": True,
                "store_handoffs": True,
            },
            metadata={"source_role": role},
        )

    @staticmethod
    def _merge(defaults: dict[str, Any], value: dict[str, Any] | None) -> dict[str, Any]:
        merged = deepcopy(defaults)
        if isinstance(value, dict):
            merged.update(value)
        return merged
