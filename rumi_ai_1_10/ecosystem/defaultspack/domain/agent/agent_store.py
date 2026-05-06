from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from blocks._common import timestamp
from .agent_definition import AgentDefinition
from .agent_templates import get_template, list_templates


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


class AgentStore:
    """JSON-backed Create Agent store."""

    def __init__(self, root: Path | None = None, pack_root: Path | None = None) -> None:
        pack_root = Path(pack_root or root or _pack_root())
        override = (
            os.environ.get("RUMI_DEFAULTSPACK_AGENT_STORE_PATH", "").strip()
            or os.environ.get("RUMI_DEFAULTSPACK_AGENTS_PATH", "").strip()
        )
        self.path = Path(override) if override else pack_root / "user_data" / "shared" / "agents" / "agents.json"

    def list_agents(self) -> list[dict[str, Any]]:
        agents = self._read().get("agents", {})
        return [dict(item) for _, item in sorted(agents.items()) if isinstance(item, dict)]

    def list(self, *_, **__) -> list[dict[str, Any]]:
        return self.list_agents()

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        item = self._read().get("agents", {}).get(str(agent_id or ""))
        return dict(item) if isinstance(item, dict) else None

    def get(self, agent_id: str) -> dict[str, Any] | None:
        return self.get_agent(agent_id)

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        template_id = str(payload.get("template_id") or payload.get("template") or "")
        template = get_template(template_id) if template_id else {}
        merged = {**template, **payload}
        if payload.get("name") and not merged.get("display_name"):
            merged["display_name"] = payload["name"]
        if payload.get("role") and not merged.get("role_key"):
            merged["role_key"] = payload["role"]
        if payload.get("model"):
            model_policy = dict(merged.get("model_policy") or {})
            model_policy.setdefault("default_model", payload["model"])
            if not model_policy.get("allowed_models"):
                model_policy["allowed_models"] = [payload["model"]]
            merged["model_policy"] = model_policy
        if payload.get("api_key_id"):
            api_key_policy = dict(merged.get("api_key_policy") or {})
            api_key_policy.setdefault("preferred_key_id", payload["api_key_id"])
            merged["api_key_policy"] = api_key_policy
        tool_policy = dict(merged.get("tool_policy") or {})
        if isinstance(payload.get("tools"), list):
            tool_policy["allowlist"] = payload["tools"]
        if payload.get("browser_profile_id"):
            tool_policy["browser_profile_id"] = payload["browser_profile_id"]
        if payload.get("browser_enabled") is False:
            tool_policy.setdefault("denylist", []).append("browser_use")
        if payload.get("computer_enabled") is False:
            tool_policy.setdefault("denylist", []).append("computer_use")
        if tool_policy:
            merged["tool_policy"] = tool_policy
        merged.update(_frontend_agent_updates(payload, base=merged))
        definition = AgentDefinition.from_dict(merged).to_dict()
        return self.upsert(definition)

    def create(self, definition: AgentDefinition | dict[str, Any]) -> dict[str, Any]:
        payload = definition.to_dict() if hasattr(definition, "to_dict") else dict(definition or {})
        if self.get_agent(str(payload.get("agent_id") or "")):
            raise ValueError("agent already exists")
        return self.upsert(payload)

    def update_agent(self, agent_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_agent(agent_id)
        if not current:
            raise ValueError("agent not found")
        normalized = _frontend_agent_updates(updates, base=current)
        if not normalized:
            normalized = {key: value for key, value in updates.items() if key not in {"agent_id", "id"}}
        current.update(normalized)
        current["updated_at"] = timestamp()
        return self.upsert(current)

    def update(self, agent_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self.update_agent(agent_id, updates)
        except ValueError:
            return None

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        data = self._read()
        removed = data.setdefault("agents", {}).pop(str(agent_id or ""), None)
        data["updated_at"] = timestamp()
        self._write(data)
        return {"agent_id": agent_id, "deleted": bool(removed)}

    def delete(self, agent_id: str) -> bool:
        return bool(self.delete_agent(agent_id).get("deleted"))

    def upsert(self, definition: AgentDefinition | dict[str, Any]) -> dict[str, Any]:
        if isinstance(definition, AgentDefinition):
            payload = definition.to_dict()
        elif hasattr(definition, "to_dict"):
            payload = AgentDefinition.from_dict(definition.to_dict()).to_dict()
        else:
            payload = AgentDefinition.from_dict(definition).to_dict()
        data = self._read()
        data.setdefault("agents", {})[payload["agent_id"]] = payload
        data["updated_at"] = timestamp()
        self._write(data)
        return payload

    def templates(self) -> list[dict[str, Any]]:
        return list_templates()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {"schema_version": 1, "agents": {}}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema_version": 1, **value}, ensure_ascii=False, indent=2), encoding="utf-8")


def _frontend_agent_updates(payload: dict[str, Any], *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map webapp AgentRecord/CreateAgentRequest fields into AgentDefinition fields."""
    base = base if isinstance(base, dict) else {}
    updates: dict[str, Any] = {}
    if payload.get("name") is not None:
        updates["display_name"] = str(payload.get("name") or "").strip()
    if payload.get("role") is not None:
        updates["role_key"] = str(payload.get("role") or "").strip() or "custom"
        if not payload.get("system_prompt"):
            updates["system_prompt"] = str(payload.get("role") or "")
    if payload.get("profile_id") is not None:
        updates["profile_id"] = str(payload.get("profile_id") or "defaultspack.local_agent")
    if payload.get("model"):
        model = str(payload.get("model"))
        model_policy = dict(base.get("model_policy") or {})
        model_policy["default_model"] = model
        if not model_policy.get("allowed_models") or model not in set(model_policy.get("allowed_models") or []):
            model_policy["allowed_models"] = [model]
        updates["model_policy"] = model_policy
    if payload.get("api_key_id") is not None or payload.get("provider_id") is not None:
        api_key_policy = dict(base.get("api_key_policy") or {})
        if payload.get("api_key_id") is not None:
            api_key_policy["preferred_key_id"] = str(payload.get("api_key_id") or "")
        if payload.get("provider_id") is not None:
            api_key_policy["provider_id"] = str(payload.get("provider_id") or "")
        updates["api_key_policy"] = api_key_policy

    tool_policy = _tool_policy_from_frontend(payload, base=base)
    if tool_policy is not None:
        updates["tool_policy"] = tool_policy

    lifecycle = payload.get("lifecycle") if isinstance(payload.get("lifecycle"), dict) else {}
    schedule = payload.get("schedule") if isinstance(payload.get("schedule"), dict) else {}
    webhook = payload.get("webhook") if isinstance(payload.get("webhook"), dict) else payload.get("webhook_policy")
    webhook = webhook if isinstance(webhook, dict) else {}
    if lifecycle or schedule or webhook:
        runtime_policy = dict(base.get("runtime_policy") or {})
        schedule_policy = dict(base.get("schedule_policy") or {"type": "manual"})
        webhook_policy = dict(base.get("webhook_policy") or {})
        run_mode = str(lifecycle.get("run_mode") or schedule.get("mode") or schedule_policy.get("run_mode") or schedule_policy.get("type") or "manual")
        if webhook:
            webhook_policy.update(_webhook_policy_from_frontend(webhook))
            run_mode = "webhook" if webhook_policy.get("enabled") else run_mode
        if schedule:
            schedule_policy.update(_schedule_policy_from_frontend(schedule, run_mode=run_mode, webhook_policy=webhook_policy))
        if lifecycle:
            runtime_policy.update({key: value for key, value in lifecycle.items() if key not in {"max_cost_usd", "stop_on_failure"}})
        runtime_policy["activation_mode"] = run_mode
        runtime_policy["non_stop"] = run_mode == "non_stop"
        runtime_policy["can_run_24_7"] = run_mode in {"scheduled", "non_stop", "webhook"} or bool(runtime_policy.get("can_run_24_7"))
        updates["runtime_policy"] = runtime_policy
        updates["schedule_policy"] = schedule_policy
        updates["webhook_policy"] = webhook_policy
        stop_conditions = dict(base.get("stop_conditions") or {})
        if "max_cost_usd" in lifecycle:
            stop_conditions["max_cost_usd"] = lifecycle.get("max_cost_usd")
        if lifecycle.get("stop_on_failure") is False:
            stop_conditions["max_failures"] = None
        updates["stop_conditions"] = stop_conditions
    return {key: value for key, value in updates.items() if key not in {"agent_id", "id"}}


def _tool_policy_from_frontend(payload: dict[str, Any], *, base: dict[str, Any]) -> dict[str, Any] | None:
    touched = any(key in payload for key in ("tools", "tool_policy", "browser_profile_id", "browser_enabled", "computer_enabled"))
    if not touched:
        return None
    tool_policy = dict(base.get("tool_policy") or {})
    incoming = payload.get("tool_policy") if isinstance(payload.get("tool_policy"), dict) else {}
    if isinstance(payload.get("tools"), list):
        tool_policy["allowlist"] = [str(item) for item in payload.get("tools") or []]
    if isinstance(incoming.get("allowed_tools"), list):
        tool_policy["allowlist"] = [str(item) for item in incoming.get("allowed_tools") or []]
    if isinstance(incoming.get("denied_tools"), list):
        tool_policy["denylist"] = [str(item) for item in incoming.get("denied_tools") or []]
    if payload.get("browser_profile_id") is not None:
        tool_policy["browser_profile_id"] = str(payload.get("browser_profile_id") or "")
    denylist = list(tool_policy.get("denylist") or [])
    if payload.get("browser_enabled") is False and "browser_use" not in denylist:
        denylist.append("browser_use")
    if payload.get("computer_enabled") is False and "computer_use" not in denylist:
        denylist.append("computer_use")
    if payload.get("browser_enabled") is True:
        denylist = [item for item in denylist if item != "browser_use"]
    if payload.get("computer_enabled") is True:
        denylist = [item for item in denylist if item != "computer_use"]
    tool_policy["denylist"] = denylist
    if isinstance(incoming.get("require_approval_for"), list):
        tool_policy["require_approval_for"] = [str(item) for item in incoming.get("require_approval_for") or []]
    return tool_policy


def _schedule_policy_from_frontend(schedule: dict[str, Any], *, run_mode: str, webhook_policy: dict[str, Any]) -> dict[str, Any]:
    if schedule.get("enabled") is False or run_mode == "manual":
        return {"type": "manual", "enabled": False, "run_mode": "manual"}
    if run_mode == "webhook":
        return {
            "type": "webhook",
            "enabled": bool(webhook_policy.get("enabled", True)),
            "run_mode": "webhook",
            "url_mode": webhook_policy.get("url_mode", "cloudflare_pages"),
        }
    interval = max(1, int(float(schedule.get("interval_minutes") or schedule.get("every_minutes") or 30)))
    return {
        "type": "interval",
        "enabled": True,
        "run_mode": run_mode,
        "every_minutes": interval,
        "timezone": str(schedule.get("timezone") or "Asia/Tokyo"),
        "start_now": bool(schedule.get("start_now")),
    }


def _webhook_policy_from_frontend(webhook: dict[str, Any]) -> dict[str, Any]:
    policy = dict(webhook)
    if "enabled" in webhook:
        policy["enabled"] = bool(webhook.get("enabled"))
    policy.setdefault("url_mode", "cloudflare_pages")
    policy.setdefault("cloudflare_pages_url", "https://rumi-agent-webhook.pages.dev/api/agent-webhook")
    policy.setdefault("custom_webhook_url", "")
    policy.setdefault("accept_unsigned_local", True)
    return policy
