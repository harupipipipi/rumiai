from blocks._common import ok, error
from domain.company.service import CompanyService

from ._helpers import company_id_from, invalid, missing_company, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    company_id = company_id_from(input_data)
    if not company_id:
        return invalid("company_id is required")
    updates = input_data.get("updates")
    if updates is None:
        updates = {key: value for key, value in input_data.items() if key not in {"id", "company_id"}}
    if not isinstance(updates, dict):
        return invalid("updates must be a dict")
    try:
        company = CompanyService().update_company(company_id, updates)
        if company is None:
            return missing_company(company_id)
        return ok(company)
    except Exception as exc:
        return error("company update failed: " + str(exc), "COMPANY_UPDATE_ERROR")
