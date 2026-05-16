from blocks._common import ok, error
from domain.company.agent_store import CompanyAgentStore

from ._helpers import company_id_from, invalid, missing_company, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "list").lower()
    store = CompanyAgentStore()
    try:
        if action == "list":
            agents = store.list(company_id)
            if agents is None:
                return missing_company(company_id)
            return ok({"agents": agents, "total": len(agents)})
        if action == "get":
            agent_id = input_data.get("agent_id")
            if not agent_id:
                return invalid("agent_id is required")
            agent = store.get(company_id, str(agent_id))
            if agent is None:
                return error("agent not found: " + str(agent_id), "NOT_FOUND")
            return ok(agent)
        if action in {"upsert", "update", "create"}:
            agent = input_data.get("agent")
            if not isinstance(agent, dict):
                return invalid("agent must be a dict")
            updated = store.upsert(company_id, agent)
            if updated is None:
                return missing_company(company_id)
            return ok(updated)
        if action in {"remove", "delete"}:
            agent_id = input_data.get("agent_id")
            if not agent_id:
                return invalid("agent_id is required")
            removed = store.remove(company_id, str(agent_id))
            if not removed:
                return error("agent not found: " + str(agent_id), "NOT_FOUND")
            return ok({"deleted": True, "agent_id": str(agent_id)})
        return invalid("unsupported agents action: " + action)
    except Exception as exc:
        return error("company agents failed: " + str(exc), "COMPANY_AGENTS_ERROR")
