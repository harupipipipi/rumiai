from __future__ import annotations

from typing import Any

from domain.extensions.runtime import get_extension_registry


class RuntimeSkillTriggerService:
    """Matches enabled extension skills and renders their runtime instructions."""

    def __init__(self, skills: list[dict[str, Any]] | None = None) -> None:
        self._skills = skills

    def evaluate(
        self,
        *,
        user_text: str,
        tool_names: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context if isinstance(context, dict) else {}
        if context.get("disable_runtime_skill_triggers") is True:
            return {"matched": [], "instructions": ""}
        text = str(user_text or "").casefold()
        tool_set = {str(name or "").strip() for name in (tool_names or []) if str(name or "").strip()}
        forced = _as_list(context.get("skills") or context.get("skill_ids"))
        matched: list[dict[str, Any]] = []
        for skill in self._list_skills():
            skill_id = str(skill.get("id") or "").strip()
            if not skill_id:
                continue
            if forced and skill_id not in forced:
                continue
            triggers = _as_list(skill.get("triggers") or skill.get("keywords"))
            applies_to = _as_list(skill.get("applies_to_tools") or skill.get("tool_ids"))
            forced_hit = skill_id in forced
            trigger_hit = forced_hit or not triggers or any(str(trigger).casefold() in text for trigger in triggers)
            tool_hit = forced_hit or not applies_to or bool(tool_set.intersection(applies_to))
            if not (trigger_hit and tool_hit):
                continue
            instruction = _instruction_text(skill)
            if not instruction:
                continue
            matched.append(
                {
                    "id": skill_id,
                    "display_name": str(skill.get("display_name") or skill_id),
                    "triggers": triggers,
                    "applies_to_tools": applies_to,
                    "instruction": instruction,
                }
            )
        return {"matched": matched, "instructions": render_skill_instructions(matched)}

    def _list_skills(self) -> list[dict[str, Any]]:
        if self._skills is not None:
            return [skill for skill in self._skills if isinstance(skill, dict)]
        try:
            return get_extension_registry(force_reload=True).skills().list(enabled_only=True)
        except Exception:
            return []


def render_skill_instructions(matched: list[dict[str, Any]]) -> str:
    if not matched:
        return ""
    lines = [
        "Runtime skill instructions matched this turn. These are active system-level instructions for this turn; follow them unless they conflict with higher-priority safety or user instructions:"
    ]
    for item in matched:
        lines.append("- {}: {}".format(item.get("id"), str(item.get("instruction") or "").strip()))
    return "\n".join(lines).strip()


def _instruction_text(skill: dict[str, Any]) -> str:
    for key in ("instructions", "instruction", "system_prompt", "prompt"):
        value = skill.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}
    for key in ("instructions", "instruction", "feedback"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    description = str(skill.get("description") or "").strip()
    return description


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
