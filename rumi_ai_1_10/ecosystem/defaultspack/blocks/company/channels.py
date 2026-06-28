from blocks._common import ok, error
from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.store import CompanyStore

from ._helpers import company_id_from, invalid, missing_company, require_dict


def _with_runtime_counts(company_id, channel, runtime_store):
    enriched = dict(channel)
    channel_id = str(enriched.get("id") or enriched.get("channel_id") or "ops-company")
    messages, total = runtime_store.list_messages(company_id, channel_id=channel_id, limit=1, offset=0)
    enriched["message_count"] = max(int(enriched.get("message_count", 0) or 0), int(total))
    if total:
        latest, _latest_total = runtime_store.list_messages(
            company_id,
            channel_id=channel_id,
            limit=1,
            offset=max(int(total) - 1, 0),
        )
        if latest:
            enriched["last_message_at"] = latest[0].get("created_at") or enriched.get("last_message_at")
        elif messages:
            enriched["last_message_at"] = messages[0].get("created_at") or enriched.get("last_message_at")
    return enriched


def _runtime_channel(channel_id):
    return {
        "id": str(channel_id),
        "name": str(channel_id),
        "description": "Runtime channel",
        "visibility": "team",
        "members": [],
    }


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "list").lower()
    store = CompanyStore()
    runtime_store = CompanyRuntimeStore()
    try:
        if action == "list":
            channels = store.list_channels(company_id)
            if channels is None:
                return missing_company(company_id)
            channels = [_with_runtime_counts(company_id, channel, runtime_store) for channel in channels]
            seen = {str(channel.get("id") or channel.get("channel_id") or "") for channel in channels}
            for channel_id in runtime_store.list_channel_ids(company_id):
                if channel_id not in seen:
                    channels.append(_with_runtime_counts(company_id, _runtime_channel(channel_id), runtime_store))
                    seen.add(channel_id)
            return ok({"channels": channels, "total": len(channels)})
        if action == "get":
            channel_id = input_data.get("channel_id") or input_data.get("id")
            if not channel_id:
                return invalid("channel_id is required")
            if store.get_company(company_id) is None:
                return missing_company(company_id)
            channel = store.get_channel(company_id, str(channel_id))
            if channel is None:
                runtime_ids = set(runtime_store.list_channel_ids(company_id))
                if str(channel_id) not in runtime_ids:
                    return error("channel not found: " + str(channel_id), "NOT_FOUND")
                channel = _runtime_channel(channel_id)
            return ok(_with_runtime_counts(company_id, channel, runtime_store))
        if action in {"upsert", "create", "update"}:
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
