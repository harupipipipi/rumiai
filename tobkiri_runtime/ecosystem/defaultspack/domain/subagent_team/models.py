from __future__ import annotations

from typing import Any

from domain.company.models import DEFAULT_COMPANY_ID, DEFAULT_COMPANY_NAME, normalize_agent, timestamp

from .ids import channel_id_from_name, generate_internal_uuid, is_uuid, stable_short_id


DEFAULT_TEAM_COMPANY_ID = DEFAULT_COMPANY_ID
DEFAULT_TEAM_COMPANY_NAME = DEFAULT_COMPANY_NAME
SUBAGENT_METADATA_KEY = "subagent_team"
DEFAULT_RICH_LIMIT = 5
PM_THRESHOLD = 5

ROLE_ICON: dict[str, str] = {
    "creator": "network",
    "pm": "crown",
    "project_manager": "crown",
    "planner": "sparkles",
    "architect": "diagram",
    "coder": "code",
    "coding_engineer": "code",
    "qa": "flask",
    "checker": "shield-check",
    "reviewer": "search",
    "researcher": "book-open",
    "documenter": "file-text",
    "browser_operator": "mouse-pointer-click",
    "main": "sparkles",
    "human": "user",
}

TOOL_ID_ALIASES: dict[str, str] = {
    "channel_check": "channel.check",
    "subagent_request": "subagent.request",
    "subagent_status": "subagent.status",
    "subagent_create": "subagent.create",
    "subagent_dm_send": "subagent.dm.send",
    "subagent_channel_join": "subagent.channel.join",
    "subagent_goal_propose": "subagent.goal.propose",
    "subagent_goal_approve": "subagent.goal.approve",
    "subagent_task_complete": "subagent.task.complete",
}

ROLE_TOOLS: dict[str, list[str]] = {
    "creator": [
        "channel_check",
        "subagent_request",
        "subagent_status",
        "subagent_create",
        "subagent_dm_send",
        "subagent_channel_join",
    ],
    "pm": ["channel_check", "subagent_dm_send", "subagent_goal_approve", "subagent_task_complete", "todo"],
    "planner": ["channel_check", "subagent_dm_send", "subagent_goal_propose", "todo"],
    "architect": ["channel_check", "subagent_dm_send", "subagent_goal_propose", "coding_file_read", "coding_file_search", "todo"],
    "coder": [
        "channel_check",
        "subagent_dm_send",
        "subagent_goal_propose",
        "coding_file_read",
        "coding_file_search",
        "coding_file_patch",
        "coding_file_write",
        "coding_terminal_exec",
    ],
    "qa": ["channel_check", "subagent_dm_send", "subagent_goal_propose", "coding_file_read", "coding_file_search", "coding_terminal_exec"],
    "checker": ["channel_check", "subagent_dm_send", "subagent_goal_propose", "coding_file_read", "coding_file_search", "coding_git_diff", "coding_terminal_exec"],
    "reviewer": ["channel_check", "subagent_dm_send", "subagent_goal_propose", "coding_file_read", "coding_file_search", "coding_git_diff"],
    "researcher": ["channel_check", "subagent_dm_send", "subagent_goal_propose", "web_search", "file_reader", "todo"],
    "documenter": ["channel_check", "subagent_dm_send", "subagent_goal_propose", "coding_file_read", "coding_file_patch", "todo"],
}


MAIN_SYSTEM_PROMPT_FRAGMENT = """Subagent/team/channel/PM/delegated-agent/DM/rich-mode/status decisions are not managed directly by Main.
Main only summarizes user intent and sends it to Subagent Creator through subagent.request or subagent.status.
Main must not create, delete, pause, resume, assign, or reconfigure subagents directly.
"""

CREATOR_SYSTEM_PROMPT = """You are the Subagent Creator and Team Orchestrator.
You manage subagents, teams, channels, PM assignment, DM routing, model/tool selection, rich-mode limits, and status aggregation.
You do not write code, execute domain tasks, browse, send external messages, or directly complete user work.
All lifecycle and status decisions flow through you; execution still flows through AgentEngine and existing approval policy.
You cannot enable /rich, treat PM receipts as user approval, or bypass local approval, workspace trust, capability policy, or audit paths.
"""

