from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from core_runtime.profile_workspace import ProfileWorkspaceManager
from domain.capability.catalog import CapabilityCatalog
from domain.chat.store import ChatStore
from domain.company.service import CompanyService

from .models import (
    CONVERSATION_SURFACES,
    DEFAULT_HUMAN_ONLY_COMMANDS,
    dict_value,
    list_strings,
    localized_text,
    normalize_bundle,
    normalize_command_policy,
    normalize_context_policy,
    normalize_fusion_definition,
    normalize_model_settings,
    normalize_registered_profile,
    normalize_review_gate,
    normalize_selection_rule,
    normalize_settings,
    normalize_team_definition,
    profile_to_company_agent,
    runtime_profile_id_from,
    safe_id,
    text_value,
    timestamp,
)
from .store import AgentStudioStore


BUILTIN_REGISTERED_PROFILE_SPECS: list[dict[str, Any]] = [
    {
        "id": "builtin.coding",
        "display_name": "Coding Agent Profile",
        "description": "Primary implementation profile for code changes and local validation.",
        "base_profile_id": "defaultspack.coding",
        "aliases": ["coding", "code", "coder"],
        "command_shortcuts": ["coding"],
        "compatibility_aliases": ["coder"],
        "tags": ["coding", "implementation"],
        "review_gate": {"mode": "blocking", "reviewer_profile_id": "builtin.review"},
    },
    {
        "id": "builtin.mini_coding",
        "display_name": "Mini Coding Agent Profile",
        "description": "A lower-cost coding profile for small fixes, quick iterations, and focused patches.",
        "base_profile_id": "defaultspack.coding",
        "aliases": ["mini", "mini-coding", "mini-coder"],
        "command_shortcuts": ["mini"],
        "tags": ["coding", "budget"],
        "model_settings": {
            "primary_model_profile_id": "openrouter/cohere/north-mini-code:free",
            "delegated_model_profile_id": "openrouter/cohere/north-mini-code:free",
        },
        "review_gate": {"mode": "blocking", "reviewer_profile_id": "builtin.review"},
    },
    {
        "id": "builtin.design",
        "display_name": "Design Agent Profile",
        "description": "Frontend and UX profile for intentional layouts and visual polish.",
        "base_profile_id": "rumi_frontend_design.frontend_design_reviewer",
        "aliases": ["design", "ui", "ux"],
        "command_shortcuts": ["design"],
        "tags": ["frontend", "design"],
    },
    {
        "id": "builtin.frontend",
        "display_name": "Frontend Only Agent Profile",
        "description": "UI-focused profile for frontend-only changes, responsive QA, and visual cleanup.",
        "base_profile_id": "rumi_frontend_design.frontend_design_reviewer",
        "aliases": ["frontend", "frontend-only"],
        "command_shortcuts": ["frontend"],
        "tags": ["frontend", "ui", "design"],
        "review_gate": {"mode": "blocking", "reviewer_profile_id": "builtin.review"},
    },
    {
        "id": "builtin.research",
        "display_name": "Research Agent Profile",
        "description": "Evidence-first research and synthesis profile.",
        "base_profile_id": "defaultspack.research_agent",
        "aliases": ["research", "analyst"],
        "command_shortcuts": ["research"],
        "compatibility_aliases": ["searcher"],
        "tags": ["research", "facts"],
    },
    {
        "id": "builtin.review",
        "display_name": "Reviewer Agent Profile",
        "description": "Review profile focused on bugs, regressions, and missing tests.",
        "base_profile_id": "rumi_agent_services.quality_reviewer",
        "aliases": ["review", "reviewer", "qa"],
        "command_shortcuts": ["reviewer"],
        "compatibility_aliases": ["reviewer"],
        "tags": ["review", "qa"],
    },
    {
        "id": "builtin.doc",
        "display_name": "Document Agent Profile",
        "description": "Document-focused artifact profile for Word and doc-style work.",
        "base_profile_id": "rumi_workspace_pack.workspace_artifact_agent",
        "aliases": ["doc", "document"],
        "command_shortcuts": ["doc"],
        "tags": ["artifact", "document"],
        "metadata": {"artifact_type": "document"},
    },
    {
        "id": "builtin.slide",
        "display_name": "Slide Agent Profile",
        "description": "Presentation profile for slide creation and polishing.",
        "base_profile_id": "rumi_workspace_pack.workspace_artifact_agent",
        "aliases": ["slide", "slides", "deck"],
        "command_shortcuts": ["slide"],
        "tags": ["artifact", "slides"],
        "metadata": {"artifact_type": "slides"},
    },
    {
        "id": "builtin.sheet",
        "display_name": "Sheet Agent Profile",
        "description": "Spreadsheet creation and editing profile.",
        "base_profile_id": "rumi_workspace_pack.workspace_artifact_agent",
        "aliases": ["sheet", "spreadsheet"],
        "command_shortcuts": ["sheet"],
        "tags": ["artifact", "spreadsheet"],
        "metadata": {"artifact_type": "spreadsheet"},
    },
    {
        "id": "builtin.csv",
        "display_name": "CSV Agent Profile",
        "description": "CSV and Sheets analyst profile for profiling and analysis.",
        "base_profile_id": "rumi_data_analysis.csv_sheet_analyst",
        "aliases": ["csv", "data"],
        "command_shortcuts": ["csv"],
        "tags": ["csv", "analysis"],
    },
    {
        "id": "builtin.movie",
        "display_name": "Movie Agent Profile",
        "description": "Storyboard and multimedia planning profile for movie-oriented work.",
        "base_profile_id": "rumi_workspace_pack.workspace_artifact_agent",
        "aliases": ["movie", "video"],
        "command_shortcuts": ["movie"],
        "tags": ["movie", "media"],
        "metadata": {"artifact_type": "movie", "workflow_id": "video_storyboard_review"},
    },
]

