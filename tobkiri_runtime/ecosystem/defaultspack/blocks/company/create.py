from blocks._common import ok, error
from domain.company.service import CompanyService

from ._helpers import invalid, require_dict


def run(input_data, context):
    if require_dict(input_data) is None:
        return invalid("input_data must be a dict")
    try:
        return ok(CompanyService().create_company(input_data))
    except ValueError as exc:
        return invalid(str(exc))
    except Exception as exc:
        return error("company create failed: " + str(exc), "COMPANY_CREATE_ERROR")
