from __future__ import annotations

import copy
import re
import time
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_PRIMARY_MODEL = "stub/default"
DEFAULT_REVIEW_GATED_COMMANDS = [
    "commit",
    "push",
    "merge",
    "terminal",
    "patch",
    "branch",
]
DEFAULT_HUMAN_ONLY_COMMANDS = ["yolo", "ultra", "ultra_yolo", "ultrayolo"]
CONTEXT_POLICY_MODES = {
    "prompt_only",
    "summary_clone",
    "forked_clone",
    "persistent_role",
    "utility_call",
}
REVIEW_GATE_MODES = {"off", "warning", "blocking"}
SELECTION_TARGETS = {"profile", "team", "fusion"}
CONVERSATION_SURFACES = {"human", "mode_agent", "team_agent", "fusion_agent"}


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def text_value(value: Any) -> str:
    return str(value or "").strip()


def list_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = re.split(r"[\n,]", value)
    else:
        values = []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = text_value(item)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def dict_value(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def record_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        values = value.values()
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [copy.deepcopy(item) for item in values if isinstance(item, dict)]


def localized_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, dict):
        for key in ("ja", "en", "label", "title", "text"):
            cleaned = text_value(value.get(key))
            if cleaned:
                return cleaned
    return text_value(value) or fallback


def safe_id(prefix: str, value: Any) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._:-]+", "-", text_value(value)).strip("-._:")
    return cleaned or prefix


