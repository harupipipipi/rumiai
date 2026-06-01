from blocks._common import ok, error
from domain.company.message_router import CompanySlackRuntime
from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.store import CompanyStore

from ._helpers import company_id_from, invalid, limit_offset, missing_company, require_dict


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
            limit, offset = limit_offset(input_data)
            if store.get_company(company_id) is None:
                return missing_company(company_id)
            result = runtime_store.list_messages(
                company_id,
                channel_id=input_data.get("channel_id"),
                thread_id=input_data.get("thread_id"),
                limit=limit,
                offset=offset,
            )
            messages, total = result
            return ok({"messages": messages, "total": total})
        if action == "get":
            message_id = input_data.get("message_id") or input_data.get("id")
            if not message_id:
                return invalid("message_id is required")
            message = runtime_store.get_message(str(message_id))
            if message is None:
                return error("message not found: " + str(message_id), "NOT_FOUND")
            return ok(message)
        if action in {"add", "create"}:
            content = input_data.get("content")
            if not content:
                return invalid("content is required")
            result = CompanySlackRuntime(company_store=store, runtime_store=runtime_store).post_message(
                company_id,
                content=str(content),
                sender_id=str(input_data.get("sender_id") or "user"),
                channel_id=str(input_data.get("channel_id") or "ops-company"),
                thread_id=input_data.get("thread_id"),
                target_agent_ids=input_data.get("target_agent_ids") if isinstance(input_data.get("target_agent_ids"), list) else None,
                metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else None,
                context=context if isinstance(context, dict) else {},
            )
            if result is None:
                return missing_company(company_id)
            return ok(result)
        return invalid("unsupported messages action: " + action)
    except Exception as exc:
        return error("company messages failed: " + str(exc), "COMPANY_MESSAGES_ERROR")
