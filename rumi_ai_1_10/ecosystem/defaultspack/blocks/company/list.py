from blocks._common import ok, error
from domain.company.service import CompanyService

from ._helpers import limit_offset


def run(input_data, context):
    try:
        if not isinstance(input_data, dict):
            input_data = {}
        limit, offset = limit_offset(input_data)
        companies, total = CompanyService().list_companies(limit=limit, offset=offset)
        return ok({"companies": companies, "total": total})
    except Exception as exc:
        return error("company list failed: " + str(exc), "COMPANY_LIST_ERROR")
