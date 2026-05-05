import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import gen_id, timestamp


class AgentDefinition:
    """マルチエージェントにおける個々のエージェントの定義。

    Attributes
    ----------
    agent_id : str
        一意識別子。
    name : str
        エージェント名（例: "coder", "reviewer"）。
    role : str
        役割の説明文（例: "You are a senior Python developer."）。
    model : str
        使用する AI モデル文字列（例: "openai/gpt-4o"）。
    system_prompt : str
        システムプロンプト。
    tools : list[dict]
        使用可能なツール定義リスト。
    """

    def __init__(
        self,
        name,
        role,
        model,
        system_prompt=None,
        tools=None,
        agent_id=None,
        display_name=None,
        description="",
        profile_id="",
        provider_id="",
        preferred_key_id="",
        tool_policy=None,
        lifecycle=None,
        budget=None,
        rate_limit=None,
        metadata=None,
        status="ready",
        created_at=None,
        updated_at=None,
    ):
        self.agent_id = agent_id if agent_id else ("agentdef_" + gen_id())
        self.name = name
        self.display_name = display_name if display_name else name
        self.description = description if description else ""
        self.role = role
        self.model = model if model else "default"
        self.profile_id = profile_id if profile_id else ""
        self.provider_id = provider_id if provider_id else self._provider_from_model(self.model)
        self.preferred_key_id = preferred_key_id if preferred_key_id else ""
        self.system_prompt = system_prompt if system_prompt else ""
        self.tools = tools if tools else []
        self.tool_policy = tool_policy if isinstance(tool_policy, dict) else {}
        self.lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
        self.budget = budget if isinstance(budget, dict) else {}
        self.rate_limit = rate_limit if isinstance(rate_limit, dict) else {}
        self.metadata = metadata if isinstance(metadata, dict) else {}
        self.status = status if status else "ready"
        self.created_at = created_at if created_at else timestamp()
        self.updated_at = updated_at if updated_at else self.created_at

    @staticmethod
    def _provider_from_model(model):
        model = str(model or "").strip()
        if "/" in model:
            return model.split("/", 1)[0]
        return ""

    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "role": self.role,
            "model": self.model,
            "profile_id": self.profile_id,
            "provider_id": self.provider_id,
            "preferred_key_id": self.preferred_key_id,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "tool_policy": self.tool_policy,
            "lifecycle": self.lifecycle,
            "budget": self.budget,
            "rate_limit": self.rate_limit,
            "metadata": self.metadata,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data):
        """dict からインスタンスを生成する。"""
        return cls(
            name=data.get("name", "unnamed"),
            role=data.get("role", ""),
            model=data.get("model", "default"),
            system_prompt=data.get("system_prompt", ""),
            tools=data.get("tools", []),
            agent_id=data.get("agent_id"),
            display_name=data.get("display_name"),
            description=data.get("description", ""),
            profile_id=data.get("profile_id", ""),
            provider_id=data.get("provider_id", ""),
            preferred_key_id=data.get("preferred_key_id", ""),
            tool_policy=data.get("tool_policy", {}),
            lifecycle=data.get("lifecycle", {}),
            budget=data.get("budget", {}),
            rate_limit=data.get("rate_limit", {}),
            metadata=data.get("metadata", {}),
            status=data.get("status", "ready"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
