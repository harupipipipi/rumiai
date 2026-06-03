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
        return ok({"runs": [_with_agent_run_preview(run) for run in runs], "total": len(runs)})
    except Exception as exc:
        return error("company runs failed: " + str(exc), "COMPANY_RUNS_ERROR")


def _with_agent_run_preview(run: dict) -> dict:
    run_id = str(run.get("run_id") or "").strip()
    if not run_id:
        return run
    try:
        from domain.agent_runtime.run_store import AgentRunStore

        agent_run = AgentRunStore().get_run(run_id)
    except Exception:
        agent_run = None
    if not isinstance(agent_run, dict):
        return run
    preview = _result_preview(agent_run.get("result_json"))
    enriched = dict(run)
    enriched["agent_run"] = {
        "status": agent_run.get("status"),
        "model": agent_run.get("model"),
        "result_preview": preview,
        "error": agent_run.get("error"),
        "updated_at": agent_run.get("updated_at"),
    }
    return enriched


def _result_preview(value) -> str:
    text = _result_text(value).strip()
    if len(text) <= 240:
        return text
    return text[:237].rstrip() + "..."


def _result_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type") == "thinking" or item.get("thinking"):
                    continue
                parts.append(str(item.get("text") or item.get("content") or ""))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "result", "assistant_text", "message"):
            if value.get(key):
                return _result_text(value.get(key))
    return ""
