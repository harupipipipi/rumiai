from blocks._common import ok, error
from domain.company.service import CompanyService


def run(input_data, context):
    try:
        metadata = input_data.get("metadata") if isinstance(input_data, dict) and isinstance(input_data.get("metadata"), dict) else None
        company = CompanyService().bootstrap_default_company(metadata=metadata)
        return ok({"bootstrapped": True, "company": company})
    except Exception as exc:
        return error("company bootstrap failed: " + str(exc), "COMPANY_BOOTSTRAP_ERROR")
