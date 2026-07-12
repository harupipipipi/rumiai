from blocks._common import ok, error
from domain.company.runtime_store import CompanyRuntimeStore

from ._helpers import company_id_from, invalid, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    agent_id = input_data.get("agent_id")
    if not company_id:
        return invalid("company_id is required")
    if not agent_id:
        return invalid("agent_id is required")
    action = str(input_data.get("action") or "list").lower()
    limit = input_data.get("limit", 100)
    if not isinstance(limit, int) or limit < 1:
        limit = 100
    store = CompanyRuntimeStore()
    try:
        if action == "list":
            items = store.list_inbox(
                company_id,
                agent_id=str(agent_id),
                status=input_data.get("status"),
                kind=input_data.get("kind"),
                limit=limit,
            )
            return ok({"inbox": items, "total": len(items)})
        if action == "consume":
            inbox_id = input_data.get("inbox_id") or input_data.get("id")
            if not inbox_id:
                return invalid("inbox_id is required")
            current = store.get_inbox_item(str(inbox_id))
            if current is None or current.get("company_id") != company_id or current.get("agent_id") != str(agent_id):
                return error("inbox item not found: " + str(inbox_id), "NOT_FOUND")
            item = store.update_inbox_item(
                str(inbox_id),
                {
                    "status": "consumed",
                    "metadata": {
                        "consumed_by": str(agent_id),
                    },
                },
            )
            return ok(item)
        return invalid("unsupported inbox action: " + action)
    except Exception as exc:
        return error("company inbox failed: " + str(exc), "COMPANY_INBOX_ERROR")