BUILTIN_TEAM_SPECS: list[dict[str, Any]] = [
    {
        "id": "builtin.delivery_team",
        "display_name": "Delivery Team Agent",
        "description": "Research, implementation, and review orchestrated as a reusable team.",
        "coordinator_profile_id": "builtin.coding",
        "reviewer_profile_id": "builtin.review",
        "member_profile_ids": ["builtin.research", "builtin.coding", "builtin.review"],
        "review_gate": {"mode": "blocking", "reviewer_profile_id": "builtin.review"},
    },
    {
        "id": "builtin.artifact_team",
        "display_name": "Artifact Team Agent",
        "description": "Document, slide, sheet, and CSV members coordinated inside a workroom.",
        "coordinator_profile_id": "builtin.doc",
        "member_profile_ids": ["builtin.doc", "builtin.slide", "builtin.sheet", "builtin.csv"],
    },
]

BUILTIN_FUSION_SPECS: list[dict[str, Any]] = [
    {
        "id": "builtin.delivery_fusion",
        "display_name": "Delivery Fusion Agent",
        "description": "OpenRouter Fusion-style deliberation across research, coding, and review.",
        "participant_profile_ids": ["builtin.research", "builtin.coding", "builtin.review"],
        "synthesis_profile_id": "builtin.review",
        "max_participants": 3,
        "max_rounds": 2,
        "max_tool_calls": 6,
        "review_gate": {"mode": "blocking", "reviewer_profile_id": "builtin.review"},
    }
]


