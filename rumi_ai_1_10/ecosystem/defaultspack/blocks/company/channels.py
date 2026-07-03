from blocks._common import ok, error
from domain.company.store import CompanyStore

from ._helpers import company_id_from, invalid, missing_company, require_dict, subagent_team_write_denied


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "list").lower()
    store = CompanyStore()
    try:
        if action == "list":
            channels = store.list_channels(company_id)
            if channels is None:
                return missing_company(company_id)
            return ok({"channels": channels, "total": len(channels)})
        if action == "get":
            channel_id = input_data.get("channel_id") or input_data.get("id")
            if not channel_id:
                return invalid("channel_id is required")
            channel = store.get_channel(company_id, str(channel_id))
            if channel is None:
                return error("channel not found: " + str(channel_id), "NOT_FOUND")
            return ok(channel)
        if action in {"upsert", "create", "update"}:
            blocked = subagent_team_write_denied(company_id)
            if blocked is not None:
                return blocked
            channel = input_data.get("channel")
            if channel is None:
                channel = {key: value for key, value in input_data.items() if key not in {"company_id", "action"}}
            if not isinstance(channel, dict):
                return invalid("channel must be a dict")
            updated = store.upsert_channel(company_id, channel)
            if updated is None:
                return missing_company(company_id)
            return ok(updated)
        if action in {"delete", "remove"}:
            blocked = subagent_team_write_denied(company_id)
            if blocked is not None:
                return blocked
            channel_id = input_data.get("channel_id") or input_data.get("id")
            if not channel_id:
                return invalid("channel_id is required")
            deleted = store.delete_channel(company_id, str(channel_id))
            if not deleted:
                return error("channel not found: " + str(channel_id), "NOT_FOUND")
            return ok({"deleted": True, "channel_id": str(channel_id)})
        return invalid("unsupported channels action: " + action)
    except Exception as exc:
        return error("company channels failed: " + str(exc), "COMPANY_CHANNELS_ERROR")