PM_SYSTEM_PROMPT = """You are the PM for this channel.
Plan, assign, review, approve /goal, monitor progress, request checkers through Creator, and mark task completion.
Do not bypass user approval for risky tools. A task is not complete until you emit task_complete with evidence.
"""

WORKER_SYSTEM_PROMPT = """You are a delegated worker subagent.
Before acting, use channel.check. Respond only when mentioned, assigned, DM'ed, or instructed through a valid channel event.
Respect PM gates and use your short id when referring to yourself. If asked to manage subagents, ask the Subagent Creator.
"""

CHECKER_SYSTEM_PROMPT = """You are a checker subagent.
Before acting, use channel.check. Verify work, tests, regressions, and evidence for the channel task.
Do not mark the channel task complete; report findings to the PM or Creator so the PM can emit task_complete.
"""

HIERARCHY_CONTRACT = "Main Agent -> Subagent Creator -> PM -> Workers / Checkers"
PM_GATE_CONTRACT = "PM gate: direct specialist routing and /goal approval go through the channel PM when present or required."
DM_RULES_CONTRACT = "DM rules: use short ids for DM routing; DM messages still require membership and channel.check context."
CHANNEL_CHECK_CONTRACT = "channel.check is required at the start of every subagent turn and before acting on channel/DM/goal state."
TASK_COMPLETION_CONTRACT = "Task completion: worker/checker updates are not final; PM task_complete with evidence is required when a PM exists or channel size is 5+."


