from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_PACK_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTSPACK_ROOT = _PACK_ROOT.parent / "defaultspack"
for _path in (str(_PACK_ROOT), str(_DEFAULTSPACK_ROOT)):
    if _path in sys.path:
        sys.path.remove(_path)
for _path in (str(_PACK_ROOT), str(_DEFAULTSPACK_ROOT)):
    sys.path.insert(0, _path)

from blocks._common import timestamp
from domain.agent.org_manager import OrgManager
from domain.agent.role_registry import RoleRegistry
from domain.agent.schedule_store import load_all_schedules, save_schedule
from domain.agent.scheduler import Scheduler
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
from domain.ai_client.providers import get_all_known_models
from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.service import CompanyService
from domain.company.task_store import CompanyTaskStore
from domain.knowledge.store import KnowledgeStore


PROFILE_ID = "defaultspack.mimo_coding_company"
CONVERSATION_KIND = "mimo_coding_company"
COMPANY_ID = "mimo-coding-company"
COMPANY_NAME = "MiMo Coding Company"
COMPANY_DESCRIPTION = "Self-improving MiMo-first coding company for long-running repo work."
DEFAULT_MAIN_MODEL = "xiaomi-token-plan-sgp/mimo-v2.5-pro"
DEFAULT_VISION_MODEL = "xiaomi-token-plan-sgp/mimo-v2-omni"
DEFAULT_FAST_MODEL = "xiaomi-token-plan-sgp/mimo-v2.5"
SCHEDULE_LOOP_KEYS = {"kickoff_review", "heartbeat", "improvement_loop", "qa_loop"}
DEFAULT_DOCKER_WORKER_COUNT = 3
MAX_TOOL_CALLS_LIMIT = 200
SUBAGENT_GAP_GRACE_SECONDS = 300
MIMO_OBSERVABILITY_HISTORY_LIMIT = 5

DEFAULT_PERSONA_SPECS = [
    {
        "id": "first_time_user",
        "label": "First-time user",
        "goal": "Find broken onboarding, missing defaults, and dead-end flows.",
    },
    {
        "id": "power_user",
        "label": "Power user",
        "goal": "Stress advanced controls, model settings, and bulk actions.",
    },
    {
        "id": "impatient_user",
        "label": "Impatient user",
        "goal": "Interrupt flows, click quickly, and expose brittle loading states.",
    },
    {
        "id": "keyboard_heavy_user",
        "label": "Keyboard-heavy user",
        "goal": "Check focus order, shortcuts, and input affordances.",
    },
]

IMPROVEMENT_STREAMS = [
    {
        "id": "initial_harness_review",
        "title": "Initial harness review",
        "description": "Review the repo and current harness shape. Prefer one small high-value improvement first.",
        "target_agent_ids": ["project_manager", "reviewer"],
        "preferred_tools": ["todo", "subagent", "coding_git_diff", "knowledge_create"],
        "owner_role": "project_manager",
        "preferred_model_role": "main",
    },
    {
        "id": "provider_search_coverage",
        "title": "Provider and search coverage",
        "description": "Improve search quality, provider discovery, and model catalogs. Keep Groq, Cerebras, and Xiaomi current.",
        "target_agent_ids": ["toolsmith", "project_manager"],
        "preferred_tools": ["web_search", "knowledge_search", "knowledge_create", "coding_file_patch"],
        "owner_role": "toolsmith",
        "preferred_model_role": "main",
    },
    {
        "id": "frontend_qa_swarm",
        "title": "Frontend QA swarm",
        "description": "Run browser and computer-use QA with multiple personas and log only evidence-backed bugs.",
        "target_agent_ids": ["browser_qa", "reviewer"],
        "preferred_tools": [
            "browser_use",
            "browser_companion",
            "computer_use",
            "desktop_list",
            "desktop_create",
            "desktop_frame",
            "desktop_input",
            "todo",
        ],
        "owner_role": "browser_qa",
        "preferred_model_role": "vision",
    },
    {
        "id": "docker_worker_swarm",
        "title": "Docker worker swarm",
        "description": "Use isolated Ubuntu Docker workers for browser and computer-use QA whenever Docker is available.",
        "target_agent_ids": ["browser_qa", "toolsmith"],
        "preferred_tools": ["coding_terminal_exec", "sandbox_exec", "computer_use", "knowledge_create"],
        "owner_role": "toolsmith",
        "preferred_model_role": "vision",
    },
    {
        "id": "tool_skill_gap_closure",
        "title": "Tool and skill gap closure",
        "description": "When a task needs a missing tool or skill, create the smallest viable one instead of giving up.",
        "target_agent_ids": ["toolsmith", "coding_engineer"],
        "preferred_tools": ["coding_file_patch", "coding_file_create", "knowledge_create", "subagent"],
        "owner_role": "toolsmith",
        "preferred_model_role": "main",
    },
    {
        "id": "knowledge_capture_loop",
        "title": "Knowledge capture loop",
        "description": "Keep the knowledge bundle current so later self-improvement loops learn from wins, failures, and QA findings.",
        "target_agent_ids": ["project_manager", "toolsmith"],
        "preferred_tools": ["knowledge_create", "knowledge_update", "knowledge_search", "todo"],
        "owner_role": "project_manager",
        "preferred_model_role": "fast",
    },
]

PERSONA_MISSIONS = {
    "first_time_user": {
        "mission": "Find onboarding gaps, missing defaults, and dead-end flows.",
        "probe_areas": ["landing flow", "first task creation", "empty states", "setup defaults"],
    },
    "power_user": {
        "mission": "Stress advanced controls, provider settings, and bulk actions.",
        "probe_areas": ["settings panels", "model picker", "tool toggles", "batch actions"],
    },
    "impatient_user": {
        "mission": "Interrupt flows, click early, and expose brittle loading states.",
        "probe_areas": ["loading states", "retry flows", "navigation while pending", "double-submit safety"],
    },
    "keyboard_heavy_user": {
        "mission": "Check focus order, shortcuts, and keyboard-only usability.",
        "probe_areas": ["focus order", "composer submit/cancel", "dialogs", "sidebar navigation"],
    },
}

TERMINAL_TASK_STATUSES = {"done", "completed", "closed", "cancelled", "canceled", "resolved"}

FALLBACK_KNOWLEDGE_DOCS = [
    (
        "README.md",
        "# MiMo Coding Company\n\n"
        "This harness runs MiMo-first long-lived coding loops with a Client Manager, PM, coder, reviewer, QA, "
        "toolsmith, and scheduler.\n",
    ),
    (
        "self_improvement_loop.md",
        "# Self Improvement Loop\n\n"
        "Start with one small verified improvement. If a missing tool or skill blocks progress, build the smallest "
        "viable version instead of stopping.\n",
    ),
    (
        "docker_worker_swarm.md",
        "# Docker Worker Swarm\n\n"
        "Use isolated Ubuntu workers for browser/computer-use QA when Docker is available. Assign different personas "
        "and targets to separate workers.\n",
    ),
]

MODEL_ALLOWLIST = [
    "opencode-go/mimo-v2.5-pro",
    "opencode-go/mimo-v2.5",
    "google/gemma-4-31b-it",
    "google/gemma-4-26b-a4b-it",
    "xiaomi-token-plan-sgp/mimo-v2.5-pro",
    "xiaomi-token-plan-sgp/mimo-v2.5",
    "xiaomi-token-plan-sgp/mimo-v2-pro",
    "xiaomi-token-plan-sgp/mimo-v2-omni",
    "xiaomi-token-plan-sgp/mimo-v2-flash",
    "gitlawb-opengateway/mimo-v2.5-pro",
    "gitlawb-opengateway/mimo-v2.5",
    "gitlawb-opengateway/mimo-v2-pro",
    "gitlawb-opengateway/mimo-v2-omni",
    "gitlawb-opengateway/mimo-v2-flash",
    "groq/openai/gpt-oss-120b",
    "cerebras/gpt-oss-120b",
    "stub/default",
]

CATALOG_EXPANDED_MODEL_PROVIDERS = ("opencode-go", "google", "groq", "cerebras")

UTILITY_MODELS = {
    "subagent_default": DEFAULT_MAIN_MODEL,
    "tool_selector": DEFAULT_FAST_MODEL,
    "prompt_compactor": DEFAULT_FAST_MODEL,
    "context_summarizer": DEFAULT_FAST_MODEL,
    "model_router": DEFAULT_MAIN_MODEL,
    "vision_ocr": DEFAULT_VISION_MODEL,
    "fast_reply": DEFAULT_FAST_MODEL,
}

TOOL_ALLOWLIST = [
    "rumi_api",
    "todo",
    "subagent",
    "web_search",
    "reddit_search",
    "file_reader",
    "browser_use",
    "browser_computer",
    "browser_companion",
    "computer_use",
    "desktop_list",
    "desktop_create",
    "desktop_frame",
    "desktop_input",
    "coding_file_read",
    "coding_file_search",
    "coding_file_list",
    "coding_file_write",
    "coding_file_create",
    "coding_file_patch",
    "coding_file_restore",
    "coding_git_status",
    "coding_git_diff",
    "coding_git_push",
    "coding_terminal_exec",
    "sandbox_exec",
    "python_exec",
    "node_exec",
    "knowledge_create",
    "knowledge_list",
    "knowledge_get",
    "knowledge_search",
    "knowledge_update",
]

