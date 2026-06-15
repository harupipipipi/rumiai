from blocks._common import ok, error
from domain.subagent_team.service import SubagentTeamService

from ._helpers import company_id_from, invalid, missing_team, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "list").lower()
    service = SubagentTeamService()
    try:
        if action == "list":
            channels = service.list_channels(company_id)
            if channels is None:
                return missing_team(company_id)
            return ok({"channels": channels, "total": len(channels)})
        if action == "get":
            channel_id = input_data.get("channel_id") or input_data.get("id")
            if not channel_id:
                return invalid("channel_id is required")
            channel = service.get_channel(company_id, str(channel_id))
            if channel is None:
                return error("channel not found: " + str(channel_id), "NOT_FOUND")
            return ok(channel)
        if action in {"create", "update", "upsert"}:
            channel = input_data.get("channel")
            if channel is None:
                channel = {key: value for key, value in input_data.items() if key not in {"company_id", "action"}}
            if not isinstance(channel, dict):
                return invalid("channel must be a dict")
            updated = service.upsert_channel(
                company_id,
                channel,
                actor_id=str(input_data.get("actor_id") or "creator"),
            )
            if updated is None:
                return missing_team(company_id)
            return ok(updated)
        if action in {"archive", "delete", "remove"}:
            channel_id = input_data.get("channel_id") or input_data.get("id")
            if not channel_id:
                return invalid("channel_id is required")
            archived = service.archive_channel(
                company_id,
                str(channel_id),
                actor_id=str(input_data.get("actor_id") or "creator"),
            )
            if archived is None:
                return error("channel not found: " + str(channel_id), "NOT_FOUND")
            return ok({"archived": True, "channel": archived})
        if action == "join":
            channel_id = input_data.get("channel_id") or input_data.get("id")
            member_id = str(input_data.get("member_id") or input_data.get("agent_id") or input_data.get("sender_id") or "user")
            if not channel_id:
                return invalid("channel_id is required")
            channel = service.get_channel(company_id, str(channel_id))
            if channel is None:
                return error("channel not found: " + str(channel_id), "NOT_FOUND")
            members = [str(item) for item in channel.get("members", [])]
            if member_id not in members:
                members.append(member_id)
            updated = service.upsert_channel(
                company_id,
                {**channel, "members": members},
                actor_id=member_id,
            )
            return ok(updated)
        if action in {"check", "channel.check"}:
            check = service.channel_check(company_id, input_data)
            if check is None:
                return missing_team(company_id)
            return ok(check)
        return invalid("unsupported channels action: " + action)
    except Exception as exc:
        return error("subagent team channels failed: " + str(exc), "SUBAGENT_TEAM_CHANNELS_ERROR")
