from blocks._common import ok, error
from domain.company.service import CompanyService

from ._helpers import company_id_from


def run(input_data, context):
    try:
        if not isinstance(input_data, dict):
            input_data = {}
        conversation_id = str(input_data.get("conversation_id") or "").strip()
        if conversation_id:
            return ok(CompanyService().status_for_conversation(conversation_id, bootstrap=bool(input_data.get("bootstrap"))))
        return ok(CompanyService().status(company_id_from(input_data)))
    except Exception as exc:
        return error("company status failed: " + str(exc), "COMPANY_STATUS_ERROR")
