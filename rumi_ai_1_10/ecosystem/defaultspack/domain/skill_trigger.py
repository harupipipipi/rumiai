from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from domain.extensions.runtime import get_extension_registry

_MENTION_RE = re.compile(r"(?:^|\s)@([^\s@]+)")
_MAX_PROMPT_FILE_CHARS = 80_000


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
        skills = self._list_skills()
        forced = _resolve_skill_ids(
            [
                *_as_list(context.get("skills") or context.get("skill_ids") or context.get("selected_skills")),
                *_mentioned_skill_ids(user_text, skills),
            ],
            skills,
        )
        matched: list[dict[str, Any]] = []
        for skill in skills:
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
            return get_extension_registry().skills().list(enabled_only=True)
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
    config = skill.get("config") if isinstance(skill.get("config"), dict) else {}
    for key in ("instructions", "instruction", "feedback"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for container in (config, metadata, skill):
        prompt_file = _instruction_file_text(container, skill)
        if prompt_file:
            return prompt_file
    description = str(skill.get("description") or "").strip()
    return description


def _instruction_file_text(container: dict[str, Any], skill: dict[str, Any]) -> str:
    for key in ("instructions_path", "instruction_path", "system_prompt_path", "prompt_path", "prompt_file"):
        value = container.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            metadata = skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}
            source_path = str(skill.get("source_path") or metadata.get("manifest_path") or "").strip()
            if source_path:
                path = Path(source_path).expanduser().parent / path
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8", errors="ignore")[:_MAX_PROMPT_FILE_CHARS].strip()
        except OSError:
            continue
    return ""


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


def _mentioned_skill_ids(text: str, skills: list[dict[str, Any]]) -> list[str]:
    aliases = _skill_alias_lookup(skills)
    ids: list[str] = []
    seen = set()
    for match in _MENTION_RE.finditer(str(text or "")):
        token = _normalize_mention_token(match.group(1))
        skill_id = aliases.get(token)
        if not skill_id or skill_id in seen:
            continue
        seen.add(skill_id)
        ids.append(skill_id)
    return ids


def _resolve_skill_ids(values: list[str], skills: list[dict[str, Any]]) -> set[str]:
    aliases = _skill_alias_lookup(skills)
    result: set[str] = set()
    for value in values:
        normalized = _normalize_mention_token(value)
        skill_id = aliases.get(normalized)
        if skill_id:
            result.add(skill_id)
    return result


def _skill_alias_lookup(skills: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for skill in skills:
        skill_id = str(skill.get("id") or "").strip()
        if not skill_id:
            continue
        values = [
            skill_id,
            skill_id.rsplit("/", 1)[-1],
            str(skill.get("display_name") or ""),
            str(skill.get("name") or ""),
        ]
        metadata = skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}
        aliases = skill.get("aliases") or metadata.get("aliases")
        if isinstance(aliases, list):
            values.extend(str(item) for item in aliases)
        for value in values:
            for alias in _alias_variants(value):
                lookup.setdefault(alias, skill_id)
    return lookup


def _alias_variants(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    variants = {text, text.replace(" ", "_"), text.replace("_", "-"), text.replace("/", "_"), text.replace("/", "-")}
    return [_normalize_mention_token(item) for item in variants if _normalize_mention_token(item)]


def _normalize_mention_token(value: str) -> str:
    return str(value or "").strip().strip(".,!?;:)]}）】」'\"").casefold()
