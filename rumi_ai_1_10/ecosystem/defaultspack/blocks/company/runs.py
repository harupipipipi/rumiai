from blocks._common import ok, error
from domain.company.runtime_store import CompanyRuntimeStore

from ._helpers import company_id_from, invalid, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    limit = input_data.get("limit", 100)
    if not isinstance(limit, int) or limit < 1:
        limit = 100
    try:
        runs = CompanyRuntimeStore().list_run_links(
            company_id,
            agent_id=input_data.get("agent_id"),
            task_id=input_data.get("task_id"),
            status=input_data.get("status"),
            limit=limit,
        )
        return ok({"runs": runs, "total": len(runs)})
    except Exception as exc:
        return error("company runs failed: " + str(exc), "COMPANY_RUNS_ERROR")
