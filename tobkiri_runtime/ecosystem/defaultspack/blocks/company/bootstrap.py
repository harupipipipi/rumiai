from blocks._common import ok, error
from domain.company.service import CompanyService


def run(input_data, context):
    try:
        if not isinstance(input_data, dict):
            input_data = {}
        metadata = input_data.get("metadata") if isinstance(input_data, dict) and isinstance(input_data.get("metadata"), dict) else None
        conversation_id = str(input_data.get("conversation_id") or (metadata or {}).get("conversation_id") or "").strip()
        scope = str(input_data.get("scope") or (metadata or {}).get("scope") or "").strip()
        if conversation_id and scope in {"conversation", "chat", "main_chat"}:
            company = CompanyService().bootstrap_conversation_company(conversation_id, metadata=metadata)
        else:
            company = CompanyService().bootstrap_default_company(metadata=metadata)
        return ok({"bootstrapped": True, "company": company})
    except Exception as exc:
        return error("company bootstrap failed: " + str(exc), "COMPANY_BOOTSTRAP_ERROR")