ROLE_DEFINITIONS = [
    {
        "agent_id": "client_manager",
        "role_key": "client_manager",
        "agent_name": "Client Manager",
        "display_name": "Client Manager",
        "model": DEFAULT_MAIN_MODEL,
        "allowed_tools": ["rumi_api", "todo", "subagent"],
        "context_limit": 64000,
        "system_prompt": "Own the user thread. Turn intent into tasks. Ask only when approval or judgment is needed.",
    },
    {
        "agent_id": "project_manager",
        "role_key": "project_manager",
        "agent_name": "Project Manager",
        "display_name": "Project Manager",
        "model": DEFAULT_MAIN_MODEL,
        "allowed_tools": ["rumi_api", "todo", "subagent", "web_search", "knowledge_search", "knowledge_create"],
        "context_limit": 96000,
        "system_prompt": "Pick the next small win. Split work clearly. Keep the loop moving.",
    },
    {
        "agent_id": "coding_engineer",
        "role_key": "coding_engineer",
        "agent_name": "Coding Engineer",
        "display_name": "Coding Engineer",
        "model": DEFAULT_MAIN_MODEL,
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
            "coding_git_push",
            "coding_terminal_exec",
            "sandbox_exec",
            "python_exec",
            "node_exec",
        ],
        "context_limit": 128000,
        "system_prompt": "Make the smallest useful code change. Verify it. Report exact files and checks.",
    },
    {
        "agent_id": "reviewer",
        "role_key": "reviewer",
        "agent_name": "Reviewer",
        "display_name": "Reviewer",
        "model": DEFAULT_MAIN_MODEL,
        "allowed_tools": [
            "rumi_api",
            "coding_file_read",
            "coding_file_search",
            "coding_git_status",
            "coding_git_diff",
            "coding_terminal_exec",
            "knowledge_search",
        ],
        "context_limit": 96000,
        "system_prompt": "Find concrete bugs, regressions, and missing tests. Lead with findings.",
    },
    {
        "agent_id": "browser_qa",
        "role_key": "browser_qa",
        "agent_name": "Browser QA",
        "display_name": "Browser QA",
        "model": DEFAULT_VISION_MODEL,
        "allowed_tools": [
            "rumi_api",
            "todo",
            "browser_use",
            "browser_computer",
            "browser_companion",
            "computer_use",
            "desktop_list",
            "desktop_create",
            "desktop_frame",
            "desktop_input",
            "web_search",
        ],
        "context_limit": 96000,
        "system_prompt": (
            "Act like a real user. Click around, break things, and file only evidence-backed bugs. "
            "If browser tools are unpaired or unavailable, create/use a managed desktop seat before stopping. "
            "Desktop and sandbox access comes from trusted local/server context; do not add payload owner_id as proof of access. "
            "For desktop_input, always include action; type with action=type_text plus text, "
            "and press keys with action=key plus key."
        ),
    },
    {
        "agent_id": "toolsmith",
        "role_key": "toolsmith",
        "agent_name": "Toolsmith",
        "display_name": "Toolsmith",
        "model": DEFAULT_MAIN_MODEL,
        "allowed_tools": [
            "rumi_api",
            "todo",
            "subagent",
            "coding_file_read",
            "coding_file_search",
            "coding_file_list",
            "coding_file_write",
            "coding_file_create",
            "coding_file_patch",
            "coding_terminal_exec",
            "knowledge_search",
            "knowledge_create",
        ],
        "context_limit": 128000,
        "system_prompt": "If a missing tool or skill blocks progress, build the smallest viable one instead of stopping.",
    },
    {
        "agent_id": "scheduler",
        "role_key": "scheduler",
        "agent_name": "Scheduler",
        "display_name": "Scheduler",
        "model": DEFAULT_FAST_MODEL,
        "allowed_tools": ["rumi_api", "todo", "subagent"],
        "context_limit": 48000,
        "system_prompt": "Run loops on time. Stay quiet when nothing meaningful changed.",
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def current_model_allowlist() -> list[str]:
    allowlist: list[str] = []
    seen: set[str] = set()

    def append(candidate: Any) -> None:
        value = str(candidate or "").strip()
        if not value or value in seen:
            return
        seen.add(value)
        allowlist.append(value)

    for model_id in MODEL_ALLOWLIST:
        append(model_id)

    for provider_id in CATALOG_EXPANDED_MODEL_PROVIDERS:
        try:
            catalog_models = get_all_known_models(provider_id=provider_id)
        except Exception:
            continue
        for model in catalog_models:
            if not isinstance(model, dict):
                continue
            model_type = str(model.get("type") or "chat").strip().lower()
            if model_type not in {"", "chat", "reasoning"}:
                continue
            append(model.get("qualified_model_id") or model.get("id"))

    return allowlist


class MimoCodingCompanyRuntime:
    def __init__(self, pack_root: Path | None = None) -> None:
        self.source_pack_root = Path(__file__).resolve().parents[2]
        self.pack_root = pack_root or self.source_pack_root
        self.defaultspack_root = self.pack_root.parent / "defaultspack"
        self.schedules_dir = self._resolve_schedules_dir()
        os.environ.setdefault("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", str(self.schedules_dir))
        self.state_path = self._resolve_state_path()

    def manifest(self) -> dict[str, Any]:
        model_allowlist = current_model_allowlist()
        return {
            "profile_id": PROFILE_ID,
            "name": COMPANY_NAME,
            "conversation_kind": CONVERSATION_KIND,
            "non_stop": True,
            "can_run_24_7": True,
            "focus": "self_improving_coding",
            "shared_resources": {
                "tool_node": "defaultspack.tool",
                "settings_source": "defaultspack.frontend_settings",
                "browser_profile_id": "defaultspack-shared",
                "knowledge_store": "defaultspack.user_data.shared.knowledge",
                "knowledge_bundle_dir": str(self._knowledge_bundle_dir()),
            },
            "models": {
                "default_main_model": DEFAULT_MAIN_MODEL,
                "default_vision_model": DEFAULT_VISION_MODEL,
                "default_fast_model": DEFAULT_FAST_MODEL,
                "allowlist": list(model_allowlist),
                "utility_models": dict(UTILITY_MODELS),
            },
            "model_self_selection": {
                "enabled": True,
                "allowlist": list(model_allowlist),
                "default_reasoning_effort": "high",
                "max_switches_per_day": 48,
                "audit_required": False,
            },
            "self_improvement": {
                "enabled": True,
                "rule": "If a missing tool or skill blocks progress, create the smallest useful one instead of giving up.",
                "knowledge_tags": ["mimo-coding-company", "self-improvement", "repo-review", "qa"],
                "seed_task_templates": [
                    "Initial harness review",
                    "Provider and search improvement",
                    "Frontend QA swarm",
                    "Tool/skill gap closure",
                ],
            },
            "scheduler": {
                "enabled": True,
                "default_heartbeat_minutes": 30,
                "default_review_interval_minutes": 180,
                "default_qa_interval_minutes": 240,
                "supports": ["interval", "once"],
                "normal_status_silent": True,
            },
            "docker": {
                "preferred_image": "ubuntu:22.04",
                "display_sessions_supported": True,
                "browser_qa_strategy": "isolated_ubuntu_sessions_when_available",
                "default_worker_count": DEFAULT_DOCKER_WORKER_COUNT,
                "template_paths": {
                    "compose": str(self._docker_bundle_dir() / "compose.yaml"),
                    "dockerfile": str(self._docker_bundle_dir() / "Dockerfile"),
                    "entrypoint": str(self._docker_bundle_dir() / "worker-entrypoint.sh"),
                    "personas": str(self._docker_bundle_dir() / "personas.json"),
                },
                "personas": self._persona_specs(),
            },
            "tool_policy": {
                "allowlist": list(TOOL_ALLOWLIST),
                "denylist": [],
                "role_overrides": {
                    role["role_key"]: list(role["allowed_tools"])
                    for role in ROLE_DEFINITIONS
                },
            },
            "knowledge_bundle": {
                "directory": str(self._knowledge_bundle_dir()),
                "documents": [str(path) for path in self._knowledge_bundle_paths()],
            },
            "roles": deepcopy(ROLE_DEFINITIONS),
        }

    def status(self) -> dict[str, Any]:
        state = self._load_state()
        org_id = state.get("org_id")
        org = OrgManager().get_org(org_id) if org_id else None
        observability = self._sync_company_observability(state)
        company = self._sync_company_record({**state, "observability": observability})
        open_tasks = 0
        try:
            task_list = CompanyTaskStore().list(COMPANY_ID, limit=500, offset=0)
            tasks = task_list[0] if task_list is not None else []
            open_tasks = len([task for task in tasks if self._is_active_task(task)])
        except Exception:
            open_tasks = 0
        try:
            knowledge_total = int(KnowledgeStore().list_entries(limit=1, offset=0).get("total", 0))
        except Exception:
            knowledge_total = 0
        autonomy_board = deepcopy(state.get("autonomy_board") if isinstance(state.get("autonomy_board"), dict) else self._autonomy_board(state))
        qa_swarm_plan = deepcopy(state.get("qa_swarm_plan") if isinstance(state.get("qa_swarm_plan"), dict) else self._qa_swarm_plan(state))
        docker_swarm = self._docker_swarm_with_monitoring(
            deepcopy(
                state.get("docker_swarm")
                if isinstance(state.get("docker_swarm"), dict)
                else self._docker_swarm_state(workspace_root=state.get("workspace_root"))
            )
        )
        return {
            "profile_id": PROFILE_ID,
            "bootstrapped": bool(org),
            "org_id": org_id,
            "company_id": COMPANY_ID,
            "conversation_id": state.get("conversation_id"),
            "conversation_group_id": state.get("conversation_group_id"),
            "company": company,
            "org": org,
            "schedules": self._schedules_for_state(state),
            "harness": {
                "main_model": state.get("main_model") or DEFAULT_MAIN_MODEL,
                "vision_model": state.get("vision_model") or DEFAULT_VISION_MODEL,
                "fast_model": state.get("fast_model") or DEFAULT_FAST_MODEL,
                "max_tool_calls": self._max_tool_calls(state.get("max_tool_calls")),
                **self._workspace_metadata(
                    workspace_id=state.get("workspace_id"),
                    workspace_label=state.get("workspace_label"),
                    workspace_root=state.get("workspace_root"),
                ),
                "utility_models": deepcopy(state.get("utility_models") if isinstance(state.get("utility_models"), dict) else UTILITY_MODELS),
                "qa_targets": list(state.get("qa_targets") if isinstance(state.get("qa_targets"), list) else []),
                "docker_swarm": docker_swarm,
                "knowledge_bundle_paths": [str(path) for path in self._knowledge_bundle_paths()],
                "schedules_dir": str(self.schedules_dir),
                "seeded_task_ids": list(state.get("seeded_task_ids") if isinstance(state.get("seeded_task_ids"), list) else []),
                "stream_task_ids": deepcopy(state.get("stream_task_ids") if isinstance(state.get("stream_task_ids"), dict) else {}),
                "seeded_knowledge_ids": list(state.get("seeded_knowledge_ids") if isinstance(state.get("seeded_knowledge_ids"), list) else []),
                "open_task_count": open_tasks,
                "knowledge_entry_count": knowledge_total,
                "observability": observability,
                "autonomy_board": autonomy_board,
                "qa_swarm_plan": qa_swarm_plan,
            },
            "state": state,
            "manifest": self.manifest(),
            "updated_at": timestamp(),
        }

    @staticmethod
    def _max_tool_calls(value: int | str | None) -> int | None:
        if value in (None, ""):
            return None
        text = str(value).strip().lower()
        if text in {"none", "null", "unlimited", "infinite", "infinity"}:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return max(1, min(parsed, MAX_TOOL_CALLS_LIMIT))

    @staticmethod
    def _workspace_metadata(
        *,
        workspace_id: str | None = None,
        workspace_label: str | None = None,
        workspace_root: str | None = None,
    ) -> dict[str, str]:
        metadata: dict[str, str] = {}
        for key, value in (
            ("workspace_id", workspace_id),
            ("workspace_label", workspace_label),
            ("workspace_root", workspace_root),
        ):
            cleaned = str(value or "").strip()
            if cleaned:
                metadata[key] = cleaned
        return metadata

    def bootstrap(
        self,
        *,
        start_nonstop: bool = True,
        heartbeat_minutes: int = 30,
        review_interval_minutes: int = 180,
        qa_interval_minutes: int = 240,
        model: str | None = None,
        vision_model: str | None = None,
        fast_model: str | None = None,
        qa_targets: list[str] | None = None,
        docker_worker_count: int = DEFAULT_DOCKER_WORKER_COUNT,
        docker_personas: list[str] | None = None,
        docker_enabled: bool = True,
        max_tool_calls: int | None = None,
        workspace_id: str | None = None,
        workspace_label: str | None = None,
        workspace_root: str | None = None,
        seed_tasks: bool = True,
        seed_knowledge: bool = True,
        run_initial_review_now: bool = False,
    ) -> dict[str, Any]:
        main_model = self._allowed_model(model or DEFAULT_MAIN_MODEL)
        selected_vision_model = self._allowed_model(vision_model or DEFAULT_VISION_MODEL)
        selected_fast_model = self._allowed_model(fast_model or DEFAULT_FAST_MODEL)
        cleaned_targets = self._clean_targets(qa_targets)
        cleaned_personas = self._clean_personas(docker_personas)
        safe_docker_worker_count = max(0, min(int(docker_worker_count if docker_worker_count is not None else DEFAULT_DOCKER_WORKER_COUNT), 16))
        docker_swarm_enabled = bool(docker_enabled) and safe_docker_worker_count > 0
        workspace_metadata = self._workspace_metadata(
            workspace_id=workspace_id,
            workspace_label=workspace_label,
            workspace_root=workspace_root,
        )
        safe_max_tool_calls = self._max_tool_calls(max_tool_calls)

        state = self._load_state()
        paused_for_bootstrap = self._pause_mimo_loop_schedules_for_bootstrap() if start_nonstop else set()
        self._define_roles(main_model, selected_vision_model, selected_fast_model)
        org_id = self._ensure_org(state, main_model, selected_vision_model, selected_fast_model)
        conversation_id = self._ensure_conversation(
            state,
            model=main_model,
            workspace_metadata=workspace_metadata,
        )
        self._apply_model_preferences(main_model, selected_vision_model, selected_fast_model)
        state["org_id"] = org_id
        state["conversation_id"] = conversation_id
        state["conversation_group_id"] = self._conversation_group_id()
        state["main_model"] = main_model
        state["vision_model"] = selected_vision_model
        state["fast_model"] = selected_fast_model
        state["max_tool_calls"] = safe_max_tool_calls
        state.update(workspace_metadata)
        state["utility_models"] = {
            **dict(UTILITY_MODELS),
            "subagent_default": main_model,
            "model_router": main_model,
            "vision_ocr": selected_vision_model,
            "tool_selector": selected_fast_model,
            "prompt_compactor": selected_fast_model,
            "context_summarizer": selected_fast_model,
            "fast_reply": selected_fast_model,
        }
        state["qa_targets"] = cleaned_targets
        if docker_swarm_enabled:
            state["docker_swarm"] = self._docker_swarm_state(
                worker_count=safe_docker_worker_count,
                persona_ids=cleaned_personas,
                qa_targets=cleaned_targets,
                workspace_root=workspace_metadata.get("workspace_root"),
            )
        else:
            state["docker_swarm"] = self._docker_swarm_disabled_state(
                persona_ids=cleaned_personas,
                qa_targets=cleaned_targets,
                reason="non_docker_worker_mode",
            )
        state["autonomy_board"] = self._autonomy_board(state)
        state["qa_swarm_plan"] = self._qa_swarm_plan(state)
        company = self._sync_company_record(state)
        if seed_knowledge:
            state["seeded_knowledge_ids"] = self._seed_knowledge(state, company)
        if seed_tasks:
            state["seeded_task_ids"] = self._seed_tasks(state)
        if start_nonstop:
            kickoff_id = self._ensure_once_schedule(
                state,
                key="kickoff_review",
                run_at=_utc_now() + timedelta(minutes=1),
                message=self._kickoff_message(state),
                model=main_model,
                agent_id="project_manager",
                tools=["rumi_api", "todo", "subagent", "knowledge_search", "knowledge_create"],
                description="Initial MiMo coding company repo and harness review.",
            )
            self._ensure_interval_schedule(
                state,
                key="heartbeat",
                minutes=heartbeat_minutes,
                message=self._heartbeat_message(state),
                model=selected_fast_model,
                agent_id="scheduler",
                tools=["rumi_api", "todo", "subagent"],
                description="Keep the coding company alive and quiet on normal ticks.",
            )
            self._ensure_interval_schedule(
                state,
                key="improvement_loop",
                minutes=review_interval_minutes,
                message=self._improvement_message(state),
                model=main_model,
                agent_id="project_manager",
                tools=["rumi_api", "todo", "subagent", "knowledge_search", "knowledge_create", "web_search"],
                description="Self-improvement loop for coding, provider, and tooling work.",
            )
            self._ensure_interval_schedule(
                state,
                key="qa_loop",
                minutes=qa_interval_minutes,
                message=self._qa_message(state),
                model=selected_vision_model,
                agent_id="browser_qa",
                tools=[
                    "rumi_api",
                    "todo",
                    "browser_use",
                    "browser_computer",
                    "browser_companion",
                    "computer_use",
                    "desktop_list",
                    "desktop_create",
                    "desktop_frame",
                    "desktop_input",
                    "web_search",
                ],
                description="Persona-based browser/computer-use QA loop.",
            )
            self._pause_stale_mimo_schedules(state)
        state["last_bootstrapped_at"] = timestamp()
        self._save_state(state)
        if start_nonstop:
            self._resume_mimo_loop_schedules_after_bootstrap(state, paused_for_bootstrap)
            if run_initial_review_now and kickoff_id:
                try:
                    Scheduler().trigger_now(kickoff_id)
                except Exception:
                    pass
        return self.status()

    def _resolve_state_path(self) -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_MIMO_CODING_STATE_PATH", "").strip()
        if override:
            return Path(override)
        return self.pack_root / "user_data" / "shared" / "mimo_coding_company" / "state.json"

    def _resolve_schedules_dir(self) -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", "").strip()
        if override:
            return Path(override)
        runtime_root = self.pack_root.parent.parent if self.pack_root.parent.name == "ecosystem" else self.pack_root.parent
        return runtime_root / "user_data" / "shared" / "schedules"

    def _load_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, **state, "updated_at": timestamp()}
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _allowed_model(self, model: str) -> str:
        cleaned = str(model or "").strip()
        if cleaned not in current_model_allowlist():
            raise ValueError("model is not allowed for MiMo Coding Company: " + cleaned)
        return cleaned

    @staticmethod
    def _clean_targets(targets: list[str] | None) -> list[str]:
        cleaned: list[str] = []
        for item in targets or []:
            value = str(item or "").strip()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned

    @staticmethod
    def _managed_desktop_target_url(target: str) -> str:
        value = str(target or "").strip()
        parsed = urlsplit(value)
        host = (parsed.hostname or "").strip().lower()
        if parsed.scheme in {"http", "https"} and host in {"127.0.0.1", "localhost"} and parsed.port == 8766:
            hostname = parsed.hostname or "127.0.0.1"
            netloc = f"{hostname}:18766"
            return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return value

    def _persona_specs(self) -> list[dict[str, Any]]:
        path = self._docker_bundle_dir() / "personas.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                specs = [item for item in raw if isinstance(item, dict) and str(item.get("id") or "").strip()]
                if specs:
                    return specs
        except Exception:
            pass
        return deepcopy(DEFAULT_PERSONA_SPECS)

    def _clean_personas(self, persona_ids: list[str] | None) -> list[str]:
        available = {str(item.get("id")) for item in self._persona_specs()}
        cleaned: list[str] = []
        for item in persona_ids or []:
            value = str(item or "").strip()
            if value and value in available and value not in cleaned:
                cleaned.append(value)
        if cleaned:
            return cleaned
        return [str(item.get("id")) for item in self._persona_specs()]

    def _knowledge_bundle_dir(self) -> Path:
        primary = self.pack_root / "knowledge" / "mimo_coding_company"
        if primary.is_dir():
            return primary
        return self.source_pack_root / "knowledge" / "mimo_coding_company"

    def _knowledge_bundle_paths(self) -> list[Path]:
        directory = self._knowledge_bundle_dir()
        if not directory.is_dir():
            return []
        return sorted(path for path in directory.glob("*.md") if path.is_file())

    def _docker_bundle_dir(self) -> Path:
        primary = self.pack_root / "docker" / "mimo_coding_company"
        if primary.is_dir():
            return primary
        return self.source_pack_root / "docker" / "mimo_coding_company"

    def _docker_runtime_dir(self) -> Path:
        return self.state_path.parent / "docker_swarm"

    def _workspace_root(self) -> Path:
        try:
            return self.source_pack_root.parents[2]
        except IndexError:
            return self.source_pack_root

    def _docker_project_name(self) -> str:
        digest = hashlib.sha1(str(self.state_path).encode("utf-8")).hexdigest()[:10]
        return f"mimo-coding-{digest}"

    def _docker_worker_container_name(self, worker_id: str) -> str:
        cleaned_worker_id = str(worker_id or "").strip().replace("_", "-") or "worker"
        return f"{self._docker_project_name()}-{cleaned_worker_id}"

    @staticmethod
    def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _docker_swarm_state(
        self,
        *,
        worker_count: int = DEFAULT_DOCKER_WORKER_COUNT,
        persona_ids: list[str] | None = None,
        qa_targets: list[str] | None = None,
        workspace_root: str | None = None,
    ) -> dict[str, Any]:
        personas = self._clean_personas(persona_ids)
        targets = list(qa_targets or [])
        bundle_dir = self._docker_bundle_dir()
        workers: list[dict[str, Any]] = []
        for index in range(max(1, worker_count)):
            persona_id = personas[index % len(personas)] if personas else "first_time_user"
            target = targets[index % len(targets)] if targets else ""
            workers.append(
                {
                    "worker_id": f"worker-{index + 1}",
                    "container_name": f"mimo-qa-worker-{index + 1}",
                    "persona_id": persona_id,
                    "qa_target": target,
                    "display": True,
                }
            )
        compose_path = bundle_dir / "compose.yaml"
        swarm_state = {
            "enabled": True,
            "worker_count": max(1, worker_count),
            "personas": personas,
            "qa_targets": targets,
            "bundle_dir": str(bundle_dir),
            "template_compose_path": str(compose_path),
            "dockerfile_path": str(bundle_dir / "Dockerfile"),
            "entrypoint_path": str(bundle_dir / "worker-entrypoint.sh"),
            "workers": workers,
        }
        return self._materialize_docker_swarm_artifacts(swarm_state, workspace_root=workspace_root)

    def _docker_swarm_disabled_state(
        self,
        *,
        persona_ids: list[str] | None = None,
        qa_targets: list[str] | None = None,
        reason: str = "disabled",
    ) -> dict[str, Any]:
        return {
            "enabled": False,
            "worker_count": 0,
            "personas": self._clean_personas(persona_ids),
            "qa_targets": list(qa_targets or []),
            "workers": [],
            "runtime_dir": str(self._docker_runtime_dir()),
            "disabled_reason": reason,
            "monitoring": {
                "disabled": True,
                "reason": reason,
                "total_workers": 0,
                "reported_workers": 0,
                "browser_launch_attempted_workers": 0,
                "missing_status_workers": [],
                "workers": [],
            },
        }

    def _materialize_docker_swarm_artifacts(self, swarm_state: dict[str, Any], *, workspace_root: str | None = None) -> dict[str, Any]:
        runtime_dir = self._docker_runtime_dir()
        assignments_dir = runtime_dir / "assignments"
        status_dir = runtime_dir / "status"
        assignments_dir.mkdir(parents=True, exist_ok=True)
        status_dir.mkdir(parents=True, exist_ok=True)
        bundle_dir = Path(str(swarm_state.get("bundle_dir") or self._docker_bundle_dir()))
        mounted_workspace_root = Path(str(workspace_root)).expanduser().resolve() if str(workspace_root or "").strip() else self._workspace_root()
        project_name = self._docker_project_name()
        workers: list[dict[str, Any]] = []
        assignment_paths: dict[str, str] = {}
        status_paths: dict[str, str] = {}

        for raw_worker in swarm_state.get("workers", []) if isinstance(swarm_state.get("workers"), list) else []:
            if not isinstance(raw_worker, dict):
                continue
            worker = dict(raw_worker)
            worker_id = str(worker.get("worker_id") or "")
            if not worker_id:
                continue
            worker["container_name"] = self._docker_worker_container_name(worker_id)
            assignment_path = assignments_dir / f"{worker_id}.assignment.json"
            status_path = status_dir / f"{worker_id}.status.json"
            assignment = self._docker_worker_assignment(worker)
            self._write_json_file(assignment_path, assignment)
            worker["assignment_path"] = str(assignment_path)
            worker["status_path"] = str(status_path)
            workers.append(worker)
            assignment_paths[worker_id] = str(assignment_path)
            status_paths[worker_id] = str(status_path)

        generated_compose_path = runtime_dir / "compose.generated.yaml"
        generated_compose_path.parent.mkdir(parents=True, exist_ok=True)
        generated_compose_path.write_text(
            self._render_docker_swarm_compose(
                bundle_dir=bundle_dir,
                project_name=project_name,
                workspace_root=mounted_workspace_root,
                runtime_dir=runtime_dir,
                workers=workers,
            ),
            encoding="utf-8",
        )
        swarm_state["compose_path"] = str(generated_compose_path)
        swarm_state["runtime_dir"] = str(runtime_dir)
        swarm_state["assignment_dir"] = str(assignments_dir)
        swarm_state["status_dir"] = str(status_dir)
        swarm_state["project_name"] = project_name
        supervisor_path = runtime_dir / "supervisor.json"
        swarm_state["supervisor_path"] = str(supervisor_path)
        swarm_state["assignment_paths"] = assignment_paths
        swarm_state["status_paths"] = status_paths
        swarm_state["workers"] = workers
        quoted_compose_path = shlex.quote(str(generated_compose_path))
        quoted_supervisor_path = shlex.quote(str(supervisor_path))
        quoted_project_filter = shlex.quote("label=rumi.project_name=" + project_name)
        swarm_state["commands"] = {
            "up": f"docker compose --project-name {project_name} -f {quoted_compose_path} up --build -d",
            "logs": f"docker compose --project-name {project_name} -f {quoted_compose_path} logs -f",
            "ps": f"docker compose --project-name {project_name} -f {quoted_compose_path} ps",
            "down": f"docker compose --project-name {project_name} -f {quoted_compose_path} down -v",
            "docker_ps": f"docker ps --filter {quoted_project_filter}",
            "supervisor": f"cat {quoted_supervisor_path}",
        }
        return swarm_state

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _docker_swarm_with_monitoring(self, swarm_state: dict[str, Any]) -> dict[str, Any]:
        swarm = deepcopy(swarm_state) if isinstance(swarm_state, dict) else {}
        if swarm.get("enabled") is False:
            swarm["monitoring"] = {
                "disabled": True,
                "reason": str(swarm.get("disabled_reason") or "disabled"),
                "total_workers": 0,
                "reported_workers": 0,
                "browser_launch_attempted_workers": 0,
                "missing_status_workers": [],
                "workers": [],
            }
            return swarm
        monitoring = self._docker_swarm_monitoring(swarm)
        swarm["monitoring"] = monitoring
        supervisor_path_text = str(swarm.get("supervisor_path") or self._docker_runtime_dir() / "supervisor.json")
        swarm["supervisor_path"] = supervisor_path_text
        self._write_json_file(Path(supervisor_path_text), self._docker_supervisor_payload(swarm, monitoring))
        return swarm

    def _docker_swarm_monitoring(self, swarm_state: dict[str, Any]) -> dict[str, Any]:
        workers = swarm_state.get("workers") if isinstance(swarm_state.get("workers"), list) else []
        observed_workers: list[dict[str, Any]] = []
        reported_workers = 0
        browser_launch_attempted_workers = 0
        missing_status_workers: list[str] = []
        for raw_worker in workers:
            if not isinstance(raw_worker, dict):
                continue
            worker = dict(raw_worker)
            worker_id = str(worker.get("worker_id") or "")
            status_path_text = str(worker.get("status_path") or "")
            status_path = Path(status_path_text) if status_path_text else None
            status_payload = self._read_json_file(status_path) if status_path is not None else {}
            reported = bool(status_payload)
            browser_launch = status_payload.get("browser_launch") if isinstance(status_payload.get("browser_launch"), dict) else {}
            browser_attempted = bool(browser_launch.get("attempted"))
            assignment = status_payload.get("assignment") if isinstance(status_payload.get("assignment"), dict) else {}
            assignment_match = False
            if assignment:
                assignment_match = (
                    str(assignment.get("worker_id") or "") == worker_id
                    and str(assignment.get("persona_id") or "") == str(worker.get("persona_id") or "")
                )
            if reported:
                reported_workers += 1
            else:
                missing_status_workers.append(worker_id)
            if browser_attempted:
                browser_launch_attempted_workers += 1
            observed_workers.append(
                {
                    "worker_id": worker_id,
                    "persona_id": str(worker.get("persona_id") or ""),
                    "qa_target": str(worker.get("qa_target") or ""),
                    "status_path": status_path_text,
                    "reported": reported,
                    "started_at": str(status_payload.get("started_at") or ""),
                    "browser_launch_attempted": browser_attempted,
                    "assignment_match": assignment_match,
                    "display": str(status_payload.get("display") or worker.get("display") or ""),
                }
            )
        return {
            "total_workers": len(observed_workers),
            "reported_workers": reported_workers,
            "browser_launch_attempted_workers": browser_launch_attempted_workers,
            "missing_status_workers": missing_status_workers,
            "workers": observed_workers,
        }

    def _docker_swarm_monitoring_summary(self, state: dict[str, Any]) -> str:
        docker_swarm = self._docker_swarm_with_monitoring(
            deepcopy(state.get("docker_swarm") if isinstance(state.get("docker_swarm"), dict) else self._docker_swarm_state())
        )
        if docker_swarm.get("enabled") is False:
            return ""
        monitoring = docker_swarm.get("monitoring") if isinstance(docker_swarm.get("monitoring"), dict) else {}
        try:
            total_workers = int(monitoring.get("total_workers") or 0)
            reported_workers = int(monitoring.get("reported_workers") or 0)
            browser_workers = int(monitoring.get("browser_launch_attempted_workers") or 0)
        except (TypeError, ValueError):
            return ""
        if total_workers <= 0:
            return ""
        summary = (
            f"Swarm monitor: {reported_workers}/{total_workers} workers reported status; "
            f"{browser_workers}/{total_workers} attempted browser launch."
        )
        missing = monitoring.get("missing_status_workers") if isinstance(monitoring.get("missing_status_workers"), list) else []
        if missing:
            summary += " Missing status: " + ", ".join(str(item) for item in missing if str(item).strip()) + "."
        mismatched = [
            str(item.get("worker_id") or "")
            for item in (monitoring.get("workers") if isinstance(monitoring.get("workers"), list) else [])
            if isinstance(item, dict) and item.get("reported") and item.get("assignment_match") is False
        ]
        if mismatched:
            summary += " Assignment mismatch: " + ", ".join(item for item in mismatched if item) + "."
        return summary

    def _docker_supervisor_payload(self, swarm_state: dict[str, Any], monitoring: dict[str, Any]) -> dict[str, Any]:
        workers = swarm_state.get("workers") if isinstance(swarm_state.get("workers"), list) else []
        return {
            "company_id": COMPANY_ID,
            "project_name": str(swarm_state.get("project_name") or self._docker_project_name()),
            "runtime_dir": str(swarm_state.get("runtime_dir") or self._docker_runtime_dir()),
            "compose_path": str(swarm_state.get("compose_path") or ""),
            "assignment_dir": str(swarm_state.get("assignment_dir") or ""),
            "status_dir": str(swarm_state.get("status_dir") or ""),
            "commands": deepcopy(swarm_state.get("commands") if isinstance(swarm_state.get("commands"), dict) else {}),
            "worker_count": int(swarm_state.get("worker_count") or len(workers)),
            "personas": list(swarm_state.get("personas") if isinstance(swarm_state.get("personas"), list) else []),
            "qa_targets": list(swarm_state.get("qa_targets") if isinstance(swarm_state.get("qa_targets"), list) else []),
            "workers": [
                {
                    "worker_id": str(worker.get("worker_id") or ""),
                    "container_name": str(worker.get("container_name") or ""),
                    "persona_id": str(worker.get("persona_id") or ""),
                    "qa_target": str(worker.get("qa_target") or ""),
                    "assignment_path": str(worker.get("assignment_path") or ""),
                    "status_path": str(worker.get("status_path") or ""),
                }
                for worker in workers
                if isinstance(worker, dict)
            ],
            "monitoring": deepcopy(monitoring),
            "refreshed_at": timestamp(),
        }

    def _docker_worker_assignment(self, worker: dict[str, Any]) -> dict[str, Any]:
        persona_id = str(worker.get("persona_id") or "first_time_user")
        persona_specs = {str(item.get("id")): item for item in self._persona_specs()}
        persona_spec = persona_specs.get(persona_id, {})
        mission = PERSONA_MISSIONS.get(persona_id, {})
        return {
            "worker_id": str(worker.get("worker_id") or ""),
            "container_name": str(worker.get("container_name") or ""),
            "persona_id": persona_id,
            "persona_label": str(persona_spec.get("label") or persona_id),
            "qa_target": str(worker.get("qa_target") or ""),
            "mission": str(mission.get("mission") or str(persona_spec.get("goal") or "")),
            "probe_areas": list(mission.get("probe_areas") or []),
            "prompt_style": "Keep prompts short, concrete, and evidence-first. For desktop/sandbox tools, rely on the server-provided principal context; do not add payload owner_id as proof of access.",
            "reporting_policy": "Report only evidence-backed bugs with exact repro steps or screenshots.",
            "tools_hint": ["browser_use", "browser_companion", "computer_use"],
            "desktop_tools_hint": ["desktop_list", "desktop_create", "desktop_frame", "desktop_input"],
            "model_hint": DEFAULT_VISION_MODEL,
        }

    @staticmethod
    def _yaml_quote(value: Any) -> str:
        return json.dumps("" if value is None else str(value))

    def _render_docker_swarm_compose(
        self,
        *,
        bundle_dir: Path,
        project_name: str,
        workspace_root: Path,
        runtime_dir: Path,
        workers: list[dict[str, Any]],
    ) -> str:
        lines = ["services:"]
        for worker in workers:
            worker_id = str(worker.get("worker_id") or "")
            service_id = worker_id.replace("_", "-")
            lines.extend(
                [
                    f"  {service_id}:",
                    "    build:",
                    f"      context: {self._yaml_quote(bundle_dir)}",
                    "      dockerfile: \"Dockerfile\"",
                    "    image: \"rumiai/mimo-coding-company-worker:latest\"",
                    f"    container_name: {self._yaml_quote(worker.get('container_name') or service_id)}",
                    "    labels:",
                    f"      rumi.company_id: {self._yaml_quote(COMPANY_ID)}",
                    f"      rumi.project_name: {self._yaml_quote(project_name)}",
                    f"      rumi.worker_id: {self._yaml_quote(worker_id)}",
                    f"      rumi.persona_id: {self._yaml_quote(worker.get('persona_id') or '')}",
                    "    environment:",
                    "      DISPLAY: \":99\"",
                    "      WORKER_ROLE: \"browser_qa\"",
                    f"      START_URL: {self._yaml_quote(worker.get('qa_target') or '')}",
                    f"      WORKER_ID: {self._yaml_quote(worker_id)}",
                    f"      WORKER_PERSONA_ID: {self._yaml_quote(worker.get('persona_id') or '')}",
                    f"      WORKER_ASSIGNMENT_FILE: {self._yaml_quote('/rumi-swarm/assignments/' + worker_id + '.assignment.json')}",
                    f"      WORKER_STATUS_FILE: {self._yaml_quote('/rumi-swarm/status/' + worker_id + '.status.json')}",
                    "    working_dir: \"/workspace\"",
                    "    volumes:",
                    f"      - {self._yaml_quote(str(workspace_root) + ':/workspace')}",
                    f"      - {self._yaml_quote(str(runtime_dir) + ':/rumi-swarm')}",
                    "    shm_size: \"1gb\"",
                    "    tty: true",
                    "    stdin_open: true",
                ]
            )
        return "\n".join(lines) + "\n"

    def _conversation_group_id(self) -> str:
        return "company:" + COMPANY_ID

    def _define_roles(self, main_model: str, vision_model: str, fast_model: str) -> None:
        registry = RoleRegistry()
        for role in self._resolved_roles(main_model, vision_model, fast_model):
            registry.define_role(
                role_key=role["role_key"],
                display_name=role["display_name"],
                system_prompt=role["system_prompt"],
                allowed_tools=role["allowed_tools"],
                context_limit=role["context_limit"],
            )

    def _resolved_roles(self, main_model: str, vision_model: str, fast_model: str) -> list[dict[str, Any]]:
        roles: list[dict[str, Any]] = []
        for role in ROLE_DEFINITIONS:
            item = dict(role)
            if item["agent_id"] == "browser_qa":
                item["model"] = vision_model
            elif item["agent_id"] == "scheduler":
                item["model"] = fast_model
            else:
                item["model"] = main_model
            roles.append(item)
        return roles

    def _ensure_org(self, state: dict[str, Any], main_model: str, vision_model: str, fast_model: str) -> str:
        manager = OrgManager()
        org_id = state.get("org_id")
        org = manager.get_org(org_id) if org_id else None
        if org is None:
            org = manager.create_org(
                COMPANY_NAME,
                COMPANY_DESCRIPTION,
                created_by=PROFILE_ID,
            )
            org_id = org["org_id"]
        for role in self._resolved_roles(main_model, vision_model, fast_model):
            manager.add_member(
                org_id,
                role["agent_id"],
                role["agent_name"],
                role["role_key"],
                role.get("model") or main_model,
            )
        return str(org_id)

    def _ensure_conversation(
        self,
        state: dict[str, Any],
        *,
        model: str,
        workspace_metadata: dict[str, str] | None = None,
    ) -> str:
        from domain.chat.store import ChatStore

        workspace_metadata = dict(workspace_metadata or {})
        store = ChatStore()
        conversation_id = state.get("conversation_id")
        if conversation_id and store.get_conversation(conversation_id):
            conversation = store.get_conversation(conversation_id)
            metadata = conversation.get("metadata") if isinstance(conversation, dict) else {}
            if not isinstance(metadata, dict):
                metadata = {}
            store.update_conversation(
                conversation_id,
                {
                    "group_id": self._conversation_group_id(),
                    "metadata": {
                        **metadata,
                        "profile_id": PROFILE_ID,
                        "client_manager_agent_id": "client_manager",
                        "company_id": COMPANY_ID,
                        **workspace_metadata,
                    },
                },
            )
            return str(conversation_id)
        conversation = store.create_conversation(
            model=model,
            system_prompt_id="mimo_coding_company",
            agent_id="client_manager",
            tags=["mimo-coding-company", "company", "coding", "self-improving"],
            conversation_kind=CONVERSATION_KIND,
            group_id=self._conversation_group_id(),
            metadata={
                "profile_id": PROFILE_ID,
                "client_manager_agent_id": "client_manager",
                "company_id": COMPANY_ID,
                **workspace_metadata,
            },
        )
        store.update_conversation(conversation["id"], {"title": "MiMo Coding Company"})
        return str(conversation["id"])

    def _apply_model_preferences(self, main_model: str, vision_model: str, fast_model: str) -> None:
        service = ModelRuntimeSettingsService(pack_root=self.defaultspack_root)
        service.update_settings(
            {
                "preferred_model": main_model,
                "utility_models": {
                    **dict(UTILITY_MODELS),
                    "subagent_default": main_model,
                    "model_router": main_model,
                    "vision_ocr": vision_model,
                    "tool_selector": fast_model,
                    "prompt_compactor": fast_model,
                    "context_summarizer": fast_model,
                    "fast_reply": fast_model,
                },
            }
        )

    def _sync_company_record(self, state: dict[str, Any]) -> dict[str, Any] | None:
        try:
            docker_swarm = self._docker_swarm_with_monitoring(
                deepcopy(state.get("docker_swarm") if isinstance(state.get("docker_swarm"), dict) else self._docker_swarm_state())
            )
            metadata = {
                "profile_id": PROFILE_ID,
                "conversation_group_id": self._conversation_group_id(),
                "conversation_id": state.get("conversation_id"),
                "legacy_org_id": state.get("org_id"),
                "main_model": state.get("main_model") or DEFAULT_MAIN_MODEL,
                "vision_model": state.get("vision_model") or DEFAULT_VISION_MODEL,
                "fast_model": state.get("fast_model") or DEFAULT_FAST_MODEL,
                "max_tool_calls": self._max_tool_calls(state.get("max_tool_calls")),
                **self._workspace_metadata(
                    workspace_id=state.get("workspace_id"),
                    workspace_label=state.get("workspace_label"),
                    workspace_root=state.get("workspace_root"),
                ),
                "self_improving": True,
                "qa_targets": list(state.get("qa_targets") if isinstance(state.get("qa_targets"), list) else []),
                "docker_swarm": docker_swarm,
                "knowledge_bundle_paths": [str(path) for path in self._knowledge_bundle_paths()],
                "autonomy_board": deepcopy(state.get("autonomy_board") if isinstance(state.get("autonomy_board"), dict) else self._autonomy_board(state)),
                "qa_swarm_plan": deepcopy(state.get("qa_swarm_plan") if isinstance(state.get("qa_swarm_plan"), dict) else self._qa_swarm_plan(state)),
                "stream_task_ids": deepcopy(state.get("stream_task_ids") if isinstance(state.get("stream_task_ids"), dict) else {}),
            }
            if isinstance(state.get("observability"), dict):
                metadata["observability"] = deepcopy(state["observability"])
            return CompanyService().store.ensure_company(
                company_id=COMPANY_ID,
                name=COMPANY_NAME,
                description=COMPANY_DESCRIPTION,
                agents=self._resolved_roles(
                    state.get("main_model") or DEFAULT_MAIN_MODEL,
                    state.get("vision_model") or DEFAULT_VISION_MODEL,
                    state.get("fast_model") or DEFAULT_FAST_MODEL,
                ),
                metadata=metadata,
                conversation_group_id=self._conversation_group_id(),
            )
        except Exception:
            return None

    def _knowledge_seed_documents(self) -> list[tuple[str, str, str]]:
        docs: list[tuple[str, str, str]] = []
        for path in self._knowledge_bundle_paths():
            try:
                body = path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            title = path.stem.replace("_", " ").replace("-", " ").title()
            first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
            if first_line.startswith("#"):
                title = first_line.lstrip("#").strip() or title
            docs.append((title, body + "\n", str(path)))
        if docs:
            return docs
        return [(filename, body, filename) for filename, body in FALLBACK_KNOWLEDGE_DOCS]

    def _seed_knowledge(self, state: dict[str, Any], company: dict[str, Any] | None) -> list[str]:
        existing = list(state.get("seeded_knowledge_ids") if isinstance(state.get("seeded_knowledge_ids"), list) else [])
        if existing:
            return existing
        store = KnowledgeStore()
        entries = self._knowledge_seed_documents()
        created_ids: list[str] = []
        for title, body, source_path in entries:
            entry = store.create(
                body if body.lstrip().startswith("#") else f"# {title}\n\n{body}\n",
                metadata={
                    "profile_id": PROFILE_ID,
                    "company_id": COMPANY_ID,
                    "tags": ["mimo-coding-company", "self-improvement"],
                    "title": title,
                    "conversation_id": state.get("conversation_id"),
                    "company_name": company.get("name") if isinstance(company, dict) else COMPANY_NAME,
                    "source_path": source_path,
                },
            )
            created_ids.append(str(entry.get("id")))
        return created_ids

    def _seed_tasks(self, state: dict[str, Any]) -> list[str]:
        store = CompanyTaskStore()
        listed = store.list(COMPANY_ID, limit=500, offset=0)
        tasks = listed[0] if listed is not None else []
        tasks_by_stream: dict[str, list[dict[str, Any]]] = {}
        for task in tasks:
            if not isinstance(task, dict):
                continue
            metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
            stream_id = str(metadata.get("stream_id") or "").strip()
            if not stream_id:
                continue
            tasks_by_stream.setdefault(stream_id, []).append(task)

        task_ids: list[str] = []
        stream_task_ids: dict[str, str] = {}
        specs = [
            {
                "title": stream["title"],
                "description": stream["description"],
                "target_agent_ids": list(stream["target_agent_ids"]),
                "source": "bootstrap",
                "stream_id": stream["id"],
            }
            for stream in IMPROVEMENT_STREAMS
        ]
        for spec in specs:
            stream_id = str(spec.get("stream_id") or "")
            stream_tasks = tasks_by_stream.get(stream_id, [])
            active = next((task for task in stream_tasks if self._is_active_task(task)), None)
            metadata = {
                "profile_id": PROFILE_ID,
                "company_id": COMPANY_ID,
                "conversation_id": state.get("conversation_id"),
                "stream_id": stream_id,
            }
            if active:
                updates: dict[str, Any] = {}
                if active.get("title") != spec["title"]:
                    updates["title"] = spec["title"]
                if active.get("description") != spec["description"]:
                    updates["description"] = spec["description"]
                if active.get("target_agent_ids") != spec["target_agent_ids"]:
                    updates["target_agent_ids"] = list(spec["target_agent_ids"])
                current_metadata = active.get("metadata") if isinstance(active.get("metadata"), dict) else {}
                merged_metadata = {**current_metadata, **metadata}
                if current_metadata != merged_metadata:
                    updates["metadata"] = merged_metadata
                if updates:
                    active = store.update(COMPANY_ID, str(active.get("id")), updates) or active
                if active.get("id"):
                    active_id = str(active["id"])
                    task_ids.append(active_id)
                    stream_task_ids[stream_id] = active_id
                continue

            created = store.create(
                COMPANY_ID,
                title=spec["title"],
                description=spec["description"],
                target_agent_ids=spec["target_agent_ids"],
                source=spec["source"],
                metadata=metadata,
            )
            if isinstance(created, dict) and created.get("id"):
                created_id = str(created["id"])
                task_ids.append(created_id)
                stream_task_ids[stream_id] = created_id
        state["stream_task_ids"] = stream_task_ids
        return task_ids

    @staticmethod
    def _is_active_task(task: dict[str, Any] | None) -> bool:
        if not isinstance(task, dict):
            return False
        status = str(task.get("status") or "").strip().lower()
        if not status:
            return True
        return status not in TERMINAL_TASK_STATUSES

    def _sync_company_observability(self, state: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "status": "ok",
            "company_id": COMPANY_ID,
            "channel_id": "ops-company",
            "team_workspace": {"synced_messages": 0},
            "schedule_history": {"checked": 0, "latest": [], "signals": []},
            "subagents": {"checked": 0, "unanswered_count": 0, "unanswered": []},
            "desktop_monitoring": {
                "surface": "desktops",
                "expected_api": "GET /api/desktops",
                "status": "unknown",
            },
        }
        try:
            runtime_store = CompanyRuntimeStore()
            known_sync_keys = self._company_runtime_sync_keys(runtime_store)
            synced = 0
            scheduler = Scheduler()
            for observed_schedule in self._mimo_company_observability_schedules(state, scheduler):
                schedule_id = observed_schedule["schedule_id"]
                loop_key = observed_schedule["loop_key"]
                schedule = observed_schedule.get("schedule")
                history = scheduler.get_history(schedule_id, limit=MIMO_OBSERVABILITY_HISTORY_LIMIT).get("entries", [])
                for entry in reversed([item for item in history if isinstance(item, dict)]):
                    summary["schedule_history"]["checked"] += 1
                    latest = self._schedule_history_observation(loop_key, schedule, entry)
                    summary["schedule_history"]["latest"].append(latest)
                    if latest.get("signal"):
                        summary["schedule_history"]["signals"].append(latest)
                    sync_key = "schedule:" + str(entry.get("execution_id") or "").strip()
                    if sync_key == "schedule:" or sync_key in known_sync_keys:
                        continue
                    runtime_store.add_message(
                        COMPANY_ID,
                        channel_id="ops-company",
                        sender_id=str((schedule or {}).get("task", {}).get("agent_id") or "scheduler"),
                        content=self._schedule_history_message(loop_key, schedule, entry),
                        metadata={
                            "sync_source": "mimo_schedule_history",
                            "sync_key": sync_key,
                            "loop_key": loop_key,
                            "schedule_id": str(entry.get("schedule_id") or schedule_id),
                            "execution_id": str(entry.get("execution_id") or ""),
                            "status": str(entry.get("status") or ""),
                            "signal": latest.get("signal"),
                        },
                    )
                    known_sync_keys.add(sync_key)
                    synced += 1

            subagent_gaps = self._subagent_reply_gaps(state)
            summary["subagents"]["checked"] = len(subagent_gaps.get("checked_ids", []))
            summary["subagents"]["repaired"] = subagent_gaps.get("repaired", [])
            summary["subagents"]["repaired_count"] = len(summary["subagents"]["repaired"])
            summary["subagents"]["unanswered"] = subagent_gaps.get("unanswered", [])
            summary["subagents"]["unanswered_count"] = len(summary["subagents"]["unanswered"])
            resolved_gap_messages = self._resolve_stale_subagent_gap_messages(runtime_store, state, subagent_gaps)
            summary["subagents"]["resolved_messages"] = resolved_gap_messages[:10]
            summary["subagents"]["resolved_message_count"] = len(resolved_gap_messages)
            for gap in summary["subagents"]["unanswered"]:
                sync_key = "subagent_gap:" + str(gap.get("child_conversation_id") or "")
                if sync_key in known_sync_keys:
                    continue
                runtime_store.add_message(
                    COMPANY_ID,
                    channel_id="ops-company",
                    sender_id="scheduler",
                    content=self._subagent_gap_message(gap),
                    metadata={
                        "sync_source": "mimo_subagent_monitor",
                        "sync_key": sync_key,
                        "child_conversation_id": gap.get("child_conversation_id"),
                        "parent_conversation_id": state.get("conversation_id"),
                        "signal": "subagent_unanswered",
                    },
                )
                known_sync_keys.add(sync_key)
                synced += 1

            desktop_monitoring = self._desktop_monitoring_observation()
            summary["desktop_monitoring"] = desktop_monitoring
            desktop_signal = str(desktop_monitoring.get("signal") or "").strip()
            if desktop_signal:
                sync_key = "desktop_monitor:" + desktop_signal + ":" + str(desktop_monitoring.get("desktop_count") or 0)
                if sync_key not in known_sync_keys:
                    runtime_store.add_message(
                        COMPANY_ID,
                        channel_id="ops-company",
                        sender_id="scheduler",
                        content=self._desktop_monitoring_message(desktop_monitoring),
                        metadata={
                            "sync_source": "mimo_desktop_monitor",
                            "sync_key": sync_key,
                            "signal": desktop_signal,
                            "surface": "desktops",
                            "desktop_count": desktop_monitoring.get("desktop_count"),
                        },
                    )
                    known_sync_keys.add(sync_key)
                    synced += 1

            stats = runtime_store.stats(COMPANY_ID)
            summary["team_workspace"] = {
                "synced_messages": synced,
                "messages": stats.get("messages", 0),
                "tasks": stats.get("tasks", 0),
                "runs": stats.get("runs", 0),
                "threads": stats.get("threads", 0),
            }
            summary["schedule_history"]["latest"] = summary["schedule_history"]["latest"][-12:]
            summary["schedule_history"]["signals"] = summary["schedule_history"]["signals"][-12:]
            summary["subagents"]["unanswered"] = summary["subagents"]["unanswered"][:10]
            return summary
        except Exception as exc:
            summary["status"] = "error"
            summary["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            return summary

    def _mimo_company_observability_schedules(self, state: dict[str, Any], scheduler: Scheduler) -> list[dict[str, Any]]:
        schedules: list[dict[str, Any]] = []
        seen_schedule_ids: set[str] = set()

        def add_schedule(raw_schedule_id: Any, *, loop_key: str = "", schedule: dict[str, Any] | None = None) -> None:
            schedule_id = str(raw_schedule_id or "").strip()
            if not schedule_id or schedule_id in seen_schedule_ids:
                return
            seen_schedule_ids.add(schedule_id)
            current = schedule if isinstance(schedule, dict) else scheduler.get_schedule(schedule_id)
            schedules.append(
                {
                    "schedule_id": schedule_id,
                    "loop_key": self._mimo_company_observability_loop_key(current, loop_key),
                    "schedule": current if isinstance(current, dict) else None,
                }
            )

        schedule_ids = state.get("schedule_ids") if isinstance(state.get("schedule_ids"), dict) else {}
        for loop_key, schedule_id in schedule_ids.items():
            add_schedule(schedule_id, loop_key=str(loop_key or "").strip())

        for schedule in scheduler.list_schedules():
            if not isinstance(schedule, dict):
                continue
            if not self._is_mimo_company_observability_schedule(schedule, state):
                continue
            add_schedule(schedule.get("id"), schedule=schedule)
        return schedules

    @staticmethod
    def _mimo_company_observability_loop_key(schedule: dict[str, Any] | None, fallback: str = "") -> str:
        cleaned_fallback = str(fallback or "").strip()
        if cleaned_fallback:
            return cleaned_fallback
        task = schedule.get("task") if isinstance(schedule, dict) and isinstance(schedule.get("task"), dict) else {}
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        loop_key = str(metadata.get("loop_key") or "").strip()
        if loop_key:
            return loop_key
        agent_id = str(task.get("agent_id") or "").strip()
        return agent_id or "schedule"

    def _is_mimo_company_observability_schedule(self, schedule: dict[str, Any], state: dict[str, Any]) -> bool:
        task = schedule.get("task") if isinstance(schedule.get("task"), dict) else {}
        task_metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        schedule_metadata = schedule.get("metadata") if isinstance(schedule.get("metadata"), dict) else {}
        metadata = {**schedule_metadata, **task_metadata}
        policy = task.get("tool_policy") if isinstance(task.get("tool_policy"), dict) else {}

        company_id = str(metadata.get("company_id") or task.get("company_id") or policy.get("company_id") or "").strip()
        if company_id == COMPANY_ID:
            return True

        profile_id = str(metadata.get("profile_id") or task.get("profile_id") or policy.get("profile_id") or "").strip()
        if profile_id == PROFILE_ID:
            return True

        state_conversation_id = str(state.get("conversation_id") or "").strip()
        conversation_ids = {
            str(task.get("conversation_id") or "").strip(),
            str(metadata.get("conversation_id") or "").strip(),
        }
        if state_conversation_id and state_conversation_id in conversation_ids:
            return True

        expected_group_id = str(state.get("conversation_group_id") or self._conversation_group_id()).strip()
        group_ids = {
            str(metadata.get("conversation_group_id") or "").strip(),
            str(metadata.get("group_id") or "").strip(),
            str(metadata.get("group") or "").strip(),
            str(task.get("conversation_group_id") or "").strip(),
            str(task.get("group_id") or "").strip(),
            str(task.get("group") or "").strip(),
        }
        return bool(expected_group_id and expected_group_id in group_ids)

    @staticmethod
    def _company_runtime_sync_keys(runtime_store: CompanyRuntimeStore) -> set[str]:
        try:
            messages, _total = runtime_store.list_messages(COMPANY_ID, limit=1000, offset=0, order="desc")
        except Exception:
            return set()
        keys: set[str] = set()
        for message in messages:
            metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            sync_key = str(metadata.get("sync_key") or "").strip()
            if sync_key:
                keys.add(sync_key)
        return keys

    @staticmethod
    def _resolve_stale_subagent_gap_messages(
        runtime_store: CompanyRuntimeStore,
        state: dict[str, Any],
        subagent_gaps: dict[str, Any],
    ) -> list[dict[str, str]]:
        checked_ids = {str(item) for item in subagent_gaps.get("checked_ids", []) if str(item or "").strip()}
        unanswered_ids = {
            str(item.get("child_conversation_id") or "")
            for item in subagent_gaps.get("unanswered", [])
            if isinstance(item, dict) and str(item.get("child_conversation_id") or "").strip()
        }
        if not checked_ids:
            return []
        parent_conversation_id = str(state.get("conversation_id") or "").strip()
        try:
            messages, _total = runtime_store.list_messages(COMPANY_ID, limit=1000, offset=0, order="desc")
        except Exception:
            return []
        resolved: list[dict[str, str]] = []
        for message in messages:
            metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            if metadata.get("sync_source") != "mimo_subagent_monitor":
                continue
            if metadata.get("signal") != "subagent_unanswered":
                continue
            child_id = str(metadata.get("child_conversation_id") or "").strip()
            if not child_id or child_id not in checked_ids or child_id in unanswered_ids:
                continue
            message_parent_id = str(metadata.get("parent_conversation_id") or "").strip()
            if parent_conversation_id and message_parent_id and message_parent_id != parent_conversation_id:
                continue
            updated = runtime_store.update_message(
                str(message.get("message_id") or message.get("id") or ""),
                {
                    "content": MimoCodingCompanyRuntime._subagent_gap_resolved_message(child_id),
                    "metadata": {
                        "signal": "subagent_repaired",
                        "previous_signal": "subagent_unanswered",
                        "resolved": True,
                        "resolved_at": timestamp(),
                        "resolved_reason": "child_conversation_repaired",
                    },
                },
                company_id=COMPANY_ID,
            )
            if updated is not None:
                resolved.append(
                    {
                        "message_id": str(updated.get("message_id") or ""),
                        "child_conversation_id": child_id,
                    }
                )
        return resolved

    @staticmethod
    def _schedule_history_observation(loop_key: str, schedule: dict[str, Any] | None, entry: dict[str, Any]) -> dict[str, Any]:
        text = (str(entry.get("error") or "") + "\n" + str(entry.get("result") or "")).lower()
        signal = ""
        if "subagent" in text and ("timeout" in text or "timed out" in text):
            signal = "subagent_timeout"
        elif "handler execution failed" in text or ("rumi_api" in text and "fail" in text):
            signal = "tool_handler_failure"
        elif "browser_companion" in text or "0 clients paired" in text:
            signal = "browser_companion_unpaired"
        elif (
            ("<tool_call" in text and "<function=" in text)
            or ("<tool_use" in text and '"name"' in text)
        ):
            signal = "text_tool_call_not_executed"
        elif "approval" in text or "permission" in text:
            signal = "approval_wait"
        elif str(entry.get("status") or "").lower() == "error" or entry.get("error"):
            signal = "schedule_error"
        return {
            "loop_key": loop_key,
            "schedule_id": str(entry.get("schedule_id") or (schedule or {}).get("id") or ""),
            "schedule_name": str((schedule or {}).get("name") or ""),
            "execution_id": str(entry.get("execution_id") or ""),
            "status": str(entry.get("status") or ""),
            "trigger": str(entry.get("trigger") or ""),
            "started_at": entry.get("started_at"),
            "completed_at": entry.get("completed_at"),
            "signal": signal,
        }

    @staticmethod
    def _schedule_history_message(loop_key: str, schedule: dict[str, Any] | None, entry: dict[str, Any]) -> str:
        status = str(entry.get("status") or "unknown")
        name = str((schedule or {}).get("name") or loop_key)
        body = str(entry.get("error") or entry.get("result") or "").strip()
        if len(body) > 2400:
            body = body[:2400].rstrip() + "\n\n... truncated by MiMo Team Workspace sync ..."
        lines = [
            f"**MiMo schedule {status}: {name}**",
            f"- Loop: `{loop_key}`",
            f"- Schedule: `{entry.get('schedule_id') or (schedule or {}).get('id') or ''}`",
            f"- Execution: `{entry.get('execution_id') or ''}`",
            f"- Trigger: `{entry.get('trigger') or ''}`",
            f"- Started: `{entry.get('started_at') or ''}`",
            f"- Completed: `{entry.get('completed_at') or ''}`",
        ]
        if body:
            lines.extend(["", body])
        return "\n".join(lines)

    def _subagent_reply_gaps(self, state: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(state.get("conversation_id") or "").strip()
        if not conversation_id:
            return {"checked_ids": [], "unanswered": [], "repaired": []}
        try:
            from domain.chat.store import ChatStore
            from domain.chat.subagent_durability import (
                has_completed_assistant_text,
                is_running_subagent_durable_draft,
                mark_subagent_child_failed,
            )

            store = ChatStore()
            parent = store.get_conversation(conversation_id) or {}
            child_ids = [
                str(item)
                for item in parent.get("child_conversation_ids", [])
                if str(item or "").strip()
            ]
            unanswered: list[dict[str, Any]] = []
            repaired: list[str] = []
            for child_id in child_ids:
                child = store.get_conversation(child_id) or {}
                if str(child.get("conversation_kind") or "") != "subagent":
                    continue
                messages = child.get("messages") if isinstance(child.get("messages"), list) else []
                has_running_draft = any(
                    is_running_subagent_durable_draft(message)
                    for message in messages
                    if isinstance(message, dict)
                )
                if has_completed_assistant_text(messages) and not has_running_draft:
                    continue
                age_seconds = self._conversation_age_seconds(child)
                if age_seconds is not None and age_seconds < SUBAGENT_GAP_GRACE_SECONDS:
                    continue
                repaired_message = mark_subagent_child_failed(
                    store,
                    child_id,
                    metadata=child.get("metadata") if isinstance(child.get("metadata"), dict) else {},
                    code="SUBAGENT_DISPATCH_INTERRUPTED",
                )
                if repaired_message is not None:
                    repaired.append(child_id)
                    child = store.get_conversation(child_id) or child
                    messages = child.get("messages") if isinstance(child.get("messages"), list) else messages
                    if has_completed_assistant_text(messages):
                        continue
                unanswered.append(
                    {
                        "child_conversation_id": child_id,
                        "title": str(child.get("title") or "Subagent"),
                        "message_count": len(messages),
                        "created_at": child.get("created_at"),
                        "last_user_prompt": next(
                            (
                                self._message_text(message)[:300]
                                for message in messages
                                if isinstance(message, dict) and str(message.get("role") or "") == "user"
                            ),
                            "",
                        ),
                    }
                )
            return {"checked_ids": child_ids, "unanswered": unanswered, "repaired": repaired}
        except Exception:
            return {"checked_ids": [], "unanswered": [], "repaired": []}

    @staticmethod
    def _conversation_age_seconds(conversation: dict[str, Any]) -> float | None:
        candidates = [
            conversation.get("updated_at"),
            conversation.get("created_at"),
        ]
        newest: float | None = None
        for candidate in candidates:
            timestamp_seconds = MimoCodingCompanyRuntime._coerce_epoch_seconds(candidate)
            if timestamp_seconds is None:
                continue
            newest = timestamp_seconds if newest is None else max(newest, timestamp_seconds)
        if newest is None:
            return None
        return max(0.0, datetime.now(timezone.utc).timestamp() - newest)

    @staticmethod
    def _coerce_epoch_seconds(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            number = float(value)
            if number <= 0:
                return None
            if number > 100000000000:
                return number / 1000.0
            return number
        text = str(value or "").strip()
        if not text:
            return None
        try:
            number = float(text)
            if number > 100000000000:
                return number / 1000.0
            return number if number > 0 else None
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    @staticmethod
    def _desktop_monitoring_observation() -> dict[str, Any]:
        summary: dict[str, Any] = {
            "surface": "desktops",
            "expected_api": "GET /api/desktops",
            "status": "unknown",
            "desktop_count": 0,
            "desktops": [],
        }
        try:
            from blocks.sandbox.api import run as sandbox_api_run

            result = sandbox_api_run({"_handler": "desktops_list"}, {"source": "mimo_observability"})
            if not isinstance(result, dict):
                summary["status"] = "error"
                summary["error"] = "desktop API returned a non-dict result"
                summary["signal"] = "desktops_probe_error"
                return summary
            if result.get("status") != "ok":
                err = result.get("error") if isinstance(result.get("error"), dict) else {}
                summary["status"] = "error"
                summary["error"] = str(err.get("message") or result.get("error") or "desktop API failed")[:300]
                summary["signal"] = "desktops_probe_error"
                return summary
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            desktops = data.get("desktops") if isinstance(data.get("desktops"), list) else []
            compact: list[dict[str, Any]] = []
            for desktop in desktops[:10]:
                if not isinstance(desktop, dict):
                    continue
                compact.append(
                    {
                        "seat_id": desktop.get("seat_id") or desktop.get("id"),
                        "name": desktop.get("name"),
                        "status": desktop.get("status"),
                        "template_id": desktop.get("template_id"),
                        "assigned_agent_id": desktop.get("assigned_agent_id"),
                    }
                )
            summary["desktop_count"] = len(desktops)
            summary["desktops"] = compact
            if not desktops:
                summary["status"] = "empty"
                summary["signal"] = "desktops_empty"
            else:
                summary["status"] = "ok"
            return summary
        except Exception as exc:
            summary["status"] = "error"
            summary["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            summary["signal"] = "desktops_probe_error"
            return summary

    @staticmethod
    def _message_text(message: dict[str, Any]) -> str:
        raw = str(message.get("raw_text") or "").strip()
        if raw:
            return raw
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(str(block.get("text") or block.get("content") or ""))
                else:
                    parts.append(str(block))
            return "\n".join(part for part in parts if part)
        return ""

    @staticmethod
    def _subagent_gap_message(gap: dict[str, Any]) -> str:
        prompt = str(gap.get("last_user_prompt") or "").strip()
        lines = [
            "**MiMo subagent child conversation has no assistant reply**",
            f"- Child conversation: `{gap.get('child_conversation_id') or ''}`",
            f"- Title: {gap.get('title') or 'Subagent'}",
            f"- Message count: {gap.get('message_count') or 0}",
        ]
        if prompt:
            lines.extend(["", "Latest user prompt:", "```text", prompt[:600], "```"])
        return "\n".join(lines)

    @staticmethod
    def _subagent_gap_resolved_message(child_conversation_id: str) -> str:
        return "\n".join(
            [
                "**MiMo subagent child conversation repaired**",
                f"- Child conversation: `{child_conversation_id}`",
                "- Previous signal: `subagent_unanswered`",
                "- Resolution: an assistant reply or repair marker is now present.",
            ]
        )

    @staticmethod
    def _desktop_monitoring_message(observation: dict[str, Any]) -> str:
        status = str(observation.get("status") or "unknown")
        count = int(observation.get("desktop_count") or 0)
        lines = [
            "**MiMo desktop monitor: Desktops workspace signal**",
            "- API: `GET /api/desktops`",
            f"- Status: `{status}`",
            f"- Desktop count: `{count}`",
        ]
        if status == "empty":
            lines.extend(
                [
                    "",
                    "No desktop seats are currently visible. Browser/computer QA may still be running through chat tools, but the Desktops workspace has no seat to inspect.",
                ]
            )
        elif observation.get("error"):
            lines.extend(["", "Error:", "```text", str(observation.get("error"))[:600], "```"])
        return "\n".join(lines)

    def _schedule_policy(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = state if isinstance(state, dict) else {}
        policy = {
            "profile_id": PROFILE_ID,
            "non_stop": True,
            "allow_shell": True,
            "allow_network": True,
            "allow_file_write": True,
            "write_actions_require_approval": False,
            "delete_actions_require_approval": True,
            "terminal_actions_require_approval": False,
            "normal_status_silent": True,
            "max_tool_calls": self._max_tool_calls(state.get("max_tool_calls")),
            "tool_allowlist": TOOL_ALLOWLIST,
            "model_allowlist": current_model_allowlist(),
            "schedule_initial_tool_choice": "required",
            "schedule_auto_approve_tool_requests": True,
            "schedule_auto_approve_tool_allowlist": [
                "rumi_api:list_routes",
                "GET /api/agent/mimo-company/status",
                "GET /api/agent/self-improvement/status",
                "GET /api/agent/multi/status",
                "GET /api/company/mimo-coding-company/channels",
                "GET /api/company/mimo-coding-company/messages",
                "GET /api/company/mimo-coding-company/status",
                "GET /api/company/status",
                "GET /api/desktops",
                "GET /api/health",
                "GET /api/remote/host/status",
                "todo",
                "subagent",
                "knowledge_search",
                "knowledge_create",
                "web_search",
                "browser_use",
                "browser_computer",
                "browser_companion",
                "computer_use",
                "desktop_list",
                "desktop_create",
                "desktop_frame",
                "desktop_input",
            ],
            "schedule_auto_approve_max_followups": "unlimited",
        }
        if state.get("workspace_id"):
            policy["workspace_id"] = state["workspace_id"]
        return policy

    def _ensure_interval_schedule(
        self,
        state: dict[str, Any],
        *,
        key: str,
        minutes: int,
        message: str,
        model: str,
        agent_id: str,
        tools: list[str],
        description: str,
    ) -> str | None:
        safe_minutes = max(1, min(int(minutes or 1), 1440))
        schedule_ids = state.setdefault("schedule_ids", {})
        scheduler = Scheduler()
        existing_id = schedule_ids.get(key)
        task = {
            "message": message,
            "model": model,
            "conversation_id": state.get("conversation_id"),
            "timeout": 600,
            "profile_id": PROFILE_ID,
            "agent_id": agent_id,
            "thinking_level": "high",
            "tools": list(tools),
            "tool_policy": self._schedule_policy(state),
            "metadata": {
                "profile_id": PROFILE_ID,
                "company_id": COMPANY_ID,
                "conversation_id": state.get("conversation_id"),
                "loop_key": key,
                **self._workspace_metadata(
                    workspace_id=state.get("workspace_id"),
                    workspace_label=state.get("workspace_label"),
                    workspace_root=state.get("workspace_root"),
                ),
            },
        }
        config = {"value": safe_minutes, "unit": "minutes"}
        name = f"MiMo Coding Company {key.replace('_', ' ')}"
        if existing_id and scheduler.get_schedule(existing_id):
            self._refresh_schedule(existing_id, task=task, config=config, name=name, description=description)
            return str(existing_id)
        schedule = scheduler.create_schedule(
            "interval",
            task,
            config,
            name=name,
            description=description,
        )
        schedule_ids[key] = schedule["id"]
        return str(schedule["id"])

    def _ensure_once_schedule(
        self,
        state: dict[str, Any],
        *,
        key: str,
        run_at: datetime,
        message: str,
        model: str,
        agent_id: str,
        tools: list[str],
        description: str,
    ) -> str | None:
        schedule_ids = state.setdefault("schedule_ids", {})
        scheduler = Scheduler()
        existing_id = schedule_ids.get(key)
        task = {
            "message": message,
            "model": model,
            "conversation_id": state.get("conversation_id"),
            "timeout": 900,
            "profile_id": PROFILE_ID,
            "agent_id": agent_id,
            "thinking_level": "high",
            "tools": list(tools),
            "tool_policy": self._schedule_policy(state),
            "metadata": {
                "profile_id": PROFILE_ID,
                "company_id": COMPANY_ID,
                "conversation_id": state.get("conversation_id"),
                "loop_key": key,
                **self._workspace_metadata(
                    workspace_id=state.get("workspace_id"),
                    workspace_label=state.get("workspace_label"),
                    workspace_root=state.get("workspace_root"),
                ),
            },
        }
        config = {"run_at": run_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
        name = "MiMo Coding Company kickoff review"
        if existing_id and scheduler.get_schedule(existing_id):
            self._refresh_schedule(existing_id, task=task, config=config, name=name, description=description)
            return str(existing_id)
        schedule = scheduler.create_schedule(
            "once",
            task,
            config,
            name=name,
            description=description,
        )
        schedule_ids[key] = schedule["id"]
        return str(schedule["id"])

    def _schedules_for_state(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        scheduler = Scheduler()
        schedules: list[dict[str, Any]] = []
        schedule_ids = state.get("schedule_ids") if isinstance(state.get("schedule_ids"), dict) else {}
        seen: set[str] = set()
        for raw_schedule_id in schedule_ids.values():
            schedule_id = str(raw_schedule_id or "").strip()
            if not schedule_id or schedule_id in seen:
                continue
            seen.add(schedule_id)
            schedule = scheduler.get_schedule(schedule_id)
            if schedule:
                try:
                    scheduler.recover_scheduled_chat_approval(schedule_id)
                    schedule = scheduler.get_schedule(schedule_id) or schedule
                except Exception:
                    pass
                schedules.append(schedule)
        return schedules

    @staticmethod
    def _mimo_loop_key_for_schedule(schedule: dict[str, Any]) -> str:
        task = schedule.get("task") if isinstance(schedule.get("task"), dict) else {}
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        if str(metadata.get("profile_id") or task.get("profile_id") or "") != PROFILE_ID:
            return ""
        if str(metadata.get("company_id") or "") != COMPANY_ID:
            return ""
        loop_key = str(metadata.get("loop_key") or "")
        return loop_key if loop_key in SCHEDULE_LOOP_KEYS else ""

    def _pause_mimo_loop_schedules_for_bootstrap(self) -> set[str]:
        paused: set[str] = set()
        for schedule in load_all_schedules():
            if not isinstance(schedule, dict):
                continue
            schedule_id = str(schedule.get("id") or "").strip()
            if not schedule_id or not self._mimo_loop_key_for_schedule(schedule):
                continue
            if schedule.get("status") != "active":
                continue
            scheduler = getattr(Scheduler, "_instance", None)
            if scheduler is not None and getattr(scheduler, "_loaded", False):
                try:
                    scheduler.pause_schedule(schedule_id)
                except Exception:
                    pass
            schedule["status"] = "paused"
            schedule["next_execution_at"] = None
            schedule["updated_at"] = timestamp()
            save_schedule(schedule)
            paused.add(schedule_id)
        return paused

    def _resume_mimo_loop_schedules_after_bootstrap(self, state: dict[str, Any], paused_schedule_ids: set[str]) -> list[str]:
        schedule_ids = state.get("schedule_ids") if isinstance(state.get("schedule_ids"), dict) else {}
        current_ids = {
            str(schedule_id)
            for loop_key, schedule_id in schedule_ids.items()
            if str(loop_key) in SCHEDULE_LOOP_KEYS
            and str(schedule_id or "").strip()
        }
        if not current_ids:
            return []

        scheduler = Scheduler()
        resumed: list[str] = []
        for schedule_id in sorted(current_ids):
            schedule = scheduler.get_schedule(schedule_id)
            if not schedule or schedule.get("status") == "completed":
                continue
            if schedule.get("status") == "active":
                resumed.append(schedule_id)
                continue
            updated = scheduler.resume_schedule(schedule_id)
            if updated and updated.get("status") == "active":
                resumed.append(schedule_id)
        return resumed

    def _pause_stale_mimo_schedules(self, state: dict[str, Any]) -> list[str]:
        schedule_ids = state.get("schedule_ids") if isinstance(state.get("schedule_ids"), dict) else {}
        keep_by_loop = {
            str(loop_key): str(schedule_id)
            for loop_key, schedule_id in schedule_ids.items()
            if str(loop_key) in SCHEDULE_LOOP_KEYS and str(schedule_id or "").strip()
        }
        if not keep_by_loop:
            return []

        scheduler = Scheduler()
        paused: list[str] = []
        for schedule in scheduler.list_schedules():
            if not isinstance(schedule, dict):
                continue
            schedule_id = str(schedule.get("id") or "")
            task = schedule.get("task") if isinstance(schedule.get("task"), dict) else {}
            metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
            if str(metadata.get("profile_id") or "") != PROFILE_ID:
                continue
            if str(metadata.get("company_id") or "") != COMPANY_ID:
                continue
            loop_key = str(metadata.get("loop_key") or "")
            if loop_key not in keep_by_loop or keep_by_loop[loop_key] == schedule_id:
                continue
            if schedule.get("status") == "active":
                scheduler.pause_schedule(schedule_id)
                paused.append(schedule_id)
        return paused

    def _refresh_schedule(
        self,
        schedule_id: str,
        *,
        task: dict[str, Any],
        config: dict[str, Any],
        name: str,
        description: str,
    ) -> None:
        scheduler = Scheduler()
        current = scheduler.get_schedule(schedule_id)
        if not current:
            return
        updates: dict[str, Any] = {}
        if current.get("task") != task:
            updates["task"] = task
        if current.get("config") != config:
            updates["config"] = config
        if current.get("name") != name:
            updates["name"] = name
        if current.get("description") != description:
            updates["description"] = description
        if updates:
            scheduler.update_schedule(schedule_id, updates)

    def _autonomy_board(self, state: dict[str, Any]) -> dict[str, Any]:
        main_model = str(state.get("main_model") or DEFAULT_MAIN_MODEL)
        vision_model = str(state.get("vision_model") or DEFAULT_VISION_MODEL)
        fast_model = str(state.get("fast_model") or DEFAULT_FAST_MODEL)
        qa_targets = list(state.get("qa_targets") if isinstance(state.get("qa_targets"), list) else [])
        streams: list[dict[str, Any]] = []
        for stream in IMPROVEMENT_STREAMS:
            item = deepcopy(stream)
            model_role = str(item.get("preferred_model_role") or "main")
            item["recommended_model"] = {
                "main": main_model,
                "vision": vision_model,
                "fast": fast_model,
            }.get(model_role, main_model)
            if item["id"] in {"frontend_qa_swarm", "docker_worker_swarm"}:
                item["qa_targets"] = list(qa_targets)
            streams.append(item)
        return {
            "selection_policy": "Pick one unfinished stream at a time. Use short prompts. Land one verified change before switching streams.",
            "supervision_contract": "Client Manager monitors, Project Manager delegates, Reviewer verifies, Toolsmith builds missing tools instead of stopping.",
            "streams": streams,
            "next_focus": streams[:3],
        }

    def _qa_swarm_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        docker_swarm = state.get("docker_swarm") if isinstance(state.get("docker_swarm"), dict) else self._docker_swarm_state()
        if docker_swarm.get("enabled") is False:
            return {
                "coordinator_agent_id": "browser_qa",
                "reporting_policy": "Report only evidence-backed bugs. Stay quiet if the assigned path passes.",
                "managed_desktop_fallback": {
                    "tools": ["desktop_list", "desktop_create", "desktop_frame", "desktop_input"],
                    "create_defaults": {
                        "template_id": "desktop.browser",
                        "starter": "browser_url",
                        "assigned_agent": "browser_qa",
                        "resolution": {"width": 1280, "height": 800},
                    },
                },
                "workers": [],
                "runtime_mode": "managed_desktop",
                "docker_disabled_reason": str(docker_swarm.get("disabled_reason") or "disabled"),
            }
        workers = docker_swarm.get("workers") if isinstance(docker_swarm.get("workers"), list) else []
        persona_specs = {str(item.get("id")): item for item in self._persona_specs()}
        assignments: list[dict[str, Any]] = []
        for worker in workers:
            if not isinstance(worker, dict):
                continue
            persona_id = str(worker.get("persona_id") or "first_time_user")
            persona_meta = PERSONA_MISSIONS.get(persona_id, {})
            persona_spec = persona_specs.get(persona_id, {})
            assignments.append(
                {
                    "worker_id": str(worker.get("worker_id") or ""),
                    "container_name": str(worker.get("container_name") or ""),
                    "persona_id": persona_id,
                    "persona_label": str(persona_spec.get("label") or persona_id),
                    "qa_target": str(worker.get("qa_target") or ""),
                    "mission": str(persona_meta.get("mission") or str(persona_spec.get("goal") or "")),
                    "probe_areas": list(persona_meta.get("probe_areas") or []),
                    "evidence_required": "Screenshots or exact repro steps before filing a bug.",
                    "fallback": "If browser_use, computer_use, or browser_companion cannot control a browser, use desktop_list/create/frame/input to continue in a managed desktop seat.",
                }
            )
        return {
            "coordinator_agent_id": "browser_qa",
            "reporting_policy": "Report only evidence-backed bugs. Stay quiet if the assigned path passes.",
            "managed_desktop_fallback": {
                "tools": ["desktop_list", "desktop_create", "desktop_frame", "desktop_input"],
                "create_defaults": {
                    "template_id": "desktop.browser",
                    "starter": "browser_url",
                    "assigned_agent": "browser_qa",
                    "resolution": {"width": 1280, "height": 800},
                },
            },
            "workers": assignments,
        }

    def _kickoff_message(self, state: dict[str, Any]) -> str:
        focus_items = self._autonomy_board(state).get("next_focus", [])
        focus = ", ".join(str(item.get("title") or item.get("id") or "") for item in focus_items[:3] if isinstance(item, dict))
        return (
            "Start MiMo Coding Company with one simple coding task. Pick one stream"
            + (": " + focus if focus else "")
            + ". Use short prompts. Hand implementation to @coding_engineer, review to @reviewer, and record the outcome in knowledge. "
            "If a missing tool or skill blocks progress, ask @toolsmith to create the smallest viable version."
        )

    def _heartbeat_message(self, state: dict[str, Any]) -> str:
        monitoring_summary = self._docker_swarm_monitoring_summary(state)
        return (
            "Run a short heartbeat for the MiMo Coding Company. Check pending tasks, recent failures, QA bugs, and blocked work. "
            "Also verify Team Workspace/Company Workspace channel sync, unanswered subagent child conversations, and the managed desktop list at /api/desktops. "
            + (monitoring_summary + " " if monitoring_summary else "")
            + "If nothing important changed, stay silent. If action is needed, mention @client_manager and @project_manager with evidence."
        )

    def _improvement_message(self, state: dict[str, Any]) -> str:
        main_model = str(state.get("main_model") or DEFAULT_MAIN_MODEL)
        focus_items = self._autonomy_board(state).get("next_focus", [])
        focus = "; ".join(str(item.get("title") or item.get("id") or "") for item in focus_items[:3] if isinstance(item, dict))
        return (
            "Run the self-improvement loop. Keep prompts short. Pick one stream"
            + (": " + focus if focus else "")
            + ". Use "
            + main_model
            + " as the main reasoning model. If the best next step needs a new tool or skill, create the smallest viable version instead of stopping. "
            "Land one verified change, then capture what changed in knowledge."
        )

    def _qa_message(self, state: dict[str, Any]) -> str:
        assignments = self._qa_swarm_plan(state).get("workers", [])
        monitoring_summary = self._docker_swarm_monitoring_summary(state)
        qa_targets = list(state.get("qa_targets") if isinstance(state.get("qa_targets"), list) else [])
        managed_targets = [self._managed_desktop_target_url(str(target)) for target in qa_targets]
        summary = "; ".join(
            (
                str(item.get("worker_id") or "")
                + " "
                + str(item.get("persona_label") or item.get("persona_id") or "")
                + " -> "
                + self._managed_desktop_target_url(str(item.get("qa_target") or "defaultspack surface"))
            )
            for item in assignments[:4]
            if isinstance(item, dict)
        )
        target_summary = "; ".join(target for target in managed_targets if target)
        return (
            "Run a QA swarm with short prompts."
            + (" " + monitoring_summary if monitoring_summary else "")
            + (" Assignments: " + summary + "." if summary else "")
            + (" Managed desktop target URLs: " + target_summary + "." if target_summary else "")
            + " First call desktop_list. Reuse only desktops whose status is running and whose startup.browser_url, desktop_spec.browser_url, or metadata startup browser_url exactly matches the managed desktop target URL. Ignore destroyed, failed, stale, or wrong-target seats. If no current-target running browser desktop is available, create a managed desktop with desktop_create using template_id=desktop.browser, starter=browser_url, browser_url=<managed desktop target URL>, assigned_agent=browser_qa. Desktop and sandbox access comes from trusted local/server context; do not add payload owner_id as proof of access. If a frame shows ERR_CONNECTION_REFUSED or a different address-bar URL, treat that seat as stale/wrong-target and create a current-target desktop. For desktop_frame and desktop_input, use the selected desktop's seat_id directly and let the server-provided principal context authorize access. For desktop_input, always include action: type text with action=type_text and text, press Enter with action=key and key=Enter, and never send a text-only payload. Prefer desktop_create with starter=browser_url and browser_url=<managed desktop target URL> for URL navigation when possible. Do not use rumi_api for desktop frames or inputs; /api/desktops/{seat_id}/frame is a GET route, never POST. "
            "Click around, use browser_use, browser_companion, computer_use, or managed desktop tools as needed, and prioritize workers missing status or browser launch before broad exploration. "
            "Log only evidence-backed bugs with repro steps. "
            "Stay quiet if everything passes."
        )
