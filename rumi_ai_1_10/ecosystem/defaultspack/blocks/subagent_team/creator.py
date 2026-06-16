from blocks._common import ok, error
from domain.company.store import CompanyStore
from domain.subagent_team.service import SubagentTeamService

from ._helpers import company_id_from, denied, invalid, is_denied, missing_team, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    action = str(input_data.get("action") or "preview").lower()
    service = SubagentTeamService()
    try:
        if action in {"status", "bootstrap", "ensure"}:
            result = service.ensure_team(input_data)
            return ok(result)
        company_id = company_id_from(input_data)
        if not company_id:
            return invalid("company_id is required")
        if action == "test":
            preview = service.creator_preview(company_id, {**input_data, "action": "preview"})
            if preview is None:
                return missing_team(company_id)
            return ok({"ok": True, "preview": preview})
        if action == "settings":
            settings = CompanyStore().get_settings(company_id)
            if settings is None:
                return missing_team(company_id)
            return ok({"settings": settings.get("subagent_team", {}) if isinstance(settings, dict) else {}})
        if action == "update_settings":
            settings = input_data.get("settings")
            if not isinstance(settings, dict):
                return invalid("settings must be a dict")
            rich_keys = {"rich_enabled", "enabled", "rich_agent_cap", "cap"}
            if any(key in settings for key in rich_keys):
                rich = service.update_rich_state(
                    company_id,
                    {
                        **settings,
                        "actor_id": input_data.get("actor_id") or input_data.get("sender_id"),
                        "channel_id": input_data.get("channel_id"),
                    },
                    context=context if isinstance(context, dict) else {},
                )
                if is_denied(rich):
                    return denied(rich)
                if rich is None:
                    return missing_team(company_id)
                settings = {key: value for key, value in settings.items() if key not in rich_keys}
                if not settings:
                    return ok({"settings": (CompanyStore().get_settings(company_id) or {}).get("subagent_team", {})})
            store = CompanyStore()
            current = store.get_settings(company_id) or {}
            updated = store.update_settings(
                company_id,
                {**current, "subagent_team": {**(current.get("subagent_team") if isinstance(current.get("subagent_team"), dict) else {}), **settings}},
            )
            if updated is None:
                return missing_team(company_id)
            return ok({"settings": updated.get("subagent_team", {})})
        if action == "preview":
            preview = service.creator_preview(company_id, input_data)
            if preview is None:
                return missing_team(company_id)
            return ok(preview)
        if action in {"request", "submit", "send", "create_goal", "goal"}:
            result = service.creator_request(company_id, input_data, context=context if isinstance(context, dict) else {})
            if is_denied(result):
                return denied(result)
            if result is None:
                return missing_team(company_id)
            return ok(result)
        return invalid("unsupported creator action: " + action)
    except Exception as exc:
        return error("subagent team creator failed: " + str(exc), "SUBAGENT_TEAM_CREATOR_ERROR")
