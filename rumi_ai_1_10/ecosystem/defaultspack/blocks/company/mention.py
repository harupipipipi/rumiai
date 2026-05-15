from blocks._common import ok, error
from domain.company.mention import CompanyMentionService
from domain.company.service import CompanyService

from ._helpers import company_id_from, invalid, missing_company, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    action = str(input_data.get("action") or "message").lower()
    content = str(input_data.get("content") or input_data.get("message") or "")
    if not content:
        return invalid("content is required")
    try:
        if action == "resolve":
            result = CompanyMentionService().resolve(company_id, content)
            if result is None:
                return missing_company(company_id)
            return ok(result)
        result = CompanyService().mention(company_id, input_data)
        if result is None:
            return missing_company(company_id)
        return ok(result)
    except Exception as exc:
        return error("company mention failed: " + str(exc), "COMPANY_MENTION_ERROR")
