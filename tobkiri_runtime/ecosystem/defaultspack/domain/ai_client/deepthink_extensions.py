"""Profile-scoped DeepThink extension and integration discovery helpers."""

from __future__ import annotations

import re
from typing import Any

from domain.extensions.runtime import get_extension_registry
from domain.skill_trigger import RuntimeSkillTriggerService
from domain.tool.schema_adapter import tool_name_from_definition

_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_MAX_EXTENSION_PHASES = 12
_MAX_PERSPECTIVES = 8
_MAX_CATALOG_ITEMS = 128
_PRESENTATION_CHOICES = {
    "icon": {"activity", "brain-circuit"},
    "tone": {"neutral", "violet-sky"},
    "entry": {"none", "rise"},
    "surface": {"aurora", "none"},
    "indicator": {"none", "orbit", "pulse"},
    "active_phase": {"none", "pulse", "signal"},
}


def deepthink_extension_contract() -> dict[str, Any]:
    """Merge DeepThink contributions from the active profile's selected packs."""

    registry = get_extension_registry()
    contributions = registry.deepthink().list(enabled_only=True)
    discovery_tools: list[str] = []
    phases: list[dict[str, str]] = []
    perspectives: list[dict[str, str]] = []
    phase_ids: set[str] = set()
    perspective_ids: set[str] = set()
    source_pack_ids: list[str] = []
    presentation: dict[str, Any] = {}

    for contribution in contributions:
        config = (
            contribution.get("config")
            if isinstance(contribution.get("config"), dict)
            else {}
        )
        source_pack_id = str(contribution.get("source_pack_id") or "").strip()
        if source_pack_id and source_pack_id not in source_pack_ids:
            source_pack_ids.append(source_pack_id)
        if not presentation:
            presentation = _normalize_presentation(config.get("presentation"))
        for tool_id in _string_list(config.get("discovery_tools"), limit=16):
            if tool_id not in discovery_tools:
                discovery_tools.append(tool_id)
        for raw_phase in _dict_list(config.get("phases")):
            phase_id = str(raw_phase.get("id") or "").strip()
            prompt = str(raw_phase.get("prompt") or "").strip()
            if (
                not _ID_RE.match(phase_id)
                or phase_id in phase_ids
                or not prompt
                or len(phases) >= _MAX_EXTENSION_PHASES
            ):
                continue
            phase_ids.add(phase_id)
            phases.append(
                {
                    "id": phase_id,
                    "label": str(raw_phase.get("label") or phase_id)[:120],
                    "prompt": prompt[:8_000],
                    "source_pack_id": source_pack_id,
                }
            )
        for raw_perspective in _dict_list(config.get("perspectives")):
            perspective_id = str(raw_perspective.get("id") or "").strip()
            mission = str(raw_perspective.get("mission") or "").strip()
            if (
                not _ID_RE.match(perspective_id)
                or perspective_id in perspective_ids
                or not mission
                or len(perspectives) >= _MAX_PERSPECTIVES
            ):
                continue
            perspective_ids.add(perspective_id)
            perspectives.append(
                {
                    "id": perspective_id,
                    "name": str(
                        raw_perspective.get("name") or perspective_id
                    )[:120],
                    "mission": mission[:1_000],
                    "source_pack_id": source_pack_id,
                }
            )

    return {
        "discovery_tools": discovery_tools,
        "phases": phases,
        "perspectives": perspectives,
        "skills_visibility": "all_enabled",
        "source_pack_ids": source_pack_ids,
        "presentation": presentation,
    }


def available_skill_catalog(*, include_instructions: bool = False) -> list[dict[str, Any]]:
    """Return all enabled skills visible through the active resolved profile."""

    skills = get_extension_registry().skills().list(enabled_only=True)
    catalog: list[dict[str, Any]] = []
    for skill in skills[:_MAX_CATALOG_ITEMS]:
        skill_id = str(skill.get("id") or "").strip()
        if not skill_id:
            continue
        item = {
            "id": skill_id,
            "display_name": str(skill.get("display_name") or skill_id)[:160],
            "description": str(skill.get("description") or "")[:1_000],
            "triggers": _string_list(
                skill.get("triggers") or skill.get("keywords"),
                limit=24,
            ),
            "applies_to_tools": _string_list(
                skill.get("applies_to_tools") or skill.get("tool_ids"),
                limit=32,
            ),
            "source_pack_id": str(skill.get("source_pack_id") or ""),
        }
        if include_instructions:
            evaluated = RuntimeSkillTriggerService(skills=[skill]).evaluate(
                user_text="",
                context={"verified_explicit_skills": [skill_id]},
            )
            matched = evaluated.get("matched") if isinstance(evaluated, dict) else []
            if isinstance(matched, list) and matched:
                item["instructions"] = str(matched[0].get("instruction") or "")[
                    :80_000
                ]
        catalog.append(item)
    return catalog