def role_key_from_profile(profile_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", text_value(profile_id)).strip("_").lower()
    return cleaned or "registered_profile"


def runtime_profile_id_from(profile: dict[str, Any]) -> str:
    return text_value(
        profile.get("runtime_profile_id")
        or profile.get("base_profile_id")
        or profile.get("capability_profile_id")
        or profile.get("profile_ref")
        or profile.get("source_profile_id")
    )


def normalize_model_settings(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    return {
        "primary_model_profile_id": text_value(
            data.get("primary_model_profile_id")
            or data.get("primary_model")
            or data.get("model")
        ),
        "delegated_model_profile_id": text_value(
            data.get("delegated_model_profile_id") or data.get("delegated_model")
        ),
        "reviewer_model_profile_id": text_value(
            data.get("reviewer_model_profile_id") or data.get("reviewer_model")
        ),
        "fusion_model_profile_id": text_value(
            data.get("fusion_model_profile_id") or data.get("fusion_model")
        ),
        "selection_model_profile_id": text_value(
            data.get("selection_model_profile_id") or data.get("selection_model")
        ),
    }


def normalize_command_policy(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    return {
        "allowed_commands": list_strings(data.get("allowed_commands")),
        "denied_commands": list_strings(data.get("denied_commands")),
        "human_only_commands": list_strings(data.get("human_only_commands"))
        or list(DEFAULT_HUMAN_ONLY_COMMANDS),
        "allow_surfaces": [
            surface
            for surface in list_strings(data.get("allow_surfaces"))
            if surface in CONVERSATION_SURFACES
        ],
        "deny_surfaces": [
            surface
            for surface in list_strings(data.get("deny_surfaces"))
            if surface in CONVERSATION_SURFACES
        ],
        "restrict_to_allowlist": bool(data.get("restrict_to_allowlist")),
    }


def normalize_context_policy(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    mode = text_value(data.get("mode") or data.get("context_mode")) or "persistent_role"
    if mode not in CONTEXT_POLICY_MODES:
        mode = "persistent_role"
    return {
        "mode": mode,
        "writeback": text_value(data.get("writeback") or data.get("write_back") or "summary"),
        "share_history": bool(data.get("share_history", True)),
        "share_workspace": bool(data.get("share_workspace", True)),
        "persist_summary": bool(data.get("persist_summary", mode == "persistent_role")),
        "fork_workspace": bool(data.get("fork_workspace", mode == "forked_clone")),
        "metadata": dict_value(data.get("metadata")),
    }


def normalize_review_gate(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    mode = text_value(data.get("mode") or data.get("review_gate_mode") or "off").lower()
    if mode not in REVIEW_GATE_MODES:
        mode = "off"
    return {
        "mode": mode,
        "reviewer_profile_id": text_value(
            data.get("reviewer_profile_id") or data.get("reviewer_id")
        ),
        "gated_commands": list_strings(data.get("gated_commands"))
        or list(DEFAULT_REVIEW_GATED_COMMANDS),
        "note": text_value(data.get("note")),
    }


def normalize_selection(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    return {
        "manual_only": bool(data.get("manual_only")),
        "auto_select": bool(data.get("auto_select")),
        "router_prompt": text_value(data.get("router_prompt")),
        "router_rules": list_strings(data.get("router_rules")),
        "test_inputs": list_strings(data.get("test_inputs")),
    }


def normalize_registered_profile(value: Any, *, builtin: bool = False) -> dict[str, Any]:
    data = dict_value(value)
    profile_id = safe_id(
        "registered-profile",
        data.get("id")
        or data.get("profile_id")
        or data.get("registered_profile_id")
        or data.get("name"),
    )
    now = timestamp()
    return {
        "id": profile_id,
        "profile_id": profile_id,
        "display_name": localized_text(
            data.get("display_name") or data.get("name"), profile_id
        ),
        "description": localized_text(data.get("description")),
        "runtime_profile_id": text_value(
            data.get("runtime_profile_id")
            or data.get("base_profile_id")
            or data.get("capability_profile_id")
            or data.get("source_profile_id")
        ),
        "base_profile_id": text_value(
            data.get("base_profile_id")
            or data.get("runtime_profile_id")
            or data.get("capability_profile_id")
            or data.get("source_profile_id")
        ),
        "source_type": text_value(data.get("source_type") or ("builtin" if builtin else "custom")) or "custom",
        "builtin": builtin or bool(data.get("builtin")),
        "status": text_value(data.get("status") or "active") or "active",
        "aliases": list_strings(data.get("aliases")),
        "command_shortcuts": list_strings(
            data.get("command_shortcuts") or data.get("commands")
        ),
        "tags": list_strings(data.get("tags")),
        "surfaces": list_strings(data.get("surfaces")) or ["chat", "workroom"],
        "compatibility_aliases": list_strings(
            data.get("compatibility_aliases") or data.get("legacy_aliases")
        ),
        "enabled_capabilities": list_strings(
            data.get("enabled_capabilities") or data.get("capabilities")
        ),
        "prompt_set": text_value(data.get("prompt_set")),
        "policy": dict_value(data.get("policy")),
        "model_settings": normalize_model_settings(data.get("model_settings")),
        "command_policy": normalize_command_policy(data.get("command_policy")),
        "context_policy": normalize_context_policy(data.get("context_policy")),
        "review_gate": normalize_review_gate(data.get("review_gate")),
        "selection": normalize_selection(data.get("selection")),
        "metadata": dict_value(data.get("metadata")),
        "created_at": text_value(data.get("created_at")) or now,
        "updated_at": now,
    }


def normalize_team_definition(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    team_id = safe_id("team", data.get("id") or data.get("team_id") or data.get("name"))
    now = timestamp()
    return {
        "id": team_id,
        "team_id": team_id,
        "display_name": localized_text(data.get("display_name") or data.get("name"), team_id),
        "description": localized_text(data.get("description")),
        "coordinator_profile_id": text_value(
            data.get("coordinator_profile_id") or data.get("lead_profile_id")
        ),
        "reviewer_profile_id": text_value(data.get("reviewer_profile_id")),
        "member_profile_ids": list_strings(
            data.get("member_profile_ids") or data.get("members")
        ),
        "dispatch_mode": text_value(data.get("dispatch_mode") or "delegated_queue") or "delegated_queue",
        "command_policy": normalize_command_policy(data.get("command_policy")),
        "review_gate": normalize_review_gate(data.get("review_gate")),
        "context_policy": normalize_context_policy(data.get("context_policy")),
        "model_settings": normalize_model_settings(data.get("model_settings")),
        "metadata": dict_value(data.get("metadata")),
        "created_at": text_value(data.get("created_at")) or now,
        "updated_at": now,
    }


def normalize_fusion_definition(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    fusion_id = safe_id(
        "fusion", data.get("id") or data.get("fusion_id") or data.get("name")
    )
    now = timestamp()
    return {
        "id": fusion_id,
        "fusion_id": fusion_id,
        "display_name": localized_text(data.get("display_name") or data.get("name"), fusion_id),
        "description": localized_text(data.get("description")),
        "participant_profile_ids": list_strings(
            data.get("participant_profile_ids") or data.get("participants")
        ),
        "synthesis_profile_id": text_value(
            data.get("synthesis_profile_id") or data.get("coordinator_profile_id")
        ),
        "max_participants": max(2, int(data.get("max_participants") or 3)),
        "max_rounds": max(1, int(data.get("max_rounds") or 2)),
        "max_tool_calls": max(1, int(data.get("max_tool_calls") or 6)),
        "command_policy": normalize_command_policy(data.get("command_policy")),
        "review_gate": normalize_review_gate(data.get("review_gate")),
        "context_policy": normalize_context_policy(data.get("context_policy")),
        "model_settings": normalize_model_settings(data.get("model_settings")),
        "metadata": dict_value(data.get("metadata")),
        "created_at": text_value(data.get("created_at")) or now,
        "updated_at": now,
    }


def normalize_selection_rule(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    rule_id = safe_id("rule", data.get("id") or data.get("name") or data.get("target_id"))
    target = text_value(data.get("target_type") or "profile")
    if target not in SELECTION_TARGETS:
        target = "profile"
    now = timestamp()
    return {
        "id": rule_id,
        "display_name": localized_text(data.get("display_name") or data.get("name"), rule_id),
        "enabled": data.get("enabled") is not False,
        "target_type": target,
        "target_id": text_value(
            data.get("target_id")
            or data.get("profile_id")
            or data.get("team_id")
            or data.get("fusion_id")
        ),
        "match_terms": list_strings(data.get("match_terms") or data.get("terms")),
        "prompt_contains": list_strings(
            data.get("prompt_contains") or data.get("when_contains")
        ),
        "condition_prompt": text_value(
            data.get("condition_prompt")
            or data.get("natural_language_condition")
            or data.get("when_prompt")
        ),
        "reason": text_value(data.get("reason")),
        "requires_confirmation": bool(data.get("requires_confirmation")),
        "metadata": dict_value(data.get("metadata")),
        "created_at": text_value(data.get("created_at")) or now,
        "updated_at": now,
    }


def normalize_settings(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    return {
        "model_defaults": normalize_model_settings(data.get("model_defaults")),
        "terminology": {
            "registered_profile_label": "Agent Profile",
            "setup_profile_label": "Setup Profile",
            "mode_agent_label": "Mode Agent",
            "fusion_agent_label": "Fusion Agent",
            "team_agent_label": "Team Agent",
            **dict_value(data.get("terminology")),
        },
        "selection_defaults": {
            "surface": text_value(
                dict_value(data.get("selection_defaults")).get("surface") or "human"
            )
            or "human",
            "auto_select": bool(
                dict_value(data.get("selection_defaults")).get("auto_select")
            ),
        },
        "metadata": dict_value(data.get("metadata")),
    }


def normalize_bundle(value: Any) -> dict[str, Any]:
    data = dict_value(value)
    profiles = {
        item["id"]: item
        for item in (
            normalize_registered_profile(profile)
            for profile in record_list(data.get("profiles"))
        )
    }
    teams = {
        item["id"]: item
        for item in (
            normalize_team_definition(team)
            for team in record_list(data.get("teams"))
        )
    }
    fusions = {
        item["id"]: item
        for item in (
            normalize_fusion_definition(fusion)
            for fusion in record_list(data.get("fusions"))
        )
    }
    rules = [normalize_selection_rule(rule) for rule in data.get("selection_rules", []) if isinstance(rule, dict)]
    return {
        "schema_version": SCHEMA_VERSION,
        "profiles": profiles,
        "teams": teams,
        "fusions": fusions,
        "selection_rules": rules,
        "settings": normalize_settings(data.get("settings")),
        "updated_at": timestamp(),
    }


def profile_to_company_agent(profile: dict[str, Any]) -> dict[str, Any]:
    display_name = text_value(profile.get("display_name") or profile.get("profile_id"))
    role_key = role_key_from_profile(text_value(profile.get("profile_id") or profile.get("id")))
    runtime_profile_id = runtime_profile_id_from(profile)
    description = text_value(profile.get("description"))
    model_settings = normalize_model_settings(profile.get("model_settings"))
    default_model = (
        text_value(model_settings.get("delegated_model_profile_id"))
        or text_value(model_settings.get("primary_model_profile_id"))
        or DEFAULT_PRIMARY_MODEL
    )
    system_prompt = (
        f"You are {display_name}. "
        f"Operate using the registered agent profile '{text_value(profile.get('profile_id') or profile.get('id'))}'. "
        f"Base runtime profile: '{runtime_profile_id or 'none'}'."
    )
    if description:
        system_prompt += f" Brief: {description}"
    return {
        "agent_id": role_key,
        "role_key": role_key,
        "agent_name": display_name,
        "display_name": display_name,
        "model": default_model,
        "aliases": list_strings(profile.get("aliases")),
        "allowed_tools": [],
        "system_prompt": system_prompt,
        "metadata": {
            "registered_profile_id": text_value(profile.get("profile_id") or profile.get("id")),
            "runtime_profile_id": runtime_profile_id,
            "command_policy": normalize_command_policy(profile.get("command_policy")),
            "context_policy": normalize_context_policy(profile.get("context_policy")),
            "review_gate": normalize_review_gate(profile.get("review_gate")),
            "model_settings": model_settings,
            **dict_value(profile.get("metadata")),
        },
    }
