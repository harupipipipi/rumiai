from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelPackMember:
    model: str
    label: str = ""
    conditions: dict[str, Any] = field(default_factory=dict)
    fallback_on: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "label": self.label,
            "conditions": dict(self.conditions),
            "fallback_on": list(self.fallback_on),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModelPackMember":
        return cls(
            model=str(value.get("model") or value.get("profile_id") or "").strip(),
            label=str(value.get("label") or value.get("display_name") or "").strip(),
            conditions=dict(value.get("conditions") if isinstance(value.get("conditions"), dict) else value.get("when") if isinstance(value.get("when"), dict) else {}),
            fallback_on=[str(item).strip() for item in (value.get("fallback_on") if isinstance(value.get("fallback_on"), list) else []) if str(item or "").strip()],
            metadata=dict(value.get("metadata") if isinstance(value.get("metadata"), dict) else {}),
        )


@dataclass
class ModelPack:
    id: str
    display_name: str = ""
    members: list[ModelPackMember] = field(default_factory=list)
    rules: dict[str, Any] = field(default_factory=dict)
    fallback: list[str] = field(default_factory=list)
    mode: str = "fallback_chain"
    budget: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "model_pack"
    aliases: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "members": [member.as_dict() for member in self.members],
            "rules": dict(self.rules),
            "fallback": list(self.fallback),
            "mode": self.mode,
            "budget": dict(self.budget),
            "safety": dict(self.safety),
            "metadata": dict(self.metadata),
            "source": self.source,
            "aliases": list(self.aliases),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModelPack":
        raw_members = value.get("members") if isinstance(value.get("members"), list) else []
        members = [
            ModelPackMember.from_dict(member)
            for member in raw_members
            if isinstance(member, dict) and str(member.get("model") or member.get("profile_id") or "").strip()
        ]
        return cls(
            id=str(value.get("id") or "").strip(),
            display_name=str(value.get("display_name") or value.get("label") or value.get("id") or "").strip(),
            members=members,
            rules=dict(value.get("rules") if isinstance(value.get("rules"), dict) else value.get("conditions") if isinstance(value.get("conditions"), dict) else {}),
            fallback=[str(item).strip() for item in (value.get("fallback") if isinstance(value.get("fallback"), list) else []) if str(item or "").strip()],
            mode=str(value.get("mode") or value.get("type") or "fallback_chain").strip() or "fallback_chain",
            budget=dict(value.get("budget") if isinstance(value.get("budget"), dict) else {}),
            safety=dict(value.get("safety") if isinstance(value.get("safety"), dict) else {}),
            metadata=dict(value.get("metadata") if isinstance(value.get("metadata"), dict) else {}),
            source=str(value.get("source") or "model_pack").strip() or "model_pack",
            aliases=[str(item).strip() for item in (value.get("aliases") if isinstance(value.get("aliases"), list) else []) if str(item or "").strip()],
        )
