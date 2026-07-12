from blocks._common import ok, error
from domain.company.runtime_store import CompanyRuntimeStore
from domain.company.summary_worker import CompanySummaryWorker

from ._helpers import company_id_from, invalid, limit_offset, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "list").lower()
    store = CompanyRuntimeStore()
    try:
        if action == "list":
            limit, offset = limit_offset(input_data)
            summaries, total = store.list_summaries(
                company_id,
                scope_type=input_data.get("scope_type"),
                dirty=input_data.get("dirty") if isinstance(input_data.get("dirty"), bool) else None,
                limit=limit,
                offset=offset,
            )
            return ok({"summaries": summaries, "total": total})
        if action in {"refresh", "summarize"}:
            scope_type = str(input_data.get("scope_type") or "").strip()
            scope_id = str(input_data.get("scope_id") or "").strip()
            if not scope_type:
                return invalid("scope_type is required")
            if not scope_id:
                return invalid("scope_id is required")
            return ok(CompanySummaryWorker(runtime_store=store).summarize_scope(company_id, scope_type, scope_id))
        if action in {"process_dirty", "dirty"}:
            limit = input_data.get("limit", 25)
            if not isinstance(limit, int) or limit < 1:
                limit = 25
            return ok({"summaries": CompanySummaryWorker(runtime_store=store).process_dirty(company_id, limit=limit)})
        return invalid("unsupported summary action: " + action)
    except Exception as exc:
        return error("company summary failed: " + str(exc), "COMPANY_SUMMARY_ERROR")