def metadata_of(item: dict[str, Any] | None) -> dict[str, Any]:
    metadata = (item or {}).get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def team_metadata(item: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata_of(item)
    nested = metadata.get(SUBAGENT_METADATA_KEY)
    return nested if isinstance(nested, dict) else {}


def role_icon(role: str) -> str:
    return ROLE_ICON.get(str(role or "").strip().lower(), "bot")


def tools_for_role(role: str) -> list[str]:
    return list(ROLE_TOOLS.get(str(role or "").strip().lower(), ["channel_check", "todo"]))


def tool_aliases_for(tools: list[str]) -> dict[str, str]:
    return {tool: TOOL_ID_ALIASES[tool] for tool in tools if tool in TOOL_ID_ALIASES}


def display_name_for_role(role: str, index: int = 1) -> str:
    names = {
        "pm": "pm_orion",
        "planner": "planner_mira",
        "architect": "architect_mira",
        "coder": "coder_kai",
        "qa": "qa_sen",
        "checker": "checker_lynx",
        "reviewer": "reviewer_lynx",
        "researcher": "researcher_nova",
        "documenter": "documenter_ren",
    }
    base = names.get(role, f"{role or 'agent'}_{index}")
    return base if index <= 1 else f"{base}_{index}"


def make_agent_spec(
    *,
    display_name: str,
    role: str,
    model: str = "default",
    channels: list[str] | None = None,
    existing_short_ids: list[str] | None = None,
    system_prompt_profile: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    role_key = str(role or "worker").strip().lower()
    short_id = _subagent_short_id(display_name, role_key, existing=existing_short_ids or [])
    legacy_short_id = stable_short_id("ag", display_name + ":" + role_key, existing=existing_short_ids or [])
    requested_agent_id = str(agent_id or "").strip()
    internal_id = requested_agent_id if requested_agent_id and is_uuid(requested_agent_id) else generate_internal_uuid()
    channel_ids = list(channels or [])
    prompt = system_prompt_for_role(
        role_key=role_key,
        uuid=internal_id,
        short_id=short_id,
        display_name=display_name,
        channels=channel_ids,
    )
    aliases = [short_id, legacy_short_id, display_name, role_key]
    if requested_agent_id and requested_agent_id not in aliases:
        aliases.append(requested_agent_id)
    metadata = {
        SUBAGENT_METADATA_KEY: {
            "uuid": internal_id,
            "short_id": short_id,
            "legacy_short_id": legacy_short_id,
            "display_name": display_name,
            "role": role_key,
            "channels": list(channels or []),
            "icon_svg_id": role_icon(role_key),
            "creator_managed": True,
            "pm_capable": role_key == "pm",
            "checker_capable": role_key in {"checker", "qa", "reviewer"},
            "system_prompt_profile": system_prompt_profile or f"{role_key}_default",
            "hierarchy": HIERARCHY_CONTRACT,
            "pm_gate": PM_GATE_CONTRACT,
            "dm_rules": DM_RULES_CONTRACT,
            "task_completion_condition": TASK_COMPLETION_CONTRACT,
            "channel_check_required": True,
            "channel_check_contract": CHANNEL_CHECK_CONTRACT,
            "provider_safe_tool_ids": tools_for_role(role_key),
            "tool_aliases": tool_aliases_for(tools_for_role(role_key)),
            "legacy_alias": requested_agent_id or None,
        }
    }
    return normalize_agent(
        {
            "agent_id": internal_id,
            "role_key": role_key,
            "agent_name": display_name,
            "display_name": display_name,
            "model": model or "default",
            "allowed_tools": tools_for_role(role_key),
            "aliases": aliases,
            "system_prompt": prompt,
            "metadata": metadata,
        }
    )


def system_prompt_for_role(
    *,
    role_key: str,
    uuid: str,
    short_id: str,
    display_name: str,
    channels: list[str] | None = None,
) -> str:
    role = str(role_key or "worker").strip().lower()
    if role == "creator":
        base = CREATOR_SYSTEM_PROMPT
    elif role == "pm":
        base = PM_SYSTEM_PROMPT
    elif role in {"checker", "qa", "reviewer"}:
        base = CHECKER_SYSTEM_PROMPT
    else:
        base = WORKER_SYSTEM_PROMPT
    return "\n".join(
        [
            base.strip(),
            "",
            "Identity contract:",
            "- Display name: " + str(display_name or role),
            "- Internal uuid: " + str(uuid or ""),
            "- Human-facing short id: " + str(short_id or ""),
            "- Channels: " + (", ".join(str(item) for item in (channels or []) if str(item).strip()) or "none assigned"),
            "- Hierarchy: " + HIERARCHY_CONTRACT,
            "- " + PM_GATE_CONTRACT,
            "- " + DM_RULES_CONTRACT,
            "- " + CHANNEL_CHECK_CONTRACT,
            "- " + TASK_COMPLETION_CONTRACT,
        ]
    )


def _subagent_short_id(display_name: str, role_key: str, *, existing: list[str]) -> str:
    seed = str(display_name or "") + ":" + str(role_key or "")
    candidate = stable_short_id("sa", seed, existing=existing)
    if candidate.startswith("sa_"):
        candidate = "sa-" + candidate.split("_", 1)[1]
    seen = {str(item) for item in existing}
    if candidate not in seen:
        return candidate
    suffix = 2
    while f"{candidate}-{suffix}" in seen:
        suffix += 1
    return f"{candidate}-{suffix}"


def make_channel_spec(
    *,
    name: str,
    kind: str = "public",
    members: list[str] | None = None,
    pm_required: bool = False,
    pm_agent_id: str | None = None,
    rich_required: bool = False,
) -> dict[str, Any]:
    channel_id = channel_id_from_name(name)
    member_ids = list(dict.fromkeys([str(item) for item in (members or []) if str(item).strip()]))
    return {
        "id": channel_id,
        "name": channel_id,
        "description": "Creator-managed subagent team channel.",
        "visibility": "private" if kind == "private" else "team",
        "members": member_ids,
        "metadata": {
            SUBAGENT_METADATA_KEY: {
                "kind": kind,
                "pm_required": bool(pm_required),
                "pm_agent_id": pm_agent_id,
                "member_count_cache": len(member_ids),
                "rich_required": bool(rich_required),
                "created_by": "subagent_creator",
            }
        },
    }


def public_agent(agent: dict[str, Any]) -> dict[str, Any]:
    team = team_metadata(agent)
    role = str(team.get("role") or agent.get("role_key") or "worker")
    return {
        "id": str(agent.get("agent_id") or agent.get("id") or ""),
        "uuid": str(team.get("uuid") or agent.get("agent_id") or agent.get("id") or ""),
        "short_id": str(team.get("short_id") or agent.get("agent_id") or agent.get("id") or ""),
        "legacy_short_id": str(team.get("legacy_short_id") or ""),
        "display_name": str(team.get("display_name") or agent.get("display_name") or ""),
        "role": role,
        "status": str(agent.get("status") or "idle"),
        "model_ref": str(agent.get("model") or "default"),
        "icon_svg_id": str(team.get("icon_svg_id") or role_icon(role)),
        "channels": list(team.get("channels") or []),
        "creator_managed": bool(team.get("creator_managed", True)),
        "pm_capable": bool(team.get("pm_capable", role == "pm")),
        "checker_capable": bool(team.get("checker_capable", role in {"checker", "qa", "reviewer"})),
        "tools": list(agent.get("allowed_tools") or []),
        "tool_aliases": dict(team.get("tool_aliases") or tool_aliases_for(list(agent.get("allowed_tools") or []))),
        "created_at": agent.get("created_at"),
        "updated_at": agent.get("updated_at"),
    }


def public_channel(channel: dict[str, Any], agents_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    team = team_metadata(channel)
    member_ids = [str(item) for item in channel.get("members", [])]
    agents_by_id = agents_by_id or {}
    members = [public_agent(agents_by_id[item]) for item in member_ids if item in agents_by_id]
    return {
        "id": str(channel.get("id") or channel.get("channel_id") or ""),
        "short_id": str(channel.get("id") or channel.get("channel_id") or ""),
        "name": str(channel.get("name") or channel.get("id") or ""),
        "kind": str(team.get("kind") or "public"),
        "visibility": str(channel.get("visibility") or "team"),
        "member_count": int(team.get("member_count_cache") or len(member_ids)),
        "members": members,
        "member_ids": member_ids,
        "pm_required": bool(team.get("pm_required", len(member_ids) >= PM_THRESHOLD)),
        "pm_agent_id": team.get("pm_agent_id"),
        "rich_required": bool(team.get("rich_required", False)),
        "message_count": int(channel.get("message_count") or 0),
        "last_message_at": channel.get("last_message_at"),
        "created_at": channel.get("created_at"),
        "updated_at": channel.get("updated_at"),
    }


def public_message(message: dict[str, Any], agents_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    metadata = metadata_of(message)
    team = metadata.get(SUBAGENT_METADATA_KEY) if isinstance(metadata.get(SUBAGENT_METADATA_KEY), dict) else {}
    sender_id = str(message.get("sender_id") or "")
    agent = (agents_by_id or {}).get(sender_id)
    sender = public_agent(agent) if agent else {
        "id": sender_id,
        "short_id": sender_id,
        "display_name": str(team.get("sender_display_name") or sender_id or "human"),
        "role": str(team.get("sender_role") or "human"),
        "icon_svg_id": str(team.get("sender_icon_svg_id") or role_icon(str(team.get("sender_role") or "human"))),
    }
    return {
        "id": str(message.get("message_id") or message.get("id") or ""),
        "channel_id": str(message.get("channel_id") or ""),
        "thread_id": message.get("thread_id"),
        "sender": sender,
        "sender_kind": str(team.get("sender_kind") or ("agent" if agent else "human")),
        "body": str(message.get("content") or message.get("body") or ""),
        "mentions": list(message.get("mentions") or []),
        "attachments": list(team.get("attachments") or []),
        "tool_calls": team.get("tool_calls"),
        "approval_refs": list(team.get("approval_refs") or []),
        "created_at": message.get("created_at") or timestamp(),
    }
