from blocks._common import ok, error
from domain.company.models import DEFAULT_CHANNEL_ID
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
    runtime_store = CompanyRuntimeStore()
    try:
        if CompanyStore().get_company(company_id) is None:
            return missing_company(company_id)
        if action == "list":
            limit, offset = limit_offset(input_data)
            threads, total = runtime_store.list_threads(
                company_id,
                channel_id=input_data.get("channel_id"),
                limit=limit,
                offset=offset,
            )
            return ok({"threads": threads, "total": total})
        if action == "get":
            thread_id = input_data.get("thread_id") or input_data.get("id")
            if not thread_id:
                return invalid("thread_id is required")
            thread = runtime_store.get_thread(str(thread_id))
            if thread is None or thread.get("company_id") != company_id:
                return error("thread not found: " + str(thread_id), "NOT_FOUND")
            return ok(thread)
        if action in {"create", "add"}:
            thread = runtime_store.ensure_thread(
                company_id,
                channel_id=str(input_data.get("channel_id") or DEFAULT_CHANNEL_ID),
                thread_id=input_data.get("thread_id"),
                title=str(input_data.get("title") or ""),
                metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else None,
            )
            return ok(thread)
        return invalid("unsupported threads action: " + action)
    except Exception as exc:
        return error("company threads failed: " + str(exc), "COMPANY_THREADS_ERROR")