def available_tool_catalog(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create a bounded public catalog from host-authorized provider tools."""

    catalog: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tool in tools[:_MAX_CATALOG_ITEMS]:
        if not isinstance(tool, dict):
            continue
        tool_id = str(tool_name_from_definition(tool) or "").strip()
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        catalog.append(
            {
                "id": tool_id,
                "description": str(
                    function.get("description")
                    or tool.get("description")
                    or ""
                )[:1_000],
                "requires_approval": bool(
                    tool.get("requires_approval")
                    or function.get("requires_approval")
                ),
            }
        )
    return catalog


def normalize_integration_plan(
    value: Any,
    *,
    tools: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    discovery_tools: list[str],
) -> dict[str, Any]:
    """Validate a model-proposed tool/skill plan against host-visible catalogs."""

    raw = value if isinstance(value, dict) else {}
    available_tools = {
        str(item.get("id") or "") for item in available_tool_catalog(tools)
    }
    available_skills = {
        str(item.get("id") or "") for item in skills if isinstance(item, dict)
    }
    selected_tool_ids = [
        item
        for item in _string_list(raw.get("selected_tool_ids"), limit=24)
        if item in available_tools
    ]
    selected_skill_ids = [
        item
        for item in _string_list(raw.get("selected_skill_ids"), limit=24)
        if item in available_skills
    ]
    available_discovery = [
        item for item in discovery_tools if item in available_tools
    ]
    return {
        "selected_tool_ids": selected_tool_ids,
        "selected_skill_ids": selected_skill_ids,
        "discovery_tool_ids": available_discovery,
        "tool_plan": _string_list(raw.get("tool_plan"), limit=16),
        "skill_plan": _string_list(raw.get("skill_plan"), limit=16),
        "rationale": str(raw.get("rationale") or "")[:4_000],
    }


def selected_skill_instructions(
    selected_skill_ids: list[str],
    *,
    skills: list[dict[str, Any]] | None = None,
) -> str:
    """Render only the skill instructions selected by integration planning."""

    if not selected_skill_ids:
        return ""
    evaluated = RuntimeSkillTriggerService(skills=skills).evaluate(
        user_text="",
        context={"skills": selected_skill_ids},
    )
    return (
        str(evaluated.get("instructions") or "").strip()
        if isinstance(evaluated, dict)
        else ""
    )


def selected_tool_definitions(
    tools: list[dict[str, Any]],
    selected_tool_ids: list[str],
) -> list[dict[str, Any]]:
    """Return the selected subset without allowing a model to invent tools."""

    selected = set(selected_tool_ids)
    return [
        tool
        for tool in tools
        if isinstance(tool, dict)
        and str(tool_name_from_definition(tool) or "") in selected
    ]


def _string_list(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _bounded_text(value: Any, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _choice(value: Any, *, field: str) -> str:
    candidate = _bounded_text(value, limit=32)
    return candidate if candidate in _PRESENTATION_CHOICES[field] else "none"


def _normalize_presentation(value: Any) -> dict[str, Any]:
    """Return the safe declarative subset consumed by the conversation UI."""

    if not isinstance(value, dict):
        return {}
    presentation_id = _bounded_text(value.get("id"), limit=96)
    if not _ID_RE.match(presentation_id):
        return {}
    motion = value.get("motion") if isinstance(value.get("motion"), dict) else {}
    event = value.get("event") if isinstance(value.get("event"), dict) else {}
    dynamic = (
        value.get("dynamic_phases")
        if isinstance(value.get("dynamic_phases"), dict)
        else {}
    )
    statuses = (
        value.get("statuses") if isinstance(value.get("statuses"), dict) else {}
    )
    feedback = (
        value.get("feedback") if isinstance(value.get("feedback"), dict) else {}
    )
    phases: list[dict[str, str]] = []
    for raw_phase in _dict_list(value.get("phases"))[:24]:
        phase_id = _bounded_text(raw_phase.get("id"), limit=96)
        if not _ID_RE.match(phase_id) or any(
            phase["id"] == phase_id for phase in phases
        ):
            continue
        phases.append(
            {
                "id": phase_id,
                "label": _bounded_text(raw_phase.get("label") or phase_id, limit=24),
                "description": _bounded_text(
                    raw_phase.get("description"),
                    limit=100,
                ),
            }
        )
    excluded = [
        item
        for item in _string_list(dynamic.get("excluded"), limit=24)
        if _ID_RE.match(item)
    ]
    return {
        "schema_version": 1,
        "id": presentation_id,
        "title": _bounded_text(value.get("title"), limit=120),
        "aria_label": _bounded_text(value.get("aria_label"), limit=120),
        "icon": _choice(value.get("icon"), field="icon"),
        "tone": _choice(value.get("tone"), field="tone"),
        "motion": {
            "entry": _choice(motion.get("entry"), field="entry"),
            "surface": _choice(motion.get("surface"), field="surface"),
            "indicator": _choice(
                motion.get("indicator"),
                field="indicator",
            ),
            "active_phase": _choice(
                motion.get("active_phase"),
                field="active_phase",
            ),
        },
        "event": {
            "template_id_field": _bounded_text(
                event.get("template_id_field"),
                limit=64,
            ),
            "phase_field": _bounded_text(event.get("phase_field"), limit=64),
            "phase_prefix": _bounded_text(event.get("phase_prefix"), limit=64),
        },
        "phases": phases,
        "dynamic_phases": {
            "insert_after": _bounded_text(
                dynamic.get("insert_after"),
                limit=96,
            ),
            "excluded": excluded,
        },
        "statuses": {
            key: _bounded_text(statuses.get(key), limit=40)
            for key in ("running", "completed", "paused", "failed")
        },
        "feedback": {
            key: _bounded_text(feedback.get(key), limit=180)
            for key in ("reviewing", "approved")
        },
    }
