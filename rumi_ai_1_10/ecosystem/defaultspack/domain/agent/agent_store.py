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
        if isinstance(payload.get("schedule"), dict) and not merged.get("schedule_policy"):
            merged["schedule_policy"] = payload["schedule"]
        if isinstance(payload.get("lifecycle"), dict):
            merged["runtime_policy"] = {**dict(merged.get("runtime_policy") or {}), **payload["lifecycle"]}
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
        current.update({key: value for key, value in updates.items() if key not in {"agent_id", "id"}})
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
