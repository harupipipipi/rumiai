from __future__ import annotations

import copy
import time
import uuid
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_COMPANY_ID = "operations-company"
DEFAULT_COMPANY_NAME = "Rumi Operations Company"
DEFAULT_COMPANY_DESCRIPTION = "Persistent company workspace for coordinated AI roles."
DEFAULT_CONVERSATION_GROUP_ID = "company:operations-company"
DEFAULT_CHANNEL_ID = "ops-company"
DEFAULT_MODEL = "stub/default"


def gen_id(prefix: str = "") -> str:
    return prefix + str(uuid.uuid4())


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


DEFAULT_SETTINGS: dict[str, Any] = {
    "task_policy": "queued",
    "dispatch_policy": "local_queue_only",
    "normal_status_silent": True,
    "mentions_create_tasks": True,
    "direct_tool_execution": False,
}


DEFAULT_AGENT_SPECS: list[dict[str, Any]] = [
    {
        "agent_id": "client_manager",
        "role_key": "client_manager",
        "agent_name": "Client Manager",
        "display_name": "Client Manager",
        "model": DEFAULT_MODEL,
        "allowed_tools": ["rumi_api", "todo", "subagent"],
        "context_limit": 64000,
        "aliases": ["client"],
        "system_prompt": (
            "You are the client-facing manager. Keep one clear conversation with the user, "
            "translate user requests into company work, summarize internal progress, and ask "
            "for approval only when the company needs authority, credentials, or judgment."
        ),
    },
    {
        "agent_id": "operations_manager",
        "role_key": "operations_manager",
        "agent_name": "Operations Manager",
        "display_name": "Operations Manager",
        "model": DEFAULT_MODEL,
        "allowed_tools": ["rumi_api", "todo", "subagent"],
        "context_limit": 96000,
        "aliases": ["ops_manager", "manager"],
        "system_prompt": (
            "You operate the asynchronous company workspace. Triage open tasks, stale runs, "
            "blocked work, waiting approvals, unresolved mentions, and dirty summaries. "
            "Route work through AgentEngine delegation and never execute specialist tools directly."
        ),
    },
    {
        "agent_id": "project_manager",
        "role_key": "project_manager",
        "agent_name": "Project Manager",
        "display_name": "Project Manager",
        "model": DEFAULT_MODEL,
        "allowed_tools": ["rumi_api", "todo", "subagent", "web_search"],
        "context_limit": 96000,
        "aliases": ["pm", "project_manager"],
        "system_prompt": (
            "You own task decomposition, ownership, milestones, blocker routing, and final "
            "handoff quality. You delegate work to specialists; you do not write production "
            "code, execute terminal commands, or perform deep research directly."
        ),
    },
    {
        "agent_id": "coding_engineer",
        "role_key": "coding_engineer",
        "agent_name": "Coding Engineer",
        "display_name": "Coding Engineer",
        "model": DEFAULT_MODEL,
        "allowed_tools": [
            "rumi_api",
            "todo",
            "coding_file_read",
            "coding_file_search",
            "coding_file_list",
            "coding_file_write",
            "coding_file_create",
            "coding_file_patch",
            "coding_git_status",
            "coding_git_diff",
            "coding_terminal_exec",
        ],
        "context_limit": 128000,
        "aliases": ["engineer", "coder"],
        "system_prompt": (
            "You implement bounded code changes in the current workspace. Follow local style, "
            "keep diffs scoped, and report changed paths and validation back to the PM."
        ),
    },
    {
        "agent_id": "research_specialist",
        "role_key": "research_specialist",
        "agent_name": "Research Specialist",
        "display_name": "Research Specialist",
        "model": DEFAULT_MODEL,
        "allowed_tools": ["rumi_api", "web_search", "reddit_search", "file_reader", "todo"],
        "context_limit": 96000,
        "aliases": ["researcher", "research"],
        "system_prompt": (
            "You research facts, docs, competitive behavior, and user voice. Prefer primary "
            "sources and note uncertainty, dates, and citations in reports."
        ),
    },
    {
        "agent_id": "reviewer",
        "role_key": "reviewer",
        "agent_name": "Reviewer",
        "display_name": "Reviewer",
        "model": DEFAULT_MODEL,
        "allowed_tools": [
            "rumi_api",
            "coding_file_read",
            "coding_file_search",
            "coding_git_status",
            "coding_git_diff",
            "coding_terminal_exec",
        ],
        "context_limit": 96000,
        "aliases": ["review"],
        "system_prompt": (
            "You review work for correctness, safety, missing tests, and drift from the user "
            "goal. Lead with actionable findings and residual risk."
        ),
    },
    {
        "agent_id": "operations_monitor",
        "role_key": "operations_monitor",
        "agent_name": "Operations Monitor",
        "display_name": "Operations Monitor",
        "model": DEFAULT_MODEL,
        "allowed_tools": ["rumi_api", "browser_use", "browser_computer", "web_search", "todo"],
        "context_limit": 64000,
        "aliases": ["monitor"],
        "system_prompt": (
            "You watch dashboards, queues, websites, and integrations. Stay silent on normal "
            "checks unless asked, and escalate incidents with evidence and next action."
        ),
    },
    {
        "agent_id": "scribe",
        "role_key": "scribe",
        "agent_name": "Scribe",
        "display_name": "Scribe",
        "model": DEFAULT_MODEL,
        "allowed_tools": ["rumi_api", "todo"],
        "context_limit": 64000,
        "aliases": ["summary", "summarizer"],
        "system_prompt": (
            "You maintain concise summaries for company, channel, thread, task, and run scopes. "
            "Capture decisions, blockers, owners, and current status without taking ownership of execution."
        ),
    },
    {
        "agent_id": "scheduler",
        "role_key": "scheduler",
        "agent_name": "Scheduler",
        "display_name": "Scheduler",
        "model": DEFAULT_MODEL,
        "allowed_tools": ["rumi_api", "todo", "subagent"],
        "context_limit": 48000,
        "aliases": ["schedule"],
        "system_prompt": (
            "You manage recurring tasks and heartbeat jobs. Avoid creating schedule loops, "
            "keep cadence explicit, and report only meaningful changes."
        ),
    },
]


