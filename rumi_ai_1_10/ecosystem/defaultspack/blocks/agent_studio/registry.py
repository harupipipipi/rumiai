from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import error, ok
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.agent_studio.service import AgentStudioService


def run(input_data, context):
    service = AgentStudioService()
    method = (input_data or {}).get("_method", "GET").upper()
    action = str((input_data or {}).get("action") or "manifest").strip().lower()
    try:
        if method == "GET" or action in {"manifest", "list"}:
            return ok(service.manifest())
        if method != "POST":
            return error("unsupported method", "METHOD_NOT_ALLOWED")

        if action == "upsert_profile":
            profile = (input_data or {}).get("profile")
            if not isinstance(profile, dict):
                return error("profile must be a dict", "INVALID_INPUT")
            return ok(service.upsert_profile(profile))
        if action == "delete_profile":
            profile_id = str((input_data or {}).get("profile_id") or "").strip()
            if not profile_id:
                return error("profile_id is required", "INVALID_INPUT")
            return ok({"deleted": service.delete_profile(profile_id), "profile_id": profile_id})

        if action == "upsert_team":
            team = (input_data or {}).get("team")
            if not isinstance(team, dict):
                return error("team must be a dict", "INVALID_INPUT")
            return ok(service.upsert_team(team))
        if action == "delete_team":
            team_id = str((input_data or {}).get("team_id") or "").strip()
            if not team_id:
                return error("team_id is required", "INVALID_INPUT")
            return ok({"deleted": service.delete_team(team_id), "team_id": team_id})

        if action == "upsert_fusion":
            fusion = (input_data or {}).get("fusion")
            if not isinstance(fusion, dict):
                return error("fusion must be a dict", "INVALID_INPUT")
            return ok(service.upsert_fusion(fusion))
        if action == "delete_fusion":
            fusion_id = str((input_data or {}).get("fusion_id") or "").strip()
            if not fusion_id:
                return error("fusion_id is required", "INVALID_INPUT")
            return ok({"deleted": service.delete_fusion(fusion_id), "fusion_id": fusion_id})

        if action == "set_selection_rules":
            rules = (input_data or {}).get("selection_rules")
            if not isinstance(rules, list):
                return error("selection_rules must be a list", "INVALID_INPUT")
            return ok({"selection_rules": service.replace_selection_rules(rules)})
        if action == "preview_selection":
            return ok({
                "decision": service.preview_selection(
                    str((input_data or {}).get("prompt") or ""),
                    conversation_id=str((input_data or {}).get("conversation_id") or "").strip(),
                )
            })
        if action == "auto_select_for_conversation":
            conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
            if not conversation_id:
                return error("conversation_id is required", "INVALID_INPUT")
            return ok(
                service.auto_select_for_conversation(
                    conversation_id,
                    str((input_data or {}).get("prompt") or ""),
                )
            )

        if action == "update_settings":
            settings = (input_data or {}).get("settings")
            if not isinstance(settings, dict):
                return error("settings must be a dict", "INVALID_INPUT")
            return ok({"settings": service.update_settings(settings)})

        if action == "import_bundle":
            bundle = (input_data or {}).get("bundle")
            if not isinstance(bundle, dict):
                return error("bundle must be a dict", "INVALID_INPUT")
            return ok(service.import_bundle(bundle, merge=bool((input_data or {}).get("merge"))))
        if action == "export_bundle":
            return ok(service.export_bundle())

        if action == "activate_profile":
            conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
            profile_id = str((input_data or {}).get("profile_id") or "").strip()
            if not conversation_id or not profile_id:
                return error("conversation_id and profile_id are required", "INVALID_INPUT")
            return ok(
                service.activate_profile_for_conversation(
                    conversation_id,
                    profile_id,
                    surface=str((input_data or {}).get("surface") or "mode_agent"),
                    reason=str((input_data or {}).get("reason") or "manual_profile_switch"),
                )
            )
        if action == "activate_team":
            conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
            team_id = str((input_data or {}).get("team_id") or "").strip()
            if not conversation_id or not team_id:
                return error("conversation_id and team_id are required", "INVALID_INPUT")
            return ok(
                service.activate_team_for_conversation(
                    conversation_id,
                    team_id,
                    reason=str((input_data or {}).get("reason") or "manual_team_switch"),
                )
            )
        if action == "activate_fusion":
            conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
            fusion_id = str((input_data or {}).get("fusion_id") or "").strip()
            if not conversation_id or not fusion_id:
                return error("conversation_id and fusion_id are required", "INVALID_INPUT")
            return ok(
                service.activate_fusion_for_conversation(
                    conversation_id,
                    fusion_id,
                    reason=str((input_data or {}).get("reason") or "manual_fusion_switch"),
                )
            )
        if action == "mark_review_gate":
            conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
            if not conversation_id:
                return error("conversation_id is required", "INVALID_INPUT")
            approved = bool((input_data or {}).get("approved"))
            return ok(
                service.mark_review_gate_for_conversation(
                    conversation_id,
                    approved=approved,
                    approved_by=str((input_data or {}).get("approved_by") or "user"),
                )
            )

        if action == "materialize_team":
            team_id = str((input_data or {}).get("team_id") or "").strip()
            if not team_id:
                return error("team_id is required", "INVALID_INPUT")
            return ok(
                service.materialize_team(
                    team_id=team_id,
                    company_id=(input_data or {}).get("company_id"),
                    conversation_id=(input_data or {}).get("conversation_id"),
                )
            )
        if action == "materialize_fusion":
            fusion_id = str((input_data or {}).get("fusion_id") or "").strip()
            if not fusion_id:
                return error("fusion_id is required", "INVALID_INPUT")
            return ok(
                service.materialize_fusion(
                    fusion_id=fusion_id,
                    company_id=(input_data or {}).get("company_id"),
                    conversation_id=(input_data or {}).get("conversation_id"),
                )
            )
        return error("unsupported action: " + action, "INVALID_ACTION")
    except Exception as exc:
        return error("agent studio failed: " + str(exc), "AGENT_STUDIO_ERROR")
