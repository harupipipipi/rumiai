from __future__ import annotations

from copy import deepcopy
from typing import Any

from .agent_definition import AgentDefinition


TEMPLATES: dict[str, dict[str, Any]] = {
    "browser_operator": {
        "display_name": "Browser Operator",
        "role_key": "browser_operator",
        "system_prompt": "Operate browser sessions with snapshot/ref actions and fall back to computer use only when needed.",
        "tool_policy": {"allowlist": ["browser_use", "todo", "rumi_api"], "browser_profile_id": "operations-company"},
    },
    "computer_operator": {
        "display_name": "Computer Operator",
        "role_key": "computer_operator",
        "system_prompt": "Inspect the desktop before acting and keep risky OS actions approval-gated.",
        "tool_policy": {"allowlist": ["computer_use", "browser_computer", "todo"], "computer_use_mode": "inspect_first"},
    },
    "research_monitor": {
        "display_name": "Research Monitor",
        "role_key": "research_specialist",
        "system_prompt": "Monitor requested sources and report only important changes with evidence.",
        "tool_policy": {"allowlist": ["browser_use", "web_search", "todo", "rumi_api"]},
        "runtime_policy": {"non_stop": True, "normal_status_silent": True},
    },
    "coding_engineer": {
        "display_name": "Coding Engineer",
        "role_key": "coding_engineer",
        "system_prompt": "Implement bounded code changes and report changed files and validation.",
        "tool_policy": {"allowlist": ["coding_file_read", "coding_file_search", "coding_file_write", "coding_file_patch", "coding_terminal_exec"]},
    },
    "reviewer": {
        "display_name": "Reviewer",
        "role_key": "reviewer",
        "system_prompt": "Review for correctness, safety, missing tests, and behavioral regressions.",
        "tool_policy": {"allowlist": ["coding_file_read", "coding_file_search", "coding_git_diff", "coding_terminal_exec"]},
    },
    "scheduler": {
        "display_name": "Scheduler",
        "role_key": "scheduler",
        "system_prompt": "Manage recurring tasks and avoid schedule loops.",
        "tool_policy": {"allowlist": ["todo", "rumi_api", "subagent"]},
    },
    "operations_monitor": {
        "display_name": "Operations Monitor",
        "role_key": "operations_monitor",
        "system_prompt": "Watch operations surfaces and escalate incidents only when action is needed.",
        "tool_policy": {"allowlist": ["browser_use", "computer_use", "browser_computer", "web_search", "todo", "rumi_api"]},
        "runtime_policy": {"non_stop": True, "normal_status_silent": True},
    },
    "custom": {
        "display_name": "Custom Agent",
        "role_key": "custom",
        "system_prompt": "",
        "tool_policy": {"allowlist": ["todo", "rumi_api"]},
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [{"template_id": key, **deepcopy(value)} for key, value in sorted(TEMPLATES.items())]


def get_template(template_id: str) -> dict[str, Any]:
    return deepcopy(TEMPLATES.get(template_id) or TEMPLATES["custom"])


class AgentTemplates:
    @staticmethod
    def from_role_definition(role: dict[str, Any]) -> AgentDefinition:
        return AgentDefinition.from_role(role, profile_id="defaultspack.operations_company")
