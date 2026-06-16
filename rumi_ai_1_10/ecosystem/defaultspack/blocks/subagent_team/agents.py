from blocks._common import ok, error
from domain.subagent_team.service import SubagentTeamService

from ._helpers import company_id_from, denied, invalid, is_denied, missing_team, require_dict


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
            agents = service.list_agents(company_id)
            if agents is None:
                return missing_team(company_id)
            return ok({"agents": agents, "total": len(agents)})
        if action == "get":
            agent_id = input_data.get("agent_id") or input_data.get("id")
            if not agent_id:
                return invalid("agent_id is required")
            agent = service.get_agent(company_id, str(agent_id))
            if agent is None:
                return error("agent not found: " + str(agent_id), "NOT_FOUND")
            return ok(agent)
        if action in {"create", "update", "upsert"}:
            agent = input_data.get("agent")
            if agent is None:
                agent = {key: value for key, value in input_data.items() if key not in {"company_id", "action"}}
            if not isinstance(agent, dict):
                return invalid("agent must be a dict")
            updated = service.creator_request(
                company_id,
                {
                    **input_data,
                    "action": "create_agent" if action == "create" else "create_agent",
                    "agent": agent,
                    "team_size": 1,
                    "create_channel": bool(input_data.get("create_channel", False)),
                },
                context=context if isinstance(context, dict) else {},
            )
            if is_denied(updated):
                return denied(updated)
            if updated is None:
                return missing_team(company_id)
            return ok(updated)
        if action in {"archive", "delete", "remove"}:
            agent_id = input_data.get("agent_id") or input_data.get("short_id") or input_data.get("id")
            if not agent_id:
                return invalid("agent_id is required")
            agent_id = _resolve_agent_id(service, company_id, str(agent_id))
            archived = service.archive_agent(
                company_id,
                str(agent_id),
                actor_id=str(input_data.get("actor_id") or "creator"),
            )
            if archived is None:
                return error("agent not found: " + str(agent_id), "NOT_FOUND")
            return ok({"archived": True, "agent": archived})
        if action in {"pause", "resume"}:
            agent_id = input_data.get("agent_id") or input_data.get("short_id") or input_data.get("id")
            if not agent_id:
                return invalid("agent_id is required")
            agent_id = _resolve_agent_id(service, company_id, str(agent_id))
            agent = service.get_agent(company_id, str(agent_id))
            if agent is None:
                return error("agent not found: " + str(agent_id), "NOT_FOUND")
            updated = service.upsert_agent(
                company_id,
                {**agent, "status": "paused" if action == "pause" else "idle"},
                actor_id=str(input_data.get("actor_id") or "creator"),
            )
            return ok(updated)
        return invalid("unsupported agents action: " + action)
    except Exception as exc:
        return error("subagent team agents failed: " + str(exc), "SUBAGENT_TEAM_AGENTS_ERROR")


def _resolve_agent_id(service, company_id: str, value: str) -> str:
    for agent in service.list_agents(company_id) or []:
        if value in {
            str(agent.get("agent_id") or ""),
            str(agent.get("id") or ""),
            str(agent.get("short_id") or ""),
            str((agent.get("metadata") or {}).get("short_id") if isinstance(agent.get("metadata"), dict) else ""),
        }:
            return str(agent.get("agent_id") or agent.get("id") or value)
    return value
