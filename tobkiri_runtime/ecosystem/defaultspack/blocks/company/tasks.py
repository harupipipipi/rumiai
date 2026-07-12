from blocks._common import ok, error
from domain.company.task_store import CompanyTaskStore

from ._helpers import company_id_from, invalid, limit_offset, missing_company, require_dict, subagent_team_write_denied


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "list").lower()
    store = CompanyTaskStore()
    try:
        if action == "list":
            limit, offset = limit_offset(input_data)
            result = store.list(
                company_id,
                status=input_data.get("status"),
                target_agent_id=input_data.get("target_agent_id"),
                limit=limit,
                offset=offset,
            )
            if result is None:
                return missing_company(company_id)
            tasks, total = result
            return ok({"tasks": tasks, "total": total})
        if action == "get":
            task_id = input_data.get("task_id") or input_data.get("id")
            if not task_id:
                return invalid("task_id is required")
            task = store.get(company_id, str(task_id))
            if task is None:
                return error("task not found: " + str(task_id), "NOT_FOUND")
            return ok(task)
        if action in {"create", "add"}:
            blocked = subagent_team_write_denied(company_id)
            if blocked is not None:
                return blocked
            title = input_data.get("title")
            if not title:
                return invalid("title is required")
            target_agent_ids = input_data.get("target_agent_ids")
            if target_agent_ids is not None and not isinstance(target_agent_ids, list):
                return invalid("target_agent_ids must be a list")
            task = store.create(
                company_id,
                title=str(title),
                description=str(input_data.get("description") or ""),
                target_agent_ids=target_agent_ids,
                source=str(input_data.get("source") or "manual"),
                metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else None,
            )
            if task is None:
                return missing_company(company_id)
            return ok(task)
        if action == "update":
            blocked = subagent_team_write_denied(company_id)
            if blocked is not None:
                return blocked
            task_id = input_data.get("task_id") or input_data.get("id")
            updates = input_data.get("updates")
            if not task_id:
                return invalid("task_id is required")
            if not isinstance(updates, dict):
                return invalid("updates must be a dict")
            task = store.update(company_id, str(task_id), updates)
            if task is None:
                return error("task not found: " + str(task_id), "NOT_FOUND")
            return ok(task)
        if action in {"delete", "remove"}:
            blocked = subagent_team_write_denied(company_id)
            if blocked is not None:
                return blocked
            task_id = input_data.get("task_id") or input_data.get("id")
            if not task_id:
                return invalid("task_id is required")
            if not store.delete(company_id, str(task_id)):
                return error("task not found: " + str(task_id), "NOT_FOUND")
            return ok({"deleted": True, "task_id": str(task_id)})
        return invalid("unsupported tasks action: " + action)
    except Exception as exc:
        return error("company tasks failed: " + str(exc), "COMPANY_TASKS_ERROR")