class AgentStudioService:
    def __init__(
        self,
        store: AgentStudioStore | None = None,
        *,
        pack_root: Path | None = None,
        workspace_manager: ProfileWorkspaceManager | None = None,
    ) -> None:
        self.store = store or AgentStudioStore()
        self.pack_root = pack_root or Path(__file__).resolve().parents[2]
        self.catalog = CapabilityCatalog(self.pack_root)
        self.workspace_manager = workspace_manager or ProfileWorkspaceManager()

    def manifest(self) -> dict[str, Any]:
        bundle = self.store.read()
        return {
            "storage_file": str(self.store.storage_file),
            "profiles": self.list_profiles(),
            "teams": self.list_teams(),
            "fusions": self.list_fusions(),
            "selection_rules": self.list_selection_rules(),
            "settings": normalize_settings(bundle.get("settings")),
            "shortcut_index": self.shortcut_index(),
            "compatibility_alias_index": self.compatibility_alias_index(),
            "summary": {
                "profile_count": len(self.list_profiles()),
                "builtin_profile_count": len(self.builtin_profiles()),
                "team_count": len(self.list_teams()),
                "fusion_count": len(self.list_fusions()),
            },
        }

    def list_profiles(self) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in self.builtin_profiles():
            merged[item["id"]] = item
        bundle = self.store.read()
        for item in bundle.get("profiles", {}).values():
            profile = normalize_registered_profile(item)
            merged[profile["id"]] = profile
        for item in self.workspace_profiles():
            merged[item["id"]] = item
        return sorted(
            merged.values(),
            key=lambda item: (
                0 if item.get("builtin") else 1,
                str(item.get("display_name") or item.get("id") or "").casefold(),
            ),
        )

    def list_teams(self) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {
            item["id"]: item for item in self.builtin_teams()
        }
        bundle = self.store.read()
        for item in bundle.get("teams", {}).values():
            team = normalize_team_definition(item)
            merged[team["id"]] = team
        return sorted(
            merged.values(),
            key=lambda item: str(item.get("display_name") or item.get("id") or "").casefold(),
        )

    def list_fusions(self) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {
            item["id"]: item for item in self.builtin_fusions()
        }
        bundle = self.store.read()
        for item in bundle.get("fusions", {}).values():
            fusion = normalize_fusion_definition(item)
            merged[fusion["id"]] = fusion
        return sorted(
            merged.values(),
            key=lambda item: str(item.get("display_name") or item.get("id") or "").casefold(),
        )

    def list_selection_rules(self) -> list[dict[str, Any]]:
        bundle = self.store.read()
        return [normalize_selection_rule(item) for item in bundle.get("selection_rules", [])]

    def builtin_profiles(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for spec in BUILTIN_REGISTERED_PROFILE_SPECS:
            catalog_profile = self.catalog.profile(text_value(spec.get("base_profile_id"))) or {}
            policy = dict_value(catalog_profile.get("policy"))
            enabled_capabilities = list(catalog_profile.get("enabled_capabilities") or [])
            item = normalize_registered_profile(
                {
                    **catalog_profile,
                    **spec,
                    "display_name": spec.get("display_name")
                    or catalog_profile.get("display_name")
                    or catalog_profile.get("name"),
                    "description": spec.get("description")
                    or catalog_profile.get("description"),
                    "policy": {
                        **policy,
                        **dict_value(spec.get("policy")),
                    },
                    "enabled_capabilities": enabled_capabilities or spec.get("enabled_capabilities"),
                    "source_type": "builtin",
                },
                builtin=True,
            )
            items.append(item)
        return items

    def builtin_teams(self) -> list[dict[str, Any]]:
        return [normalize_team_definition(item) for item in BUILTIN_TEAM_SPECS]

    def builtin_fusions(self) -> list[dict[str, Any]]:
        return [normalize_fusion_definition(item) for item in BUILTIN_FUSION_SPECS]

    def workspace_profiles(self) -> list[dict[str, Any]]:
        root = self.workspace_manager.user_data_root / "profiles"
        if not root.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(root.iterdir()):
            profile_file = path / "profile.yaml"
            if not profile_file.is_file():
                continue
            try:
                profile = self.workspace_manager.load_profile_yaml(path.name)
            except Exception:
                continue
            runtime_id = text_value(profile.get("profile_id") or path.name)
            item = normalize_registered_profile(
                {
                    "id": runtime_id,
                    "display_name": localized_text(profile.get("display_name") or profile.get("name"), runtime_id),
                    "description": localized_text(profile.get("description")),
                    "runtime_profile_id": runtime_id,
                    "base_profile_id": runtime_id,
                    "source_type": "project_local",
                    "context_policy": {"mode": "persistent_role"},
                    "metadata": {
                        "profile_workspace": self.workspace_manager.payload_for_profile(runtime_id),
                    },
                    **profile,
                }
            )
            items.append(item)
        return items

    def resolve_profile(self, query: str) -> dict[str, Any] | None:
        needle = text_value(query).lower().lstrip("/")
        if not needle:
            return None
        for profile in self.list_profiles():
            tokens = {
                text_value(profile.get("id")).lower(),
                text_value(profile.get("profile_id")).lower(),
                runtime_profile_id_from(profile).lower(),
                *(item.lower() for item in profile.get("aliases", [])),
                *(item.lower() for item in profile.get("command_shortcuts", [])),
                *(item.lower() for item in profile.get("compatibility_aliases", [])),
            }
            if needle in tokens:
                return profile
        return None

    def resolve_team(self, query: str) -> dict[str, Any] | None:
        needle = text_value(query).lower().lstrip("/")
        if not needle:
            return None
        for team in self.list_teams():
            tokens = {
                text_value(team.get("id")).lower(),
                text_value(team.get("team_id")).lower(),
                text_value(team.get("display_name")).lower(),
            }
            if needle in tokens:
                return team
        return None

    def resolve_fusion(self, query: str) -> dict[str, Any] | None:
        needle = text_value(query).lower().lstrip("/")
        if not needle:
            return None
        for fusion in self.list_fusions():
            tokens = {
                text_value(fusion.get("id")).lower(),
                text_value(fusion.get("fusion_id")).lower(),
                text_value(fusion.get("display_name")).lower(),
            }
            if needle in tokens:
                return fusion
        return None

    def shortcut_index(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for profile in self.list_profiles():
            for shortcut in profile.get("command_shortcuts", []):
                result[text_value(shortcut).lower()] = text_value(profile.get("id"))
        return result

    def compatibility_alias_index(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for profile in self.list_profiles():
            for alias in profile.get("compatibility_aliases", []):
                result[text_value(alias).lower()] = text_value(profile.get("id"))
        return result

    def upsert_profile(self, record: dict[str, Any]) -> dict[str, Any]:
        self._validate_profile_record(record)
        return self.store.upsert_profile(record)

    def delete_profile(self, profile_id: str) -> bool:
        return self.store.delete_profile(profile_id)

    def upsert_team(self, record: dict[str, Any]) -> dict[str, Any]:
        self._validate_team_record(record)
        return self.store.upsert_team(record)

    def delete_team(self, team_id: str) -> bool:
        return self.store.delete_team(team_id)

    def upsert_fusion(self, record: dict[str, Any]) -> dict[str, Any]:
        self._validate_fusion_record(record)
        return self.store.upsert_fusion(record)

    def delete_fusion(self, fusion_id: str) -> bool:
        return self.store.delete_fusion(fusion_id)

    def replace_selection_rules(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._validate_selection_rules(rules)
        return self.store.replace_selection_rules(rules)

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_settings(updates)

    def import_bundle(self, payload: dict[str, Any], *, merge: bool = False) -> dict[str, Any]:
        self._validate_bundle(payload)
        imported = normalize_bundle(payload)
        if not merge:
            return self.store.replace(imported)
        current = self.store.read()
        merged = {
            **current,
            "profiles": {
                **dict_value(current.get("profiles")),
                **dict_value(imported.get("profiles")),
            },
            "teams": {
                **dict_value(current.get("teams")),
                **dict_value(imported.get("teams")),
            },
            "fusions": {
                **dict_value(current.get("fusions")),
                **dict_value(imported.get("fusions")),
            },
            "selection_rules": [
                *current.get("selection_rules", []),
                *imported.get("selection_rules", []),
            ],
            "settings": {
                **dict_value(current.get("settings")),
                **dict_value(imported.get("settings")),
            },
        }
        return self.store.replace(merged)

    def export_bundle(self) -> dict[str, Any]:
        bundle = self.store.read()
        return {
            **bundle,
            "profiles": list(bundle.get("profiles", {}).values()),
            "teams": list(bundle.get("teams", {}).values()),
            "fusions": list(bundle.get("fusions", {}).values()),
            "selection_rules": list(bundle.get("selection_rules", [])),
        }

    def activate_profile_for_conversation(
        self,
        conversation_id: str,
        profile_id: str,
        *,
        surface: str = "mode_agent",
        reason: str = "manual_profile_switch",
    ) -> dict[str, Any]:
        profile = self.resolve_profile(profile_id)
        if profile is None:
            raise ValueError("unknown registered profile: " + str(profile_id))
        runtime_profile_id = runtime_profile_id_from(profile)
        agent_state = self._agent_studio_state_patch(
            conversation_id,
            {
                "surface": surface if surface in CONVERSATION_SURFACES else "mode_agent",
                "active_profile_id": text_value(profile.get("id")),
                "active_team_id": "",
                "active_fusion_id": "",
                "runtime_profile_id": runtime_profile_id,
                "active_label": text_value(profile.get("display_name")),
                "review_gate": {
                    "approved": False,
                    "approved_at": "",
                    "approved_by": "",
                },
                "activated_at": timestamp(),
                "activation_reason": reason,
            },
            activity_entry=self._activity_entry(
                event_type="activation",
                message=f"Mode Agent switched to {text_value(profile.get('display_name')) or text_value(profile.get('id'))}.",
                surface=surface if surface in CONVERSATION_SURFACES else "mode_agent",
                target_id=text_value(profile.get("id")),
                label=text_value(profile.get("display_name")),
                reason=reason,
            ),
        )
        metadata_patch = {
            "profile_id": runtime_profile_id or text_value(profile.get("id")),
            "agent_profile_id": text_value(profile.get("id")),
            "agent_context_policy": normalize_context_policy(profile.get("context_policy")),
            "agent_review_gate": normalize_review_gate(profile.get("review_gate")),
            "agent_model_settings": normalize_model_settings(profile.get("model_settings")),
            "agent_command_policy": normalize_command_policy(profile.get("command_policy")),
            "agent_studio": agent_state,
        }
        updates: dict[str, Any] = {"metadata": self._conversation_metadata_patch(conversation_id, metadata_patch)}
        primary_model = text_value(
            normalize_model_settings(profile.get("model_settings")).get("primary_model_profile_id")
        )
        if primary_model:
            updates["model"] = primary_model
        conversation = self._update_conversation(conversation_id, updates)
        return {"conversation": conversation, "profile": profile, "surface": surface}

    def activate_team_for_conversation(
        self,
        conversation_id: str,
        team_id: str,
        *,
        reason: str = "manual_team_switch",
    ) -> dict[str, Any]:
        team = self.resolve_team(team_id)
        if team is None:
            raise ValueError("unknown team definition: " + str(team_id))
        company = self.materialize_team(
            team_id=team["id"],
            conversation_id=conversation_id,
        )["company"]
        coordinator = self._team_coordinator_profile(team)
        runtime_profile_id = runtime_profile_id_from(coordinator) if coordinator else ""
        agent_state = self._agent_studio_state_patch(
            conversation_id,
            {
                "surface": "team_agent",
                "active_profile_id": text_value(coordinator.get("id") if coordinator else ""),
                "active_team_id": text_value(team.get("id")),
                "active_fusion_id": "",
                "runtime_profile_id": runtime_profile_id,
                "active_label": text_value(team.get("display_name")),
                "team_member_profile_ids": list(team.get("member_profile_ids") or []),
                "review_gate": {
                    "approved": False,
                    "approved_at": "",
                    "approved_by": "",
                },
                "activated_at": timestamp(),
                "activation_reason": reason,
            },
            activity_entry=self._activity_entry(
                event_type="activation",
                message=f"Team Agent switched to {text_value(team.get('display_name')) or text_value(team.get('id'))}.",
                surface="team_agent",
                target_id=text_value(team.get("id")),
                label=text_value(team.get("display_name")),
                reason=reason,
            ),
        )
        metadata_patch = {
            "profile_id": runtime_profile_id,
            "agent_profile_id": text_value(coordinator.get("id") if coordinator else ""),
            "company_id": text_value(company.get("id")),
            "team_id": text_value(team.get("id")),
            "agent_context_policy": self._effective_context_policy(surface="team_agent", team=team),
            "agent_review_gate": self._effective_review_gate(surface="team_agent", team=team),
            "agent_model_settings": self._effective_model_settings(surface="team_agent", team=team),
            "agent_command_policy": self._effective_command_policy(surface="team_agent", team=team),
            "agent_studio": agent_state,
        }
        updates: dict[str, Any] = {"metadata": self._conversation_metadata_patch(conversation_id, metadata_patch)}
        primary_model = text_value(
            self._effective_model_settings(surface="team_agent", team=team).get("primary_model_profile_id")
        )
        if primary_model:
            updates["model"] = primary_model
        conversation = self._update_conversation(conversation_id, updates)
        return {"conversation": conversation, "team": team, "company": company}

    def activate_fusion_for_conversation(
        self,
        conversation_id: str,
        fusion_id: str,
        *,
        reason: str = "manual_fusion_switch",
    ) -> dict[str, Any]:
        fusion = self.resolve_fusion(fusion_id)
        if fusion is None:
            raise ValueError("unknown fusion definition: " + str(fusion_id))
        company = self.materialize_fusion(
            fusion_id=fusion["id"],
            conversation_id=conversation_id,
        )["company"]
        synthesis = self.resolve_profile(text_value(fusion.get("synthesis_profile_id")) or "")
        runtime_profile_id = runtime_profile_id_from(synthesis or {})
        agent_state = self._agent_studio_state_patch(
            conversation_id,
            {
                "surface": "fusion_agent",
                "active_profile_id": text_value(synthesis.get("id") if synthesis else ""),
                "active_team_id": "",
                "active_fusion_id": text_value(fusion.get("id")),
                "runtime_profile_id": runtime_profile_id,
                "active_label": text_value(fusion.get("display_name")),
                "participant_profile_ids": list(fusion.get("participant_profile_ids") or []),
                "review_gate": {
                    "approved": False,
                    "approved_at": "",
                    "approved_by": "",
                },
                "activated_at": timestamp(),
                "activation_reason": reason,
            },
            activity_entry=self._activity_entry(
                event_type="activation",
                message=f"Fusion Agent switched to {text_value(fusion.get('display_name')) or text_value(fusion.get('id'))}.",
                surface="fusion_agent",
                target_id=text_value(fusion.get("id")),
                label=text_value(fusion.get("display_name")),
                reason=reason,
            ),
        )
        metadata_patch = {
            "profile_id": runtime_profile_id,
            "agent_profile_id": text_value(synthesis.get("id") if synthesis else ""),
            "company_id": text_value(company.get("id")),
            "fusion_id": text_value(fusion.get("id")),
            "agent_context_policy": self._effective_context_policy(surface="fusion_agent", fusion=fusion),
            "agent_review_gate": self._effective_review_gate(surface="fusion_agent", fusion=fusion),
            "agent_model_settings": self._effective_model_settings(surface="fusion_agent", fusion=fusion),
            "agent_command_policy": self._effective_command_policy(surface="fusion_agent", fusion=fusion),
            "agent_studio": agent_state,
        }
        updates: dict[str, Any] = {"metadata": self._conversation_metadata_patch(conversation_id, metadata_patch)}
        primary_model = text_value(
            self._effective_model_settings(surface="fusion_agent", fusion=fusion).get("primary_model_profile_id")
        )
        if primary_model:
            updates["model"] = primary_model
        conversation = self._update_conversation(conversation_id, updates)
        return {"conversation": conversation, "fusion": fusion, "company": company}

    def mark_review_gate_for_conversation(
        self,
        conversation_id: str,
        *,
        approved: bool,
        approved_by: str = "user",
    ) -> dict[str, Any]:
        metadata = self._conversation_metadata(conversation_id)
        state = dict_value(metadata.get("agent_studio"))
        review_gate = dict_value(state.get("review_gate"))
        review_gate.update(
            {
                "approved": bool(approved),
                "approved_at": timestamp() if approved else "",
                "approved_by": text_value(approved_by) if approved else "",
            }
        )
        state["review_gate"] = review_gate
        self._append_activity_entry(
            state,
            self._activity_entry(
                event_type="review_gate",
                message=(
                    f"Review gate approved by {text_value(approved_by) or 'user'}."
                    if approved
                    else "Review gate approval was cleared."
                ),
                surface=text_value(state.get("surface")) or "human",
                approved=approved,
                approved_by=text_value(approved_by),
            ),
        )
        metadata["agent_studio"] = state
        conversation = self._update_conversation(conversation_id, {"metadata": metadata})
        return {"conversation": conversation, "review_gate": review_gate}

    def materialize_team(
        self,
        *,
        team_id: str,
        company_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        team = self.resolve_team(team_id)
        if team is None:
            raise ValueError("unknown team definition: " + str(team_id))
        company_service = CompanyService()
        if conversation_id:
            company = company_service.bootstrap_conversation_company(
                conversation_id,
                metadata={
                    "name": text_value(team.get("display_name")) or "Team Workroom",
                    "team_id": text_value(team.get("id")),
                    "surface": "team_agent",
                    "source": "agent_studio",
                },
            )
        elif company_id:
            company = company_service.get_company(company_id)
            if company is None:
                company = company_service.create_company(
                    {
                        "id": company_id,
                        "name": text_value(team.get("display_name")) or company_id,
                        "description": text_value(team.get("description")),
                        "metadata": {
                            "team_id": text_value(team.get("id")),
                            "surface": "team_agent",
                            "source": "agent_studio",
                        },
                    }
                )
        else:
            raise ValueError("company_id or conversation_id is required")
        if company is None:
            raise ValueError("failed to create team workroom")
        for member_id in team.get("member_profile_ids", []):
            profile = self.resolve_profile(member_id)
            if profile is None:
                continue
            company_service.store.upsert_agent(company["id"], profile_to_company_agent(profile))
        updated_company = company_service.get_company(company["id"]) or company
        return {"company": updated_company, "team": team}

    def materialize_fusion(
        self,
        *,
        fusion_id: str,
        company_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        fusion = self.resolve_fusion(fusion_id)
        if fusion is None:
            raise ValueError("unknown fusion definition: " + str(fusion_id))
        company_service = CompanyService()
        if conversation_id:
            company = company_service.bootstrap_conversation_company(
                conversation_id,
                metadata={
                    "name": text_value(fusion.get("display_name")) or "Fusion Workroom",
                    "fusion_id": text_value(fusion.get("id")),
                    "surface": "fusion_agent",
                    "source": "agent_studio",
                },
            )
        elif company_id:
            company = company_service.get_company(company_id)
            if company is None:
                company = company_service.create_company(
                    {
                        "id": company_id,
                        "name": text_value(fusion.get("display_name")) or company_id,
                        "description": text_value(fusion.get("description")),
                        "metadata": {
                            "fusion_id": text_value(fusion.get("id")),
                            "surface": "fusion_agent",
                            "source": "agent_studio",
                        },
                    }
                )
        else:
            raise ValueError("company_id or conversation_id is required")
        if company is None:
            raise ValueError("failed to create fusion workroom")
        for member_id in fusion.get("participant_profile_ids", []):
            profile = self.resolve_profile(member_id)
            if profile is None:
                continue
            company_service.store.upsert_agent(company["id"], profile_to_company_agent(profile))
        updated_company = company_service.get_company(company["id"]) or company
        return {"company": updated_company, "fusion": fusion}

    def command_guard(
        self,
        command_name: str,
        *,
        conversation_id: str = "",
        profile_id: str = "",
        context: dict[str, Any] | None = None,
        executor_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = text_value(command_name).lower().lstrip("/")
        state = self.selection_state_for_conversation(conversation_id) if conversation_id else {}
        surface = text_value(state.get("surface") or "human")
        policy = self._effective_command_policy(
            surface=surface,
            profile=self.resolve_profile(text_value(profile_id or state.get("active_profile_id")) or ""),
            team=self.resolve_team(text_value(state.get("active_team_id")) or ""),
            fusion=self.resolve_fusion(text_value(state.get("active_fusion_id")) or ""),
        )
        review_gate = self._effective_review_gate(
            surface=surface,
            profile=self.resolve_profile(text_value(profile_id or state.get("active_profile_id")) or ""),
            team=self.resolve_team(text_value(state.get("active_team_id")) or ""),
            fusion=self.resolve_fusion(text_value(state.get("active_fusion_id")) or ""),
        )
        if context and isinstance(context.get("profile_policy"), dict):
            policy = {
                **policy,
                **normalize_command_policy(context["profile_policy"].get("command_policy")),
            }
        resolved_executor_policy = dict_value(executor_policy)
        human_only = bool(resolved_executor_policy.get("human_only"))
        if name in set(DEFAULT_HUMAN_ONLY_COMMANDS) or name in set(policy.get("human_only_commands", [])):
            human_only = True
        if human_only and surface != "human":
            decision = {
                "allowed": False,
                "code": "HUMAN_ONLY_COMMAND",
                "message": f"/{name} is human-only while {surface} is active.",
            }
            self._record_command_activity(conversation_id, state, name, surface, decision)
            return decision
        allow_surfaces = set(resolved_executor_policy.get("allow_surfaces") or policy.get("allow_surfaces") or [])
        if allow_surfaces and surface not in allow_surfaces:
            decision = {
                "allowed": False,
                "code": "COMMAND_SURFACE_BLOCKED",
                "message": f"/{name} is not available while {surface} is active.",
            }
            self._record_command_activity(conversation_id, state, name, surface, decision)
            return decision
        deny_surfaces = set(resolved_executor_policy.get("deny_surfaces") or policy.get("deny_surfaces") or [])
        if surface in deny_surfaces:
            decision = {
                "allowed": False,
                "code": "COMMAND_SURFACE_BLOCKED",
                "message": f"/{name} is not available while {surface} is active.",
            }
            self._record_command_activity(conversation_id, state, name, surface, decision)
            return decision
        if name in set(policy.get("denied_commands", [])):
            decision = {
                "allowed": False,
                "code": "COMMAND_DENIED_BY_PROFILE",
                "message": f"/{name} is blocked by the active agent profile policy.",
            }
            self._record_command_activity(conversation_id, state, name, surface, decision)
            return decision
        if policy.get("restrict_to_allowlist") and name not in set(policy.get("allowed_commands", [])):
            decision = {
                "allowed": False,
                "code": "COMMAND_NOT_ALLOWED",
                "message": f"/{name} is outside the active agent allowlist.",
            }
            self._record_command_activity(conversation_id, state, name, surface, decision)
            return decision
        if (
            review_gate.get("mode") == "blocking"
            and name in set(review_gate.get("gated_commands", []))
            and not bool(dict_value(state.get("review_gate")).get("approved"))
        ):
            reviewer = text_value(review_gate.get("reviewer_profile_id")) or "reviewer"
            decision = {
                "allowed": False,
                "code": "REVIEW_GATE_BLOCKED",
                "message": f"/{name} is blocked until {reviewer} passes the review gate.",
            }
            self._record_command_activity(conversation_id, state, name, surface, decision)
            return decision
        warning = None
        if (
            review_gate.get("mode") == "warning"
            and name in set(review_gate.get("gated_commands", []))
            and not bool(dict_value(state.get("review_gate")).get("approved"))
        ):
            reviewer = text_value(review_gate.get("reviewer_profile_id")) or "reviewer"
            warning = f"/{name} should wait for {reviewer} to pass the review gate."
        decision = {"allowed": True, "warning": warning, "surface": surface}
        if warning:
            self._record_command_activity(conversation_id, state, name, surface, decision)
        return decision

    def selection_state_for_conversation(self, conversation_id: str) -> dict[str, Any]:
        metadata = self._conversation_metadata(conversation_id)
        state = dict_value(metadata.get("agent_studio"))
        if not state:
            return {"surface": "human", "review_gate": {"approved": True}, "activity_log": []}
        state.setdefault("surface", "human")
        state.setdefault("review_gate", {"approved": False})
        state.setdefault("activity_log", [])
        return state

    def _team_coordinator_profile(self, team: dict[str, Any]) -> dict[str, Any] | None:
        lead = self.resolve_profile(text_value(team.get("coordinator_profile_id")) or "")
        if lead is not None:
            return lead
        for member_id in team.get("member_profile_ids", []):
            candidate = self.resolve_profile(member_id)
            if candidate is not None:
                return candidate
        return None

    @staticmethod
    def _merge_shallow(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        return {**base, **{key: value for key, value in overlay.items() if value not in (None, "", [], {})}}

    def _effective_command_policy(
        self,
        *,
        surface: str,
        profile: dict[str, Any] | None = None,
        team: dict[str, Any] | None = None,
        fusion: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = normalize_command_policy({})
        if profile is not None:
            result = self._merge_shallow(result, normalize_command_policy(profile.get("command_policy")))
        if team is not None:
            result = self._merge_shallow(result, normalize_command_policy(team.get("command_policy")))
            lead = self._team_coordinator_profile(team)
            if lead is not None:
                result = self._merge_shallow(result, normalize_command_policy(lead.get("command_policy")))
        if fusion is not None:
            result = self._merge_shallow(result, normalize_command_policy(fusion.get("command_policy")))
            synthesis = self.resolve_profile(text_value(fusion.get("synthesis_profile_id")) or "")
            if synthesis is not None:
                result = self._merge_shallow(result, normalize_command_policy(synthesis.get("command_policy")))
        if surface != "human":
            result["human_only_commands"] = list(
                dict.fromkeys(
                    [*DEFAULT_HUMAN_ONLY_COMMANDS, *result.get("human_only_commands", [])]
                )
            )
        return result

    def _effective_context_policy(
        self,
        *,
        surface: str,
        profile: dict[str, Any] | None = None,
        team: dict[str, Any] | None = None,
        fusion: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = normalize_context_policy({})
        if profile is not None:
            result = self._merge_shallow(result, normalize_context_policy(profile.get("context_policy")))
        if team is not None:
            result = self._merge_shallow(result, normalize_context_policy(team.get("context_policy")))
        if fusion is not None:
            result = self._merge_shallow(result, normalize_context_policy(fusion.get("context_policy")))
        if surface == "fusion_agent":
            result["mode"] = text_value(result.get("mode") or "summary_clone") or "summary_clone"
        return result

    def _effective_model_settings(
        self,
        *,
        surface: str,
        profile: dict[str, Any] | None = None,
        team: dict[str, Any] | None = None,
        fusion: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bundle = self.store.read()
        result = normalize_model_settings(
            dict_value(bundle.get("settings")).get("model_defaults")
        )
        if profile is not None:
            result = self._merge_shallow(result, normalize_model_settings(profile.get("model_settings")))
        if team is not None:
            result = self._merge_shallow(result, normalize_model_settings(team.get("model_settings")))
        if fusion is not None:
            result = self._merge_shallow(result, normalize_model_settings(fusion.get("model_settings")))
        if surface == "fusion_agent" and not text_value(result.get("fusion_model_profile_id")):
            result["fusion_model_profile_id"] = text_value(result.get("primary_model_profile_id"))
        return result

    def _effective_review_gate(
        self,
        *,
        surface: str,
        profile: dict[str, Any] | None = None,
        team: dict[str, Any] | None = None,
        fusion: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = normalize_review_gate({})
        if profile is not None:
            result = self._merge_shallow(result, normalize_review_gate(profile.get("review_gate")))
        if team is not None:
            result = self._merge_shallow(result, normalize_review_gate(team.get("review_gate")))
            lead = self._team_coordinator_profile(team)
            if lead is not None:
                result = self._merge_shallow(result, normalize_review_gate(lead.get("review_gate")))
        if fusion is not None:
            result = self._merge_shallow(result, normalize_review_gate(fusion.get("review_gate")))
        return result

    def _conversation_metadata(self, conversation_id: str) -> dict[str, Any]:
        conversation = ChatStore().get_conversation(text_value(conversation_id))
        if conversation is None:
            raise ValueError("conversation not found: " + str(conversation_id))
        return dict_value(conversation.get("metadata"))

    def _validate_bundle(self, payload: dict[str, Any]) -> None:
        profile_records = self._bundle_records(payload.get("profiles"), label="profiles")
        normalized_profile_ids: list[str] = []
        for record in profile_records:
            self._validate_profile_record(record)
            normalized_profile_ids.append(normalize_registered_profile(record).get("id", ""))
        self._ensure_unique_ids("profiles", normalized_profile_ids)
        known_profile_ids = {
            *[item for item in normalized_profile_ids if item],
            *[text_value(profile.get("id")) for profile in self.list_profiles()],
        }

        team_records = self._bundle_records(payload.get("teams"), label="teams")
        normalized_team_ids: list[str] = []
        for record in team_records:
            self._validate_team_record(record, imported_profile_ids=known_profile_ids)
            normalized_team_ids.append(normalize_team_definition(record).get("id", ""))
        self._ensure_unique_ids("teams", normalized_team_ids)
        known_team_ids = {
            *[item for item in normalized_team_ids if item],
            *[text_value(team.get("id")) for team in self.list_teams()],
        }

        fusion_records = self._bundle_records(payload.get("fusions"), label="fusions")
        normalized_fusion_ids: list[str] = []
        for record in fusion_records:
            self._validate_fusion_record(record, imported_profile_ids=known_profile_ids)
            normalized_fusion_ids.append(normalize_fusion_definition(record).get("id", ""))
        self._ensure_unique_ids("fusions", normalized_fusion_ids)
        known_fusion_ids = {
            *[item for item in normalized_fusion_ids if item],
            *[text_value(fusion.get("id")) for fusion in self.list_fusions()],
        }

        selection_rules = payload.get("selection_rules")
        if selection_rules is not None:
            if not isinstance(selection_rules, list):
                raise ValueError("selection_rules must be a list")
            for index, rule in enumerate(selection_rules):
                if not isinstance(rule, dict):
                    raise ValueError(f"selection_rules[{index}] must be an object")
            self._validate_selection_rules(
                [rule for rule in selection_rules if isinstance(rule, dict)],
                imported_profile_ids=known_profile_ids,
                imported_team_ids=known_team_ids,
                imported_fusion_ids=known_fusion_ids,
            )

    def _validate_profile_record(self, record: dict[str, Any]) -> None:
        raw_id = text_value(
            record.get("id")
            or record.get("profile_id")
            or record.get("registered_profile_id")
            or record.get("name")
        )
        if not raw_id:
            raise ValueError("profile.id is required")
        runtime_id = runtime_profile_id_from(record)
        if not runtime_id:
            raise ValueError(
                f"profile '{raw_id}' requires base_profile_id or runtime_profile_id"
            )

    def _validate_team_record(
        self,
        record: dict[str, Any],
        *,
        imported_profile_ids: set[str] | None = None,
    ) -> None:
        raw_id = text_value(record.get("id") or record.get("team_id") or record.get("name"))
        if not raw_id:
            raise ValueError("team.id is required")
        team = normalize_team_definition(record)
        if not team.get("member_profile_ids"):
            raise ValueError(f"team '{raw_id}' requires at least one member_profile_ids entry")
        coordinator = text_value(team.get("coordinator_profile_id"))
        if coordinator:
            self._validate_profile_reference(
                coordinator,
                field_name="coordinator_profile_id",
                owner_label=f"team '{raw_id}'",
                imported_profile_ids=imported_profile_ids,
            )
        reviewer = text_value(team.get("reviewer_profile_id"))
        if reviewer:
            self._validate_profile_reference(
                reviewer,
                field_name="reviewer_profile_id",
                owner_label=f"team '{raw_id}'",
                imported_profile_ids=imported_profile_ids,
            )
        for member_id in team.get("member_profile_ids", []):
            self._validate_profile_reference(
                member_id,
                field_name="member_profile_ids",
                owner_label=f"team '{raw_id}'",
                imported_profile_ids=imported_profile_ids,
            )

    def _validate_fusion_record(
        self,
        record: dict[str, Any],
        *,
        imported_profile_ids: set[str] | None = None,
    ) -> None:
        raw_id = text_value(record.get("id") or record.get("fusion_id") or record.get("name"))
        if not raw_id:
            raise ValueError("fusion.id is required")
        fusion = normalize_fusion_definition(record)
        participants = fusion.get("participant_profile_ids", [])
        if len(participants) < 2:
            raise ValueError(
                f"fusion '{raw_id}' requires at least two participant_profile_ids entries"
            )
        for participant_id in participants:
            self._validate_profile_reference(
                participant_id,
                field_name="participant_profile_ids",
                owner_label=f"fusion '{raw_id}'",
                imported_profile_ids=imported_profile_ids,
            )
        synthesis = text_value(fusion.get("synthesis_profile_id"))
        if synthesis:
            self._validate_profile_reference(
                synthesis,
                field_name="synthesis_profile_id",
                owner_label=f"fusion '{raw_id}'",
                imported_profile_ids=imported_profile_ids,
            )

    def _validate_selection_rules(
        self,
        rules: list[dict[str, Any]],
        *,
        imported_profile_ids: set[str] | None = None,
        imported_team_ids: set[str] | None = None,
        imported_fusion_ids: set[str] | None = None,
    ) -> None:
        for rule in rules:
            target_id = text_value(
                rule.get("target_id")
                or rule.get("profile_id")
                or rule.get("team_id")
                or rule.get("fusion_id")
            )
            if not target_id:
                raise ValueError("selection rule target_id is required")
            normalized = normalize_selection_rule(rule)
            if not normalized.get("match_terms") and not normalized.get("prompt_contains"):
                raise ValueError(
                    f"selection rule '{text_value(normalized.get('id')) or target_id}' requires match_terms or prompt_contains"
                )
            target_type = text_value(normalized.get("target_type") or "profile")
            if target_type == "profile":
                self._validate_profile_reference(
                    target_id,
                    field_name="target_id",
                    owner_label=f"selection rule '{text_value(normalized.get('id')) or target_id}'",
                    imported_profile_ids=imported_profile_ids,
                )
            elif target_type == "team":
                if target_id not in (imported_team_ids or set()) and self.resolve_team(target_id) is None:
                    raise ValueError(
                        f"selection rule '{text_value(normalized.get('id')) or target_id}' references unknown team '{target_id}'"
                    )
            elif target_type == "fusion":
                if target_id not in (imported_fusion_ids or set()) and self.resolve_fusion(target_id) is None:
                    raise ValueError(
                        f"selection rule '{text_value(normalized.get('id')) or target_id}' references unknown fusion '{target_id}'"
                    )

    def _validate_profile_reference(
        self,
        profile_id: str,
        *,
        field_name: str,
        owner_label: str,
        imported_profile_ids: set[str] | None = None,
    ) -> None:
        cleaned = text_value(profile_id)
        if not cleaned:
            raise ValueError(f"{owner_label} requires {field_name}")
        if cleaned in (imported_profile_ids or set()):
            return
        if self.resolve_profile(cleaned) is not None:
            return
        raise ValueError(f"{owner_label} references unknown profile '{cleaned}' in {field_name}")

    @staticmethod
    def _bundle_records(value: Any, *, label: str) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, dict):
            raw_items = list(value.values())
        elif isinstance(value, list):
            raw_items = value
        else:
            raise ValueError(f"{label} must be a list or object")
        records: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                raise ValueError(f"{label}[{index}] must be an object")
            records.append(item)
        return records

    @staticmethod
    def _ensure_unique_ids(label: str, ids: list[str]) -> None:
        duplicates = sorted({
            item
            for item in ids
            if item and ids.count(item) > 1
        })
        if duplicates:
            raise ValueError(f"duplicate {label} ids are not allowed: {', '.join(duplicates)}")

    def _agent_studio_state_patch(
        self,
        conversation_id: str,
        patch: dict[str, Any],
        *,
        activity_entry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict_value(self._conversation_metadata(conversation_id).get("agent_studio"))
        for key, value in patch.items():
            state[key] = copy.deepcopy(value)
        state.setdefault("activity_log", [])
        if activity_entry:
            self._append_activity_entry(state, activity_entry)
        return state

    def _record_command_activity(
        self,
        conversation_id: str | None,
        state: dict[str, Any],
        name: str,
        surface: str,
        decision: dict[str, Any],
    ) -> None:
        cleaned_conversation_id = text_value(conversation_id)
        if not cleaned_conversation_id:
            return
        entry_type = "command_denied" if decision.get("allowed") is False else "command_warning"
        message = text_value(decision.get("message") or decision.get("warning"))
        if not message:
            return
        metadata = self._conversation_metadata(cleaned_conversation_id)
        current_state = dict_value(metadata.get("agent_studio")) or dict_value(state)
        self._append_activity_entry(
            current_state,
            self._activity_entry(
                event_type=entry_type,
                message=message,
                surface=surface,
                command=name,
                reason_code=text_value(decision.get("code")),
            ),
        )
        metadata["agent_studio"] = current_state
        self._update_conversation(cleaned_conversation_id, {"metadata": metadata})

    @staticmethod
    def _activity_entry(
        *,
        event_type: str,
        message: str,
        surface: str = "",
        target_id: str = "",
        label: str = "",
        reason: str = "",
        reason_code: str = "",
        command: str = "",
        approved: bool | None = None,
        approved_by: str = "",
    ) -> dict[str, Any]:
        event_id = safe_id(
            "agent-studio-event",
            f"{event_type}-{surface}-{target_id or command}-{timestamp()}",
        )
        entry = {
            "id": event_id,
            "type": text_value(event_type) or "event",
            "message": text_value(message),
            "surface": text_value(surface),
            "target_id": text_value(target_id),
            "label": text_value(label),
            "reason": text_value(reason),
            "reason_code": text_value(reason_code),
            "command": text_value(command),
            "created_at": timestamp(),
        }
        if approved is not None:
            entry["approved"] = bool(approved)
        if approved_by:
            entry["approved_by"] = text_value(approved_by)
        return entry

    @staticmethod
    def _append_activity_entry(state: dict[str, Any], entry: dict[str, Any]) -> None:
        activity_log = [
            dict_value(item)
            for item in (state.get("activity_log") or [])
            if isinstance(item, dict)
        ]
        activity_log.append(dict_value(entry))
        state["activity_log"] = activity_log[-25:]

    def _conversation_metadata_patch(
        self,
        conversation_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        current = self._conversation_metadata(conversation_id)
        merged = copy.deepcopy(current)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **copy.deepcopy(value)}
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    def _update_conversation(self, conversation_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        updated = ChatStore().update_conversation(text_value(conversation_id), updates)
        if updated is None:
            raise ValueError("conversation not found: " + str(conversation_id))
        return updated