def default_agents() -> list[dict[str, Any]]:
    return [normalize_agent(agent) for agent in DEFAULT_AGENT_SPECS]


def default_channel(now: str | None = None) -> dict[str, Any]:
    ts = now or timestamp()
    return {
        "id": DEFAULT_CHANNEL_ID,
        "name": DEFAULT_CHANNEL_ID,
        "description": "Internal company coordination channel.",
        "visibility": "team",
        "members": [agent["agent_id"] for agent in DEFAULT_AGENT_SPECS],
        "mentions": True,
        "append_only": True,
        "message_count": 0,
        "last_message_at": None,
        "metadata": {"default": True},
        "created_at": ts,
        "updated_at": ts,
    }


def normalize_agent(agent: dict[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(agent)
    agent_id = str(item.get("agent_id") or item.get("id") or item.get("role_key") or "").strip()
    if not agent_id:
        agent_id = gen_id("agent_")
    item["id"] = agent_id
    item["agent_id"] = agent_id
    item["role_key"] = str(item.get("role_key") or agent_id).strip()
    item["agent_name"] = str(item.get("agent_name") or item.get("display_name") or agent_id).strip()
    item["display_name"] = str(item.get("display_name") or item["agent_name"]).strip()
    item["model"] = str(item.get("model") or DEFAULT_MODEL).strip()
    item["allowed_tools"] = list(item.get("allowed_tools") or [])
    item["context_limit"] = int(item.get("context_limit") or 64000)
    item["aliases"] = [str(alias).strip().lstrip("@") for alias in item.get("aliases", []) if str(alias).strip()]
    item.setdefault("status", "idle")
    item.setdefault("metadata", {})
    item.setdefault("created_at", timestamp())
    item["updated_at"] = timestamp()
    return item


def normalize_company(company: dict[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(company)
    now = timestamp()
    item.setdefault("id", gen_id("company_"))
    item["id"] = str(item["id"])
    item.setdefault("name", DEFAULT_COMPANY_NAME)
    item.setdefault("description", "")
    item.setdefault("status", "active")
    item.setdefault("conversation_group_id", "company:" + item["id"])
    item.setdefault("settings", copy.deepcopy(DEFAULT_SETTINGS))
    item.setdefault("metadata", {})
    item.setdefault("agents", {})
    item.setdefault("channels", {})
    item.setdefault("messages", {})
    item.setdefault("tasks", {})
    item.setdefault("inbound_routes", {})
    item.setdefault("created_at", now)
    item.setdefault("updated_at", now)
    if isinstance(item["agents"], list):
        item["agents"] = {agent["agent_id"]: normalize_agent(agent) for agent in item["agents"] if isinstance(agent, dict)}
    elif isinstance(item["agents"], dict):
        item["agents"] = {
            str(agent_id): normalize_agent(agent if isinstance(agent, dict) else {"agent_id": str(agent_id)})
            for agent_id, agent in item["agents"].items()
        }
    else:
        item["agents"] = {}
    if not isinstance(item["channels"], dict):
        item["channels"] = {}
    if not isinstance(item["messages"], dict):
        item["messages"] = {}
    if not isinstance(item["tasks"], dict):
        item["tasks"] = {}
    if not isinstance(item["inbound_routes"], dict):
        item["inbound_routes"] = {}
    return item


def public_company(company: dict[str, Any]) -> dict[str, Any]:
    item = normalize_company(company)
    item["agent_count"] = len(item.get("agents", {}))
    item["channel_count"] = len(item.get("channels", {}))
    item["message_count"] = len(item.get("messages", {}))
    item["task_count"] = len(item.get("tasks", {}))
    return item
